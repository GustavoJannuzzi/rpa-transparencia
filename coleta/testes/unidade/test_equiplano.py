"""Equiplano, sem rede: o leitor do relatório impresso, a máscara de CPF e RG e a
regra de quem é vereador, nas linhas que o portal falso (`apoio/equiplano_falso.py`)
devolve. O robô de tela inteiro contra esse portal está em
`portal_falso/test_equiplano.py`."""

from __future__ import annotations

from decimal import Decimal

import pytest

from coleta.entidades import EntidadeEquiplano
from coleta.fontes.equiplano import relatorio as rel
from coleta.fontes.equiplano.fonte import Equiplano, eh_a_camara
from coleta.modelo import ItemInventario, Procedencia
from coleta.nucleo.texto import cpfs_expostos

from ..apoio.equiplano_falso import CPF_SERVIDORA, CPF_SOLTO, CPF_VEREADORA, ENTIDADE, MUNICIPIO, NOME_SERVIDORA, NOME_VEREADORA, relatorio

PROC = Procedencia(fonte="t", url="u", hash_original="h", coletado_em="2026-11-26")


def _so_digitos(cpf: str) -> str:
    return "".join(c for c in cpf if c.isdigit())


def _ent(host: str = "http://127.0.0.1:1") -> EntidadeEquiplano:
    return EntidadeEquiplano(fonte="equiplano_teste", casa="cm-vila-exemplo", municipio=MUNICIPIO, ibge=4199999, regiao="Teste",
                             host=host, entidade=ENTIDADE, de=2024, ate=2025)


# ---------------------------------------------------------------- a máscara e o leitor
def test_a_mascara_tira_cpf_e_rg_inteiros_e_o_cpf_solto_no_texto():
    bruto = relatorio(2025)
    assert cpfs_expostos(bruto.decode("cp1252")) >= 3  # a amostra tem mesmo o que a trava precisa pegar
    limpo = rel.limpar(bruto).decode("cp1252")
    assert cpfs_expostos(limpo) == 0
    for cpf in (CPF_VEREADORA, CPF_SERVIDORA, CPF_SOLTO):
        assert cpf not in limpo and _so_digitos(cpf) not in limpo
    assert "12345678" not in limpo and "9.876.543-2" not in limpo  # RG
    assert limpo.count(rel.OMITIDO) >= 6


def test_o_leitor_fecha_com_o_total_do_relatorio_impresso():
    r = rel.ler(rel.limpar(relatorio(2025)).decode("cp1252"))
    assert r.entidade == "CÂMARA MUNICIPAL DE VILA EXEMPLO - PR" and (r.inicio, r.fim) == ("01/01/2025", "31/12/2025")
    assert r.empenhos_no_arquivo == len(r.empenhos) == 3 and not r.problemas
    assert r.total_liquido == Decimal("2178.63") == sum(e.liquido for e in r.empenhos)
    v, s, c = r.empenhos
    # o cabeçalho da página 2 no meio do arquivo não vira linha de empenho
    assert (v.numero, v.natureza, v.codigo_credor, v.nome_credor) == ("16/2025", "AGENTES POLÍTICOS", "439091-1", NOME_VEREADORA)
    assert v.cargo_na_descricao == "Vereadora" and v.data_inicial == "13/01/2025" and v.destino == "Curitiba - PR"
    assert v.valor_total_diarias == "1694,49" and [m.data for m in v.liquidacoes] == ["13/01/202"]  # a data que o papel corta
    # estorno de empenho, e o de liquidação com o rótulo cortado ("Estorno de ")
    assert s.estornado == Decimal("484.14") and len(s.estornos_liquidacao) == 1 and s.liquido == Decimal("484.14")
    assert c.estornado == c.valor and c.liquido == 0 and c.data_inicial is None


def test_bloco_fora_do_formato_vira_problema_e_nao_some():
    texto = rel.limpar(relatorio(2025)).decode("cp1252").replace("17/2025;;;;20/02/2025", "17/2025;;;;sem data", 1)
    r = rel.ler(texto)
    assert len(r.empenhos) == 2 and len(r.problemas) == 1
    assert r.empenhos_no_arquivo == len(r.empenhos) + len(r.problemas)  # a conta da conferência continua fechando
    assert NOME_SERVIDORA not in r.problemas[0].texto


def test_quem_e_vereador_vem_da_natureza_e_conflito_descarta_o_nome():
    f = Equiplano(_ent())
    r = rel.ler(rel.limpar(relatorio(2025)).decode("cp1252"))
    item = ItemInventario(chave="diarias-2025", descricao="", periodo="2025")
    v, s, _ = (f._despesa(item, 2025, e, "k", PROC) for e in r.empenhos)
    assert v.beneficiario_tipo == "parlamentar" and v.nome_beneficiario == NOME_VEREADORA and v.ref_parlamentar == "mat:439091-1"
    assert s.beneficiario_tipo == "servidor" and s.nome_beneficiario is None and s.ref_parlamentar is None
    assert s.descricao == "Ponta Grossa - PR"  # só o destino; a descrição livre cita servidora pelo nome
    e = r.empenhos[0]
    e.cargo_na_descricao = "Motorista"
    conflito = f._despesa(item, 2025, e, "k", PROC)
    assert conflito.nome_beneficiario is None and conflito.extra["nota_cargo"]


@pytest.mark.parametrize("texto, municipio, esperado", [
    ("Câmara Municipal de Piên", "Piên", True),
    ("Santo Antônio Sudoeste Camara Municipal", "Santo Antônio do Sudoeste", True),
    ("Camara Municipal de Rio Bonito do Iguacu", "Rio Bonito do Iguaçu", True),
    ("Município de Manoel Ribas", "Manoel Ribas", False),
    ("Câmara Municipal de Terra Rica", "Piên", False),
])
def test_a_entidade_configurada_tem_de_ser_a_camara_do_municipio(texto, municipio, esperado):
    assert eh_a_camara(texto, municipio) is esperado
