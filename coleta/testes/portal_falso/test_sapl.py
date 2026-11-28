"""SAPL sem rede: a API é falsa, servida por um MockTransport. O robô descobre,
coleta, resiste a 503 e timeout, retoma sem repetir pedido, reproduz a coleta gravada
sem pedir nada, e a conferência liga os nomes sem criar vereador."""

from __future__ import annotations

import json

import httpx
import pytest

from coleta.destinos import atividade as publicar_atividade
from coleta.entidades import EntidadeSapl
from coleta.fontes.base import Contexto
from coleta.fontes.sapl.fonte import Sapl
from coleta.nucleo import atividade, execucao
from coleta.nucleo.banco import conectar
from coleta.nucleo.conferencia import conferir

# ---------------------------------------------------------------- SAPL de mentira, ponta a ponta

ENT = EntidadeSapl(fonte="sapl_teste", casa="cm-maringa", municipio="Maringá", ibge=4115200, host="https://sapl.teste.pr.leg.br",
                   de="2025-01-01", lote_presenca=2)


def _pagina(regs: list[dict], pagina: int = 1, por_pagina: int = 100) -> dict:
    trecho = regs[(pagina - 1) * por_pagina: pagina * por_pagina]
    tem_mais = pagina * por_pagina < len(regs)
    return {"pagination": {"total_entries": len(regs), "page": pagina, "next_page": pagina + 1 if tem_mais else None}, "results": trecho}


def _api_falsa(falhas: list[str], pedidos: list[str]):
    sessoes = [{"id": 10 + i, "data_inicio": f"2025-03-0{i + 1}", "tipo": 1, "numero": i + 1, "__str__": f"{i + 1}ª Sessão Ordinária da 1ª SL"}
               for i in range(3)]
    parl = [{"id": 1, "nome_completo": "Fulana de Tal", "nome_parlamentar": "Fulana"},
            {"id": 2, "nome_completo": "Beltrano Souza", "nome_parlamentar": "Beltrano"},
            {"id": 3, "nome_completo": "Pessoa Sem Cadastro", "nome_parlamentar": "Sem Cadastro"}]
    presenca = [{"id": 100 + k, "sessao_plenaria": s["id"], "parlamentar": p} for k, (s, p) in
                enumerate((s, p) for s in sessoes for p in (1, 2))] + [{"id": 200, "sessao_plenaria": 10, "parlamentar": 3}]
    just = [{"id": 7, "sessao_plenaria": 12, "parlamentar": 2, "tipo_ausencia": 1, "data": "2025-03-03", "ausencia": 2, "observacao": ""}]
    votos = [{"id": 500 + k, "voto": v, "parlamentar": p, "votacao": 1,
              "__str__": f"Votação: Ordem: Ordem do Dia/Expediente: 1 - PL nº 1 em {s} - Votação: Aprovado - Parlamentar: X"}
             for k, (v, p, s) in enumerate([("Sim", 1, "1ª Sessão Ordinária da 1ª SL"), ("Não", 2, "1ª Sessão Ordinária da 1ª SL"),
                                            ("Sim", 1, "3ª Sessão Ordinária da 1ª SL"),
                                            ("Sim", 1, "40ª Sessão Ordinária de 2013 da 15ª Legislatura")])]
    fila = list(falhas)

    def responder(req: httpx.Request) -> httpx.Response:
        p, q = req.url.path, req.url.params
        pedidos.append(str(req.url))
        if p.endswith("robots.txt"):
            return httpx.Response(200, text="User-agent: *\nDisallow: /materia/docacessorio/pdf/\n", headers={"content-type": "text/plain"})
        if fila and q.get("page_size") == "100" and "votoparlamentar" in p:
            f = fila.pop(0)
            if f == "503":
                return httpx.Response(503, text="indisponível")
            raise httpx.ReadTimeout("demorou", request=req)
        pg, tam = int(q.get("page", "1")), int(q.get("page_size", "10"))
        if p.endswith("/tiposessaoplenaria/"):
            return httpx.Response(200, json=_pagina([{"id": 1, "nome": "Ordinária"}]))
        if p.endswith("/tipojustificativa/"):
            return httpx.Response(200, json=_pagina([{"id": 1, "descricao": "Atestado médico"}]))
        if p.endswith("/sessaoplenaria/"):
            return httpx.Response(200, json=_pagina(sessoes, pg, tam))
        if p.endswith("/parlamentar/"):
            return httpx.Response(200, json=_pagina(parl, pg, tam))
        if p.endswith("/sessaoplenariapresenca/"):
            ids = {int(x) for x in q["sessao_plenaria__in"].split(",")}
            return httpx.Response(200, json=_pagina([r for r in presenca if r["sessao_plenaria"] in ids], pg, tam))
        if p.endswith("/justificativaausencia/"):
            return httpx.Response(200, json=_pagina(just, pg, tam))
        if p.endswith("/votoparlamentar/"):
            lista = sorted(votos, key=lambda v: -int(str(v["id"]))) if q.get("o") == "-id" else votos
            if "id__lte" in q:
                lista = [v for v in lista if int(str(v["id"])) <= int(q["id__lte"])]
            return httpx.Response(200, json=_pagina(lista, pg, tam))
        return httpx.Response(404)

    return httpx.MockTransport(responder)


