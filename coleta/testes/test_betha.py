"""Betha Cloud genérico: a consulta achada pelo texto do menu e a leitura da tabela,
sem rede. As linhas são montadas aqui, com nomes inventados; o menu imita o JSON
que a página recebe (formato visto em 26/11/2026 em Fazenda Rio Grande e
Bandeirantes)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from coleta import entidades
from coleta.fontes import FONTES
from coleta.fontes.betha.fonte import COLUNAS_DIARIAS, BethaCloud, candidatas_diarias, consultas_do_menu
from coleta.fontes.cmc_betha.fonte import CmcBetha
from coleta.modelo import ItemInventario, Resultado
from coleta.nucleo.erros import PortalMudou

MENU = [
    {"nome": "Receitas e Despesas", "consultas": [], "subMenus": [
        {"nome": "Diárias", "consultas": [
            {"id": 91026, "titulo": "Despesas de Diárias e Viagens", "tipo": "CONSULTA_PADRAO"},
            {"id": 211742, "titulo": "Diárias", "tipo": "CONSULTA_PADRAO"},
        ], "subMenus": []},
        {"nome": "Receitas públicas", "consultas": [
            {"id": 91011, "titulo": "Receitas Orçamentárias Diárias", "tipo": "CONSULTA_PADRAO"},
        ], "subMenus": []},
    ]},
    {"nome": "Pessoal", "consultas": [
        {"id": 58003, "titulo": "DIÁRIAS", "tipo": "CONSULTA_PADRAO"},
        {"id": 990, "titulo": "Diárias", "tipo": "LINK", "url": "https://exemplo/#/x/consulta/1"},
        {"id": 73853, "titulo": "Relatório Resumido Mensal de Diárias Concedidas", "tipo": "RELATORIOS"},
    ], "subMenus": []},
    {"nome": "Mais consultas", "consultas": [
        {"id": 91027, "titulo": "Despesas de Diárias e Viagens - Educação", "tipo": "CONSULTA_PADRAO"},
        {"id": 358760, "titulo": "Diárias.", "tipo": "CONSULTA_PADRAO"},
        {"id": 324825, "titulo": "Diárias 2026", "tipo": "CONSULTA_PADRAO"},
    ], "subMenus": []},
]

ENT = next(e for e in entidades.betha() if e.fonte == "betha_fazenda_rio_grande")


def _linha(pagina: int, **kw) -> dict:
    base = {"ANO": "2026", "NUMERO": "10", "CREDOR": "FULANA DE TAL", "CNPJ CPF CREDOR": "123.456.***-**",
            "CARGO DO CREDOR": "Vereador", "QUANTIDADE": "2", "VALOR PREVISTO DIARIA R": "R$ 1.200,50",
            "PERIODO": "03-11-2026 a 04-11-2026", "FINALIDADE": "Curso com o assessor BELTRANO DA SILVA", "LOCAL DE DESTINO": "Curitiba"}
    return {"_pagina": pagina, **base, **kw}


def _ler(fonte, linhas, hits=(), rotulos=None) -> Resultado:
    res = Resultado()
    fonte._diarias(ItemInventario(chave="diarias-consulta-211742", descricao="", periodo="todos"), linhas, list(hits),
                   ["h1", "h2"], "https://transparencia.betha.cloud/#/x/consulta/211742", res,
                   list(COLUNAS_DIARIAS) if rotulos is None else rotulos)
    return res


# ---------------------------------------------------------------- menu
def test_a_consulta_e_achada_pelo_texto_do_menu_em_qualquer_grupo():
    achadas = {c["id"] for _, c in candidatas_diarias(MENU)}
    # "Diárias", "DIÁRIAS", "Diárias." e "Diárias 2026", em grupos diferentes; nunca as
    # parecidas ("Despesas de Diárias e Viagens", "Receitas Orçamentárias Diárias"),
    # nem link externo ou relatório com o mesmo texto
    assert achadas == {211742, 58003, 358760, 324825}
    caminhos = {c["id"]: cam for cam, c in consultas_do_menu(MENU)}
    assert caminhos[211742] == ("Receitas e Despesas", "Diárias")


def test_toda_camara_do_betha_tem_portal_ibge_e_id_que_a_plataforma_aceita():
    import re

    todas = entidades.betha(todas=True)
    assert len({e.portal for e in todas}) == len(todas)
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{22}==", e.portal) for e in todas)
    assert all(re.fullmatch(r"[a-z_]+", e.fonte) and str(e.ibge).startswith("41") for e in todas)
    coletadas = {f.id for f in FONTES if isinstance(f, BethaCloud)}
    # as de fora estão na configuração (com o motivo), mas não viram fonte
    assert all(e.fonte not in coletadas for e in todas if e.fora)
    assert all(e.detalhe for e in todas if e.fora)
    assert isinstance(next(f for f in FONTES if f.id == "cmc_betha"), CmcBetha)


# ---------------------------------------------------------------- leitura
def test_so_vereador_guarda_nome_e_a_finalidade_nao_e_publicada():
    f = BethaCloud(ENT)
    linhas = [
        _linha(1),
        _linha(1, NUMERO="11", CREDOR="SERVIDOR INVENTADO", **{"CARGO DO CREDOR": "Assessor Parlamentar"}),
        _linha(2, NUMERO="12", CREDOR="OUTRO INVENTADO", **{"CARGO DO CREDOR": "Veriador"}),
        _linha(2, NUMERO="13", CREDOR="SEM CARGO INVENTADO", **{"CARGO DO CREDOR": "-"}),
        _linha(2, NUMERO="14", CREDOR="PRESIDENTE INVENTADA", **{"CARGO DO CREDOR": "Presidente da Câmara"}),
    ]
    res = _ler(f, linhas)
    assert len(res.despesas) == len(linhas) and not res.pendencias
    por_numero = {d.extra["numero"]: d for d in res.despesas}
    assert por_numero["10"].nome_beneficiario == "FULANA DE TAL" and por_numero["10"].ref_parlamentar == "nome:FULANA DE TAL"
    assert por_numero["14"].beneficiario_tipo == "parlamentar"
    for n in ("11", "12", "13"):
        # servidor, cargo parecido com vereador e cargo vazio: sem nome, na leitura
        assert por_numero[n].nome_beneficiario is None and por_numero[n].ref_parlamentar is None
    # a finalidade pode citar servidor pelo nome: só o destino vai para a descrição
    assert all("BELTRANO" not in (d.descricao or "") for d in res.despesas)
    assert por_numero["10"].descricao == "Curitiba"
    assert por_numero["10"].valor == Decimal("1200.50") and por_numero["10"].competencia == "2026-11"
    assert all(d.casa == ENT.casa for d in res.despesas)
    assert {p.nome for p in res.pessoas} == {"FULANA DE TAL", "PRESIDENTE INVENTADA"}
    # o CPF mascarado da tela não vai para lugar nenhum
    assert all("***" not in str(d.model_dump()) for d in res.despesas)


def test_curitiba_continua_publicando_a_finalidade_revisada():
    res = _ler(CmcBetha(), [_linha(1)])
    assert res.despesas[0].descricao == "Curitiba — Curso com o assessor BELTRANO DA SILVA"


def test_linha_ilegivel_vai_para_revisao_e_chave_estavel_sem_colisao():
    f = BethaCloud(ENT)
    linhas = [_linha(1), _linha(1), _linha(1, **{"VALOR PREVISTO DIARIA R": "R$ --"}), _linha(1, NUMERO="9", PERIODO="a definir")]
    a, b = _ler(f, linhas), _ler(f, linhas)
    assert len(a.despesas) == 2 and len(a.pendencias) == 2
    # duas linhas iguais (diária e complemento com o mesmo número) não colidem
    assert len({d.chave for d in a.despesas}) == 2
    assert [d.chave for d in a.despesas] == [d.chave for d in b.despesas]


def test_coluna_que_sumiu_ou_tela_diferente_da_resposta_e_portal_que_mudou():
    f = BethaCloud(ENT)
    with pytest.raises(PortalMudou):
        _ler(f, [_linha(1)], rotulos=sorted(COLUNAS_DIARIAS - {"CARGO DO CREDOR"}))
    hit = {"numeroDiaria": 10, "credor": "FULANA DE TAL", "valorTotal": 1200.5, "periodoDiarias": "03-11-2026 a 04-11-2026"}
    assert _ler(f, [_linha(1)], hits=[hit]).despesas[0].extra["conferido_com_resposta_da_tela"] is True
    with pytest.raises(PortalMudou):
        _ler(f, [_linha(1)], hits=[{**hit, "valorTotal": 1100}])


def test_consulta_vazia_e_resultado_nao_erro():
    res = _ler(BethaCloud(ENT), [])
    assert not res.despesas and not res.pendencias
