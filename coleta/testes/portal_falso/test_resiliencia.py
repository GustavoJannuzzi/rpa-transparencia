"""Resiliência e retomada do robô de navegador, sem rede.

O Playwright intercepta as requisições e serve as amostras; injeta erro 500,
lentidão e queda de sessão. O resultado final tem de ser igual ao da rodada limpa,
e uma coleta interrompida no meio, retomada, também.
"""

from __future__ import annotations

import json

import httpx
import pytest
from playwright.async_api import async_playwright

from coleta.fontes.base import Contexto
from coleta.fontes.cmc_elotech.fonte import CmcElotechAPI
from coleta.fontes.cmc_legado.fonte import CmcLegado
from coleta.nucleo import execucao
from coleta.nucleo.banco import conectar

from ..apoio.replay_legado import Replay, transporte_sem_rede
from ..conftest import AMOSTRAS


def foto(con, fonte: str) -> list[tuple]:
    return sorted(tuple(r) for r in con.execute(
        "SELECT chave, ref_parlamentar, beneficiario_tipo, competencia, valor FROM despesas WHERE fonte=?", (fonte,)))


async def rodar_legado(replay: Replay, *, parar_apos: int | None = None, so_coletar: bool = False):
    con = conectar()
    async with async_playwright() as pw:
        nav = await pw.chromium.launch()
        ctx = Contexto(con=con, navegador=nav, transporte_http=transporte_sem_rede(), rotas_navegador=[("**/*", replay.rota)])
        f = CmcLegado()
        await f.abrir(ctx)
        try:
            if not so_coletar:
                await execucao.descobrir(f)
            placar = await execucao.coletar(f, parar_apos=parar_apos)
        finally:
            await f.fechar()
            await nav.close()
    return con, placar


@pytest.fixture
async def limpa(dados_tmp):
    con, placar = await rodar_legado(Replay())
    resultado = foto(con, "cmc_legado")
    con.close()
    assert placar.ok == 4 and placar.erro == 0
    assert len(resultado) == 81 + 47 + 43 + 22 - 0  # todas as linhas viram despesa (nenhuma ilegível nas amostras)
    return resultado


async def test_falhas_injetadas_dao_o_mesmo_resultado_da_rodada_limpa(limpa, tmp_path, monkeypatch):
    monkeypatch.setenv("RPA_DADOS", str(tmp_path / "dados-com-falhas"))
    replay = Replay({
        "Diarias_2013.pdf": ["sessao"],      # a aplicação avisa "Sua sessão expirou." e volta ao início
        "Diarias_2014.pdf": ["500", "500"],  # duas falhas de servidor seguidas
        "Diarias_2015.pdf": ["lento"],       # demora, mas chega
    })
    con, placar = await rodar_legado(replay)
    assert placar.erro == 0 and placar.ok == 4
    assert placar.tentativas_extras == 3
    assert replay.pedidos["Diarias_2014.pdf"] == 3
    assert foto(con, "cmc_legado") == limpa
    con.close()


async def test_falha_que_nao_passa_vira_erro_com_evidencia(dados_tmp):
    replay = Replay({"Diarias_2016.pdf": ["500"] * 10})
    con, placar = await rodar_legado(replay)
    assert placar.ok == 3 and placar.erro == 1
    linha = con.execute("SELECT situacao, evidencia, ultimo_erro FROM inventario WHERE chave='diarias-2016'").fetchone()
    assert linha["situacao"] == "erro" and "FalhaTransitoria" in linha["ultimo_erro"]
    pasta = dados_tmp / linha["evidencia"]
    assert (pasta / "tela.png").exists() and (pasta / "rastro.zip").exists() and (pasta / "erro.txt").exists()
    # rodar de novo, com o portal de volta, pega só o que faltou
    con.close()
    con, placar = await rodar_legado(Replay(), so_coletar=True)
    assert placar.ok == 1 and placar.pulados == 3
    con.close()


async def test_retomada_depois_de_interromper_no_meio(limpa, tmp_path, monkeypatch):
    monkeypatch.setenv("RPA_DADOS", str(tmp_path / "dados-interrompido"))
    with pytest.raises(execucao.Interrompido):
        await rodar_legado(Replay(), parar_apos=2)
    con = conectar()
    situacoes = dict(con.execute("SELECT situacao, COUNT(*) FROM inventario GROUP BY 1").fetchall())
    assert situacoes == {"ok": 2, "pendente": 2}
    con.close()
    con, placar = await rodar_legado(Replay(), so_coletar=True)
    assert placar.pulados == 2 and placar.ok == 2
    assert foto(con, "cmc_legado") == limpa
    # e rodar tudo de novo, refazendo, não duplica nada
    con.close()
    con = conectar()
    antes = con.execute("SELECT COUNT(*) FROM despesas").fetchone()[0]
    con.close()
    async with async_playwright() as pw:
        nav = await pw.chromium.launch()
        con = conectar()
        f = CmcLegado()
        await f.abrir(Contexto(con=con, navegador=nav, transporte_http=transporte_sem_rede(), rotas_navegador=[("**/*", Replay().rota)]))
        await execucao.coletar(f, refazer=True)
        await f.fechar()
        await nav.close()
    assert con.execute("SELECT COUNT(*) FROM despesas").fetchone()[0] == antes
    assert foto(con, "cmc_legado") == limpa
    con.close()