async def _coletar(falhas: list[str], parar_apos: int | None = None):
    con = conectar()
    pedidos: list[str] = []
    f = Sapl(ENT)
    await f.abrir(Contexto(con=con, transporte_http=_api_falsa(falhas, pedidos)))
    n = await execucao.descobrir(f)
    try:
        placar = await execucao.coletar(f, parar_apos=parar_apos)
    finally:
        await f.fechar()
    return con, n, placar, pedidos


async def test_sapl_descobre_coleta_e_resiste_a_503_e_timeout(dados_tmp, monkeypatch, tmp_path):
    con, n, placar, _ = await _coletar([])
    # 1 página de parlamentares + 1 de sessões + 2 lotes de presença + 1 de ausência + 1 de votos
    assert n == 6 and placar.ok == 6 and placar.erro == 0
    tipos = {r[0]: r[1] for r in con.execute("SELECT tipo, COUNT(*) FROM atividades GROUP BY 1")}
    assert tipos == {"sessao": 3, "presenca": 7, "ausencia": 1, "voto": 3}  # o voto de 2013 fica fora da janela
    fora = con.execute("SELECT valor FROM totais_oficiais WHERE metrica='fora_da_janela'").fetchone()[0]
    assert fora == "1"
    assert con.execute("SELECT rotulo FROM atividades WHERE tipo='ausencia'").fetchone()[0] == "Atestado médico"
    limpo = sorted(tuple(r) for r in con.execute("SELECT chave, ref_parlamentar, ref_sessao, rotulo FROM atividades"))
    con.close()
    monkeypatch.setenv("RPA_DADOS", str(tmp_path / "dados-com-falhas"))
    con, n, placar, _ = await _coletar(["503", "timeout"])
    assert placar.ok == 6 and placar.erro == 0 and placar.tentativas_extras == 2
    assert sorted(tuple(r) for r in con.execute("SELECT chave, ref_parlamentar, ref_sessao, rotulo FROM atividades")) == limpo
    con.close()


async def test_sapl_retoma_de_onde_parou_e_nao_repete_pedido(dados_tmp):
    with pytest.raises(execucao.Interrompido):
        await _coletar([], parar_apos=3)
    con = conectar()
    feitos = con.execute("SELECT COUNT(*) FROM inventario WHERE situacao='ok'").fetchone()[0]
    assert feitos == 3
    con.close()
    # a segunda rodada só pega o que falta, e a descoberta refeita reaproveita o que já baixou
    con, _, placar, pedidos = await _coletar([])
    assert placar.ok == 3 and placar.pulados == 3
    assert not any("sessaoplenaria/" in p for p in pedidos)
    assert con.execute("SELECT COUNT(*) FROM atividades WHERE tipo='voto'").fetchone()[0] == 3
    con.close()


