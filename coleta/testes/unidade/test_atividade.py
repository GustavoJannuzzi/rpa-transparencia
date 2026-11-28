"""Atividade legislativa, sem rede: a sessão de cada voto do SAPL, achada pelo nome
inteiro, e as linhas de frequência de Curitiba, copiadas como o leitor de PDF as
entrega dos relatórios de 2019 a 2026. O robô do SAPL contra a API falsa está em
`portal_falso/test_sapl.py`."""

from __future__ import annotations

import pytest

from coleta.fontes.cmc_frequencia.fonte import _casa, competencia_do_cartao, nome_valido
from coleta.fontes.sapl.fonte import sessao_do_voto
from coleta.nucleo import atividade

# ---------------------------------------------------------------- SAPL: o voto e a sessão

SESSOES = {"50ª Sessão Ordinária da 2ª Sessão Legislativa da 19ª Legislatura": "990",
           "5ª Sessão Ordinária da 2ª Sessão Legislativa da 19ª Legislatura": "945"}


@pytest.mark.parametrize("texto,esperado", [
    ("Votação: Ordem: Ordem do Dia/Expediente: 3 - Projeto de Lei nº 118 de 2026 em 50ª Sessão Ordinária da 2ª Sessão Legislativa "
     "da 19ª Legislatura - Votação: Aprovado em 2ª votação - Parlamentar: Fulana (Vereadora)", "990"),
    # a matéria tem " em " e o resultado tem " - ": vale o nome inteiro da sessão
    ("Votação: Ordem: Ordem do Dia/Expediente: 1 - Moção em homenagem em 5ª Sessão Ordinária da 2ª Sessão Legislativa da 19ª "
     "Legislatura - Votação: Aprovado - em única - Parlamentar: X", "945"),
    # sessão de fora da janela (voto antigo migrado): não liga a nada
    ("Votação: Ordem: Ordem do Dia/Expediente: 3 - Veto nº 914 de 2013 em 71ª Sessão Ordinária de 2013 da 1ª Sessão Legislativa da "
     "15ª Legislatura - Votação: Rejeitado - Parlamentar: X", None),
])
def test_o_voto_se_liga_a_sessao_pelo_nome_inteiro(texto, esperado):
    assert sessao_do_voto(texto, SESSOES) == esperado


# ---------------------------------------------------------------- frequência de Curitiba

@pytest.mark.parametrize("linha,nome,valores", [
    ("Alexandre Leprevost(B) 08 0 0", "Alexandre Leprevost", (8, 0, 0)),
    ("1 Alexandre Leprevost 13[E] 1 0", "Alexandre Leprevost", (13, 1, 0)),
    ("3 Angelo Vanhoni 13 [G] 1 0", "Angelo Vanhoni", (13, 1, 0)),
    ("Renato Freitas 10 1[4] 0", "Renato Freitas", (10, 1, 0)),
    ("Indiara Barbosa 0 0 11(E)", "Indiara Barbosa", (0, 0, 11)),
    ("João da 5 Irmãos 11 0 0", "João da 5 Irmãos", (11, 0, 0)),
    ("Tico Kuzma PRESIDENTE PRESIDENTE PRESIDENTE", "Tico Kuzma", (None, None, None)),
    ("Marcelo Fachinello Presidente Presidente Presidente", "Marcelo Fachinello", (None, None, None)),
])
def test_linha_de_frequencia_em_cada_layout(linha, nome, valores):
    m = _casa(linha)
    assert m is not None
    assert m.group("nome").replace("(B)", "").strip() == nome or nome in m.group("nome")
    assert tuple(None if g.upper() == "PRESIDENTE" else int(g) for g in m.groups()[1:4]) == valores


@pytest.mark.parametrize("linha", [
    "Renato Freitas 10 1[4] 0 Sabino Picolo 11 0 0",  # duas linhas coladas
    "Alexandre Leprevost 3 11 15 12 14 15 17 11 12 11 9 130 0 0",  # consolidado anual (meses em colunas)
    "Angelo Vanhoni 9 0",  # célula faltando: vai para revisão
    "402.00751.2026 APROVADOS",
])
def test_linha_que_nao_e_de_um_vereador_nao_vira_linha(linha):
    assert _casa(linha) is None


def test_nome_com_celula_dentro_nao_e_nome():
    assert nome_valido("João da 5 Irmãos") and not nome_valido("Renato Freitas 10 1[4] 0 Sabino Picolo")


def test_periodo_do_cartao():
    assert competencia_do_cartao(2026, "Outubro") == "2026-10"
    assert competencia_do_cartao(2026, "Março") == "2026-03"
    assert competencia_do_cartao(2019, "2019") == "2019"
    assert competencia_do_cartao(2019, "1º semestre") is None


# ---------------------------------------------------------------- nomes

def test_nome_da_lista_de_presenca_fecha_sem_o_titulo_e_com_iniciais():
    exato, toks = atividade.indices({"ver-cwb-a": {"SARGENTO TANIA GUERREIRO"}, "ver-cwb-b": {"SERGIO RENATO BUENO BALAGUER"},
                                     "ver-cwb-c": {"GIORGIA PRATES"}, "ver-cwb-d": {"GIORGIA PRATES MANDATA PRETA"}})
    assert atividade.escolher({"Sgt. Tania Guerreiro"}, exato, toks) == ({"ver-cwb-a"}, "nome sem o título")
    assert atividade.escolher({"Sergio R. B. Balaguer"}, exato, toks)[0] == {"ver-cwb-b"}
    # nome exato vale primeiro; "Giorgia Prates - Mandata" casa com dois: fica em revisão, não se escolhe
    assert atividade.escolher({"Giorgia Prates"}, exato, toks) == ({"ver-cwb-c"}, "nome")
    assert len(atividade.escolher({"Giorgia Prates - Mandata"}, exato, toks)[0]) == 2
    assert atividade.escolher({"Professor Euller"}, exato, toks)[0] == set()