# ---------------------------------------------------------------- API (httpx), sem navegador
def _transporte_elotech(falhas: list[str]):
    sample = {a: json.loads((AMOSTRAS / "cmc_elotech" / f"diarias_{a}.json").read_text(encoding="utf-8")) for a in (2017, 2018, 2022, 2023)}
    fila = list(falhas)

    def responder(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("robots.txt"):
            return httpx.Response(404)
        if "/api/diarias" in req.url.path:
            if req.headers.get("entidade") != "1":
                return httpx.Response(500, text="MissingRequestHeaderException")
            if fila:
                f = fila.pop(0)
                if f == "500":
                    return httpx.Response(503, text="indisponível")
                if f == "timeout":
                    raise httpx.ReadTimeout("demorou", request=req)
            return httpx.Response(200, json=sample[int(req.url.params["exercicio"])])
        return httpx.Response(404)

    return httpx.MockTransport(responder)


async def _coletar_elotech(falhas: list[str]):
    con = conectar()
    f = CmcElotechAPI()
    await f.abrir(Contexto(con=con, transporte_http=_transporte_elotech(falhas)))
    for a in (2017, 2018, 2022, 2023):
        con.execute("INSERT INTO inventario(fonte, chave, descricao, periodo, parametros) VALUES(?,?,?,?,?)",
                    (f.id, f"diarias-{a}", "", str(a), json.dumps({"ano": a})))
    placar = await execucao.coletar(f)
    await f.fechar()
    return con, placar


async def test_api_com_503_e_timeout_da_o_mesmo_resultado(dados_tmp, tmp_path, monkeypatch):
    con, placar = await _coletar_elotech([])
    limpo = foto(con, "cmc_elotech")
    con.close()
    assert placar.ok == 4 and limpo
    monkeypatch.setenv("RPA_DADOS", str(tmp_path / "dados-api-falhas"))
    con, placar = await _coletar_elotech(["500", "timeout", "500"])
    assert placar.ok == 4 and placar.erro == 0 and placar.tentativas_extras == 3
    assert foto(con, "cmc_elotech") == limpo
    con.close()


async def test_contexto_novo_a_cada_item_da_o_mesmo_resultado(limpa, tmp_path, monkeypatch):
    """Trocar o contexto do navegador entre os itens (o que libera o Temp) não muda nada no resultado."""
    from coleta import config
    from coleta.fontes.base import FonteNavegador

    monkeypatch.setenv("RPA_DADOS", str(tmp_path / "dados-contexto"))
    monkeypatch.setattr(config, "ITENS_POR_CONTEXTO", 1)
    trocas = []
    monkeypatch.setattr(FonteNavegador, "ao_renovar", lambda self: trocas.append(1))
    con, placar = await rodar_legado(Replay())
    assert placar.ok == 4 and placar.erro == 0 and len(trocas) == 3
    assert foto(con, "cmc_legado") == limpa
    con.close()


async def test_disco_quase_cheio_para_antes_do_item_e_deixa_pendente(dados_tmp, monkeypatch):
    from coleta import config

    monkeypatch.setattr(config, "DISCO_MINIMO_MB", 10**9)  # mais do que qualquer disco tem
    con, placar = await rodar_legado(Replay())
    assert placar.ok == 0 and placar.erro == 0 and placar.parou and "disco quase cheio" in placar.parou
    situacoes = dict(con.execute("SELECT situacao, COUNT(*) FROM inventario GROUP BY 1").fetchall())
    assert situacoes == {"pendente": 4}
    con.close()


async def test_fonte_sem_rastro_ainda_deixa_a_evidencia_do_erro(dados_tmp, monkeypatch):
    """Fonte de item longo não grava rastro (ele fica no Temp até o navegador fechar); no erro,
    o print da página inteira e o HTML continuam."""
    monkeypatch.setattr(CmcLegado, "rastrear", False)
    con, placar = await rodar_legado(Replay({"Diarias_2016.pdf": ["500"] * 10}))
    assert placar.erro == 1 and placar.ok == 3
    linha = con.execute("SELECT evidencia FROM inventario WHERE chave='diarias-2016'").fetchone()
    pasta = dados_tmp / linha["evidencia"]
    assert (pasta / "tela.png").exists() and (pasta / "pagina.html").exists() and not (pasta / "rastro.zip").exists()
    con.close()