async def test_sapl_reproduz_a_coleta_gravada_sem_pedir_nada(dados_tmp, monkeypatch, tmp_path):
    con, _, _, _ = await _coletar([])
    gravado = sorted(tuple(r) for r in con.execute("SELECT chave, hash_original, coletado_em FROM atividades WHERE tipo!='sessao'"))
    con.close()
    monkeypatch.setenv("RPA_SAPL_REPRODUZIR", str(dados_tmp / "cache" / "sapl"))
    monkeypatch.setenv("RPA_DADOS", str(tmp_path / "canonico"))
    con = conectar()
    f = Sapl(ENT)
    pedidos: list[str] = []
    await f.abrir(Contexto(con=con, transporte_http=_api_falsa([], pedidos)))
    await execucao.descobrir(f)
    await execucao.coletar(f)
    await f.fechar()
    assert [p for p in pedidos if not p.endswith("robots.txt")] == []
    # mesmos bytes, mesmo hash, mesma data de coleta: a procedência é a da coleta original
    assert sorted(tuple(r) for r in con.execute("SELECT chave, hash_original, coletado_em FROM atividades WHERE tipo!='sessao'")) == gravado
    con.close()


async def test_sapl_conferencia_liga_nomes_sem_criar_vereador_e_fecha_a_equacao(dados_tmp, monkeypatch):
    monkeypatch.setattr(atividade, "fontes_de_atividade", lambda: {"sapl_teste": "cm-maringa"})
    monkeypatch.setattr(publicar_atividade, "_fontes", lambda: {"sapl_teste": Sapl(ENT)})
    con, _, _, _ = await _coletar([])
    # os vereadores vêm das fontes de despesa (aqui, o cadastro do Elotech)
    for ref, nome in (("mat:1", "FULANA DE TAL"), ("mat:2", "BELTRANO SOUZA")):
        con.execute("INSERT INTO pessoas_fonte(fonte, ref, periodo, nome, casa, extra) VALUES('elotech_maringa',?,'2025',?,'cm-maringa','{}')",
                    (ref, nome))
        con.execute("INSERT INTO inventario(fonte, chave, situacao) VALUES('elotech_maringa', ?, 'ok')", (ref,))
    conferir(con)
    ligados = {r[0]: r[1] for r in con.execute("SELECT ref, parlamentar_id FROM parlamentar_ids WHERE fonte='sapl_teste'")}
    assert ligados == {"sapl:1": "ver-maringa-fulana-de-tal", "sapl:2": "ver-maringa-beltrano-souza"}
    # quem só existe no SAPL não vira vereador: vai para revisão, com os registros contados
    assert con.execute("SELECT COUNT(*) FROM parlamentares WHERE nome LIKE '%Cadastro%'").fetchone()[0] == 0
    rev = con.execute("SELECT motivo, detalhe FROM revisao WHERE fonte='sapl_teste'").fetchone()
    assert "não fecha" in rev[0] and json.loads(rev[1])["registros"] == 1
    eq = con.execute("SELECT esperado, obtido, resultado, detalhe FROM conferencias WHERE fonte='sapl_teste' "
                     "AND verificacao='origem_igual_coletado_mais_revisao'").fetchone()
    assert eq[2] == "confere" and "fora da janela = 1" in eq[3]
    parl, casas, _ = publicar_atividade.resumos(con)
    a = parl["ver-maringa-beltrano-souza"][0]
    assert a["presencas"] == 3 and a["ausencias"] == [{"rotulo": "Atestado médico", "n": 1}] and a["votos"] == [{"rotulo": "Não", "n": 1}]
    assert a["documento"] == "https://sapl.teste.pr.leg.br/parlamentar/2"
    c = casas["cm-maringa"][0]
    assert c["situacao"] == "completa" and [v["nome"] for v in c["vereadores"]] == sorted(v["nome"] for v in c["vereadores"])
    con.close()
