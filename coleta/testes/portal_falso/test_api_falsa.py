"""O robô inteiro contra APIs falsas (httpx.MockTransport), sem rede: o adaptador
genérico do Elotech (Maringá), a CLDF, a ALMG e a ALESP, com 503 e timeout injetados e
nenhum CPF gravado."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from coleta import config, entidades
from coleta.fontes.alesp.fonte import Alesp
from coleta.fontes.almg.fonte import Almg
from coleta.fontes.base import Contexto
from coleta.fontes.cldf.fonte import Cldf
from coleta.fontes.elotech.fonte import ElotechAPI
from coleta.modelo import ItemInventario
from coleta.nucleo import execucao
from coleta.nucleo.banco import conectar
from coleta.nucleo.erros import PortalMudou
from coleta.nucleo.texto import cpfs_expostos

from ..conftest import AMOSTRAS

MARINGA = next(e for e in entidades.elotech() if e.fonte == "elotech_maringa")


def _json(rel: str):
    return json.loads((AMOSTRAS / rel).read_text(encoding="utf-8"))


def _transporte_maringa(falhas: list[str], cnpj: str | None = None):
    dia = _json("elotech/maringa_diarias_2025.json")
    serv = _json("elotech/maringa_servidores_2025.json")
    ent = _json("elotech/maringa_entidades.json")
    fila = list(falhas)

    def responder(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p.endswith("robots.txt"):
            return httpx.Response(200, text="<html>SPA</html>", headers={"content-type": "text/html"})
        if p.endswith("/api/entidades"):
            return httpx.Response(200, json=[{**e, "cnpj": cnpj or e["cnpj"]} for e in ent])
        if "/api/exercicios/entidade/6" in p:
            return httpx.Response(200, json=[{"id": {"entidade": {"id": 6}, "exercicio": 2025}}, {"id": {"entidade": {"id": 1}, "exercicio": 2027}}])
        if req.headers.get("entidade") != "6":
            return httpx.Response(500, text="MissingRequestHeaderException")
        if "/api/diarias" in p:
            # a falha injetada vale para a coleta (a descoberta não repete, por desenho)
            if fila and req.url.params.get("size") != "1":
                f = fila.pop(0)
                if f == "503":
                    return httpx.Response(503, text="indisponível")
                if f == "timeout":
                    raise httpx.ReadTimeout("demorou", request=req)
            if req.url.params.get("size") == "1":
                return httpx.Response(200, json={**dia, "content": dia["content"][:1], "last": False})
            return httpx.Response(200, json=dia)
        if "/api/servidores" in p:
            return httpx.Response(200, json=serv)
        return httpx.Response(404)

    return httpx.MockTransport(responder)


async def _coletar_maringa(falhas: list[str]):
    con = conectar()
    f = ElotechAPI(MARINGA)
    await f.abrir(Contexto(con=con, transporte_http=_transporte_maringa(falhas)))
    n = await execucao.descobrir(f)
    placar = await execucao.coletar(f)
    await f.fechar()
    return con, n, placar


async def test_elotech_generico_descobre_coleta_e_resiste_a_503_e_timeout(dados_tmp, tmp_path, monkeypatch):
    con, n, placar = await _coletar_maringa([])
    assert n == 2 and placar.ok == 2 and placar.erro == 0  # o exercício de outra entidade (2027) não entra
    limpo = sorted(tuple(r) for r in con.execute("SELECT chave, ref_parlamentar, beneficiario_tipo, valor, casa FROM despesas"))
    assert len(limpo) == 41 and {r[4] for r in limpo} == {"cm-maringa"}
    assert con.execute("SELECT COUNT(*) FROM remuneracoes").fetchone()[0] > 0
    con.close()
    monkeypatch.setenv("RPA_DADOS", str(tmp_path / "dados-com-falhas"))
    con, n, placar = await _coletar_maringa(["503", "timeout", "503"])
    assert placar.ok == 2 and placar.erro == 0 and placar.tentativas_extras == 3
    assert sorted(tuple(r) for r in con.execute("SELECT chave, ref_parlamentar, beneficiario_tipo, valor, casa FROM despesas")) == limpo
    con.close()


async def test_entidade_com_outro_cnpj_para_a_coleta(dados_tmp):
    con = conectar()
    f = ElotechAPI(MARINGA)
    await f.abrir(Contexto(con=con, transporte_http=_transporte_maringa([], cnpj="00000000000191")))
    with pytest.raises(PortalMudou, match="outro CNPJ"):
        await f.descobrir()
    await f.fechar()
    con.close()


def _transporte_cldf():
    html = (AMOSTRAS / "cldf" / "conjunto.html").read_text(encoding="utf-8")
    csv_ = (AMOSTRAS / "cldf" / "verbas_2023_amostra.csv").read_bytes()
    xlsx = (AMOSTRAS / "cldf" / "verbas_2025_amostra.xlsx").read_bytes()

    def responder(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p.endswith("robots.txt"):
            return httpx.Response(200, text="User-agent: *\nDisallow: /api/\nCrawl-Delay: 0\n", headers={"content-type": "text/plain"})
        if p.endswith("/dataset/verbas-indenizatorias"):
            return httpx.Response(200, text=html, headers={"content-type": "text/html"})
        if p.endswith(".csv"):
            return httpx.Response(200, content=csv_)
        if p.endswith(".xlsx"):
            return httpx.Response(200, content=xlsx)
        return httpx.Response(404)

    return httpx.MockTransport(responder)


async def test_cldf_ponta_a_ponta_sem_cpf_gravado(dados_tmp, monkeypatch):
    con = conectar()
    f = Cldf(entidades.assembleias()["cldf"])
    # só os anos que a amostra tem
    monkeypatch.setattr(f, "de", 2023)
    monkeypatch.setattr(f, "ate", 2025)
    await f.abrir(Contexto(con=con, transporte_http=_transporte_cldf()))
    await execucao.descobrir(f)
    item = con.execute("SELECT parametros FROM inventario WHERE fonte='cldf'").fetchone()
    anos = json.loads(item[0])["anos"]
    # a amostra serve de recurso para todos os anos da página: o teste fica com 2023 e 2025
    anos = {a: v for a, v in anos.items() if a in ("2023", "2025")}
    anos["2023"]["conferir"] = []
    anos["2025"]["conferir"] = []
    con.execute("UPDATE inventario SET parametros=? WHERE fonte='cldf'", (json.dumps({"anos": anos}),))
    placar = await execucao.coletar(f)
    await f.fechar()
    assert placar.ok == 1 and placar.erro == 0
    tudo = json.dumps([dict(r) for r in con.execute("SELECT * FROM despesas")] + [dict(r) for r in con.execute("SELECT * FROM pessoas_fonte")],
                      ensure_ascii=False, default=str)
    assert "111.111.111-11" not in tudo and "11111111111" not in tudo  # o CPF falso do deputado não foi gravado
    motivos = {r[0] for r in con.execute("SELECT motivo FROM pendencias")}
    assert any("colunas deslocadas" in m for m in motivos)
    # mesma pessoa, mesma referência: as grafias ligadas pelo CPF na memória
    refs = {r[0] for r in con.execute("SELECT DISTINCT ref_parlamentar FROM despesas")}
    assert all(r.startswith("nome:") for r in refs)
    con.close()


async def test_almg_coleta_o_mes_com_procedencia_por_nota(dados_tmp):
    j = _json("almg/verba_mes.json")

    def responder(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("robots.txt"):
            return httpx.Response(200, text="User-agent: *\nAllow: /api/v2/\nDisallow: /\n", headers={"content-type": "text/plain"})
        return httpx.Response(200, json=j)

    con = conectar()
    f = Almg(entidades.assembleias()["almg"])
    await f.abrir(Contexto(con=con, transporte_http=httpx.MockTransport(responder)))
    item = ItemInventario(chave="verbas-12193-2025", descricao="", periodo="2025",
                          parametros={"deputado": 12193, "nome": "Deputado", "partido": "PV", "ano": 2025, "meses": [9]})
    r = await f.coletar_item(item)
    await f.fechar()
    notas = sum(len(t["listaDetalheVerba"]) for t in j["list"])
    assert len(r.despesas) == notas and not r.pendencias
    assert all(d.procedencia.localizador and d.granularidade == "nota" and d.casa == "al-mg" for d in r.despesas)
    assert next(t for t in r.totais if t.metrica == "tipos_que_fecham").valor == f"{len(j['list'])}/{len(j['list'])}"
    con.close()


async def test_alesp_publica_agregado_e_nunca_grava_o_cpf(dados_tmp, monkeypatch):
    import gzip

    amostra = (AMOSTRAS / "alesp" / "despesas_amostra.json").read_bytes()
    deputados = {"deputados": [{"matricula": x["matricula"], "siglaPartido": "XX"} for x in json.loads(amostra)["despesas"][:3]]}
    con = conectar()
    f = Alesp(entidades.assembleias()["alesp"])
    destino: Path = config.cache() / "alesp" / "despesas.json.gz"
    destino.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(destino, "wb") as z:
        z.write(amostra)
    versao = {"last_modified": "x", "etag": "y", "tamanho": "1"}
    destino.with_suffix(".meta.json").write_text(json.dumps({"versao": versao, "sha256": "abc"}), encoding="utf-8")

    def responder(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("robots.txt"):
            return httpx.Response(404)
        return httpx.Response(200, json=deputados)

    await f.abrir(Contexto(con=con, transporte_http=httpx.MockTransport(responder)))
    r = await f.coletar_item(ItemInventario(chave="despesas", descricao="", periodo="", parametros={"versao": versao}))
    await f.fechar()
    no_periodo = sum(1 for x in json.loads(amostra)["despesas"] if 2023 <= int(x["ano"]) <= 2026)
    assert len(r.despesas) + len(r.pendencias) == no_periodo
    assert all(d.granularidade == "agregado" and d.data is None for d in r.despesas)
    assert cpfs_expostos(json.dumps([d.model_dump(mode="json") for d in r.despesas])) == 0
    assert not any("111111" in (d.fornecedor_doc or "") for d in r.despesas)  # PF fica mascarado
    con.close()
