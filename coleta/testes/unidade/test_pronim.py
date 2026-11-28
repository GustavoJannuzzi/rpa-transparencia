"""Govbr Pronim, sem rede: a leitura da tabela por credor pelo cabeçalho e a escolha
da unidade gestora. O robô inteiro contra o portal falso, que prova que o CPF não
chega ao disco, está em `portal_falso/test_pronim.py`."""

from __future__ import annotations

from decimal import Decimal

import pytest

from coleta.fontes.pronim.fonte import ler_linhas, unidade_da_camara
from coleta.nucleo.erros import PortalMudou


# ---------------------------------------------------------------- a tabela
def test_tabela_por_credor_pelo_cabecalho_e_coluna_que_sumiu():
    cab = ["Nome", "CNPJ/CPF", "Valor Empenhado", "Valor Em Liquidação", "Valor Liquidado", "Valor Pago", "Valor Anulado"]
    c = ler_linhas(cab, [["Fulana", "123", "R$ 1.694,49", "R$ 0,00", "R$ 1.694,49", "R$ 1.694,49", "R$ 0,00"]])
    assert c[0].valores["empenhado"] == Decimal("1694.49") and c[0].nome == "Fulana"
    with pytest.raises(PortalMudou):
        ler_linhas([x for x in cab if x != "Valor Anulado"], [])


def test_unidade_gestora_e_a_da_camara_e_a_consolidada_so_quando_e_a_unica():
    assert unidade_da_camara([("-1", "CONSOLIDADA"), ("1", "CÂMARA MUNICIPAL"), ("0", "PREFEITURA MUNICIPAL")]) == ("1", "CÂMARA MUNICIPAL")
    assert unidade_da_camara([("-1", "CONSOLIDADA")]) == ("-1", "CONSOLIDADA")
    with pytest.raises(PortalMudou):
        unidade_da_camara([("-1", "CONSOLIDADA"), ("0", "PREFEITURA MUNICIPAL")])
