"""Parser: as amostras reais gravadas pelo robô (25/11/2026) dão o resultado esperado."""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections.abc import Iterable
from datetime import date
from decimal import Decimal

import pytest

from coleta.de_para import cargo, categoria, eh_cargo_parlamentar
from coleta.fontes.camara_deputados.fonte import ler_linha_ceap
from coleta.fontes.cmc_betha.fonte import CmcBetha, chave_coluna
from coleta.fontes.cmc_elotech.fonte import CmcElotechAPI
from coleta.fontes.cmc_legado.parser import ler_pdf, ler_periodo, verificar_consistencia
from coleta.fontes.cmc_prefeitura.fonte import CmcPrefeitura, ler_grade
from coleta.fontes.tse.fonte import ler_candidaturas
from coleta.modelo import Despesa, ItemInventario, Procedencia, Resultado
from coleta.nucleo.erros import PortalMudou
from coleta.nucleo.texto import ValorIlegivel, cpfs_expostos, decimal_ponto, dinheiro_br, documento_fornecedor, mascarar_cpf, normalizar_nome

from .conftest import AMOSTRAS


def _soma(valores: Iterable[Decimal | None]) -> Decimal:
    """Soma de valores que não podem faltar: um None quebra o teste, como quebraria a soma."""
    total = Decimal(0)
    for v in valores:
        assert v is not None
        total += v
    return total

PROC = Procedencia(fonte="t", url="u", hash_original="h", coletado_em="2026-11-25")


# ---------------------------------------------------------------- utilitários
@pytest.mark.parametrize("txt,esperado", [
    ("R$ 1.234,56", "1234.56"), ("R$ 0,00", "0.00"), ("R$-2.113,91", "-2113.91"), ("610", "610"), ("R$ 14.500,00", "14500.00"),
])
def test_dinheiro_br(txt, esperado):
    assert dinheiro_br(txt) == Decimal(esperado)


@pytest.mark.parametrize("txt", ["R$ 610 + R$ 100", "", "abc", "R$ 1,2,3"])
def test_dinheiro_br_recusa_o_que_nao_e_um_valor(txt):
    with pytest.raises(ValorIlegivel):
        dinheiro_br(txt)


def test_decimal_ponto_nao_passa_por_float_errado():
    assert decimal_ponto("39800.25") == Decimal("39800.25")
    assert decimal_ponto(0.1) == Decimal("0.1")


def test_documento_fornecedor():
    assert documento_fornecedor("381.942.120/0012-0") == ("38.194.212/0001-20", "cnpj")
    doc, tipo = documento_fornecedor("123.456.789-01")
    assert tipo == "cpf" and doc == "***.456.789-**"
    assert documento_fornecedor("") == (None, "vazio")


CPF_EXEMPLO = "52998224725"  # o CPF de exemplo que circula em documentação; os verificadores fecham
MASCARA = "***.982.247-**"


@pytest.mark.parametrize("bruto, esperado", [
    (f"FULANO DE TAL {CPF_EXEMPLO}", f"FULANO DE TAL {MASCARA}"),
    ("FULANO DE TAL - CPF 529.982.247-25", f"FULANO DE TAL - CPF {MASCARA}"),
    # as formas que a CEAP publica no nome do MEI
    (f"FULANODETAL{CPF_EXEMPLO}", f"FULANODETAL{MASCARA}"),                 # colado ao nome
    (f"Fulano de Tal {CPF_EXEMPLO}Z TUR", f"Fulano de Tal {MASCARA}Z TUR"),  # seguido de letras
    (f"FULANO DE TAL {CPF_EXEMPLO}-ME", f"FULANO DE TAL {MASCARA}-ME"),      # seguido de -ME
    (f"FULANO DE TAL - MEI-{CPF_EXEMPLO}", f"FULANO DE TAL - MEI-{MASCARA}"),  # depois de MEI-
    (CPF_EXEMPLO, MASCARA),                                                  # sozinho
    # o que não é CPF fica
    ("TELEFONE 41999998888", "TELEFONE 41999998888"),          # verificadores não fecham
    (f"1{CPF_EXEMPLO}", f"1{CPF_EXEMPLO}"),                    # 12 dígitos: outro número
    (f"publ/2402/{CPF_EXEMPLO}.pdf", f"publ/2402/{CPF_EXEMPLO}.pdf"),  # caminho de documento
    (f"nota?ideDocumentoFiscal={CPF_EXEMPLO}", f"nota?ideDocumentoFiscal={CPF_EXEMPLO}"),
])
def test_cpf_dentro_do_nome_do_mei_sai_mascarado(bruto, esperado):
    assert mascarar_cpf(bruto) == esperado
    assert cpfs_expostos(esperado) == 0


def test_publicar_recusa_gravar_com_cpf(tmp_path):
    from coleta.destinos.json_plataforma import CpfNaPublicacao, _escrever

    # texto passa pela máscara; um número fora de texto não passa, e a trava pega
    _escrever(tmp_path / "ok.json", {"nome": f"FULANODETAL{CPF_EXEMPLO}"})
    assert CPF_EXEMPLO not in (tmp_path / "ok.json").read_text(encoding="utf-8")
    with pytest.raises(CpfNaPublicacao):
        _escrever(tmp_path / "ruim.json", {"documento": int(CPF_EXEMPLO)})
    assert not (tmp_path / "ruim.json").exists()


def test_normalizar_nome():
    assert normalizar_nome("Carla Cristiana de Carvalho (Carla Pimentel)") == "CARLA CRISTIANA DE CARVALHO"
    assert normalizar_nome("Vereador Jorge Luiz Bernardi") == "JORGE LUIZ BERNARDI"
    assert normalizar_nome("TÂNIA MARA ABRÃO") == "TANIA MARA ABRAO"


def test_guarda_de_privacidade_e_de_para_de_cargo():
    assert eh_cargo_parlamentar("Vereadora") and eh_cargo_parlamentar("PRESIDENTE DA CÂMARA MUNICIPAL")
    assert not eh_cargo_parlamentar("Presidente da Comissão de Licitação")
    assert not eh_cargo_parlamentar("Assessor de Gabinete")
    # o erro de digitação da fonte cai fora da guarda (perde o nome) mas a de-para sabe que é vereadora
    assert not eh_cargo_parlamentar("Veradora") and cargo("cmc_elotech", "Veradora") == "vereador"
    assert cargo("cmc_betha", "Cargo que não existe") is None
    assert categoria("camara_deputados", "PASSAGEM AÉREA - SIGEPA") == ("passagem_aerea", "Passagem aérea")


# ---------------------------------------------------------------- legado (PDF)
@pytest.mark.parametrize("texto,ano,ini,fim", [
    ("16/12/2013", 2013, date(2013, 12, 16), date(2013, 12, 16)),
    ("26/02 a 03/03", 2013, date(2013, 2, 26), date(2013, 3, 3)),
    ("10 a 12/03/2015", 2015, date(2015, 3, 10), date(2015, 3, 12)),
    ("05/12/2016 a\n08/12/2016", 2016, date(2016, 12, 5), date(2016, 12, 8)),
    ("22/06/2015 à 24/06/2015", 2015, date(2015, 6, 22), date(2015, 6, 24)),
    ("18 e 19/11/2013", 2013, date(2013, 11, 18), date(2013, 11, 19)),
    ("05/04/216", 2016, None, None),
])
def test_periodo_nos_quatro_formatos(texto, ano, ini, fim):
    assert ler_periodo(texto, ano) == (ini, fim)


def test_consistencia_de_quantidade_composta():
    assert verificar_consistencia("02 diárias +02 refeições", "R$ 610,00 + R$100,00", Decimal("1420.00")) == "ok"
    assert verificar_consistencia("1+1 refeição", "R$290,00+$100,00", Decimal("390.00")) == "ok"
    assert verificar_consistencia("1+1 refeição", "R$290,00+$200,00", Decimal("390.00")).startswith("diverge")
    assert verificar_consistencia("02 + 02 refeições", "R$ 210,00", Decimal("520.00")).startswith("nao_verificavel")


ESPERADO_LEGADO = {2013: (81, 48, 11), 2014: (47, 18, 11), 2015: (43, 15, 15), 2016: (22, 7, 15)}


@pytest.mark.parametrize("ano", sorted(ESPERADO_LEGADO))
def test_pdf_do_legado(ano):
    rel = ler_pdf((AMOSTRAS / "cmc_legado" / f"Diarias_{ano}.pdf").read_bytes(), ano)
    linhas, parl, colunas = ESPERADO_LEGADO[ano]
    assert len(rel.linhas) == linhas
    assert sum(l.parlamentar for l in rel.linhas) == parl
    assert len(rel.colunas) == colunas
    # servidor nunca sai do parser com nome ou matrícula
    assert all(l.beneficiario is None and l.matricula is None for l in rel.linhas if not l.parlamentar)
    assert all(l.beneficiario for l in rel.linhas if l.parlamentar)


def test_totais_do_pdf_2015_fecham_nas_tres_colunas():
    rel = ler_pdf((AMOSTRAS / "cmc_legado" / "Diarias_2015.pdf").read_bytes(), 2015)
    anual = next(t for t in rel.totais if t.escopo == "2015")
    assert anual.diarias == _soma(l.valor_total for l in rel.linhas) == Decimal("27750.00")
    assert anual.hospedagem == sum(l.hospedagem or 0 for l in rel.linhas) == Decimal("31573.70")
    assert anual.transporte == sum(l.transporte or 0 for l in rel.linhas) == Decimal("47141.68")


def test_total_de_abril_2016_so_fecha_sem_a_linha_devolvida():
    rel = ler_pdf((AMOSTRAS / "cmc_legado" / "Diarias_2016.pdf").read_bytes(), 2016)
    abril = [l for l in rel.linhas if l.competencia_bloco == 4]
    total = next(t for t in rel.totais if t.escopo == "2016-04")
    assert _soma(l.valor_total for l in abril) != total.diarias
    assert _soma(l.valor_total for l in abril if "devolvida" not in l.marcas) == total.diarias == Decimal("140.00")


PDF_SEM_TABELA = b"\n".join([
    b"%PDF-1.4",
    b"1 0 obj <</Type/Catalog/Pages 2 0 R>> endobj",
    b"2 0 obj <</Type/Pages/Kids[3 0 R]/Count 1>> endobj",
    b"3 0 obj <</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>> endobj",
    b"4 0 obj <</Length 44>> stream",
    b"BT /F1 12 Tf 20 100 Td (Sem tabela) Tj ET",
    b"endstream endobj",
    b"5 0 obj <</Type/Font/Subtype/Type1/BaseFont/Helvetica>> endobj",
    b"trailer <</Root 1 0 R>>",
    b"%%EOF",
    b"",
])


def test_pdf_sem_a_tabela_esperada_para_a_fonte():
    # o parser não inventa colunas: sem o cabeçalho de diárias, é portal que mudou
    with pytest.raises(PortalMudou):
        ler_pdf(PDF_SEM_TABELA, 2016)


# ---------------------------------------------------------------- Elotech (API)
def _elotech_res(ano: int) -> Resultado:
    f = CmcElotechAPI()
    item = ItemInventario(chave=f"diarias-{ano}", descricao="", periodo=str(ano), parametros={"ano": ano})
    j = json.loads((AMOSTRAS / "cmc_elotech" / f"diarias_{ano}.json").read_text(encoding="utf-8"))
    out = Resultado()
    for i, x in enumerate(j["content"]):
        d = f._uma_diaria(x, ano, item, f"k{i}", PROC)
        (out.despesas if isinstance(d, Despesa) else out.pendencias).append(d)
    return out


def test_elotech_2018_matricula_no_campo_cargo():
    r = _elotech_res(2018)
    d = next(d for d in r.despesas if d.extra.get("nota_matricula"))
    assert d.ref_parlamentar == "mat:1083" and d.cargo_original == "Vereador"


def test_elotech_2022_viagem_sem_diaria_vale_zero_dito_pela_fonte():
    r = _elotech_res(2022)
    sem = [d for d in r.despesas if d.extra.get("nota_valor")]
    assert sem and all(d.valor == 0 for d in sem)


def test_elotech_2023_cancelada_e_servidor_sem_nome():
    r = _elotech_res(2023)
    assert len(r.despesas) + len(r.pendencias) == 40
    assert any("cancelada" in d.extra["marcas"] for d in r.despesas)
    assert all(d.nome_beneficiario is None for d in r.despesas if d.beneficiario_tipo == "servidor")
    assert all(d.nome_beneficiario for d in r.despesas if d.beneficiario_tipo == "parlamentar" and d.extra["nome_na_fonte"])


# ---------------------------------------------------------------- Prefeitura (HTML)
def _grade_prefeitura() -> list[list[str]]:
    html = (AMOSTRAS / "cmc_prefeitura" / "diarias_2025_pagina1.html").read_text(encoding="utf-8")
    linhas = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        if "grid_Pager" in tr:
            continue
        cel = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)
        linhas.append([re.sub(r"\s+", " ", re.sub(r"<[^>]+>", ".", c)).strip(" .") for c in cel])
    return [l for l in linhas if l]


def test_prefeitura_cabecalho_com_dica_escondida():
    mapa, dados = ler_grade(_grade_prefeitura())
    assert {"doc", "solicitante", "cargo", "inicio", "valor"} <= set(mapa)
    assert len(dados) == 10


def test_prefeitura_linha_de_vereadora_e_de_servidor():
    mapa, dados = ler_grade(_grade_prefeitura())
    f = CmcPrefeitura()
    item = ItemInventario(chave="diarias-2025", descricao="", periodo="2025", parametros={"ano": 2025})
    vistos: dict = {}
    res = [f._linha(c, mapa, 2025, item, vistos, PROC) for c in dados]
    ver = [d for d in res if isinstance(d, Despesa) and d.beneficiario_tipo == "parlamentar"]
    srv = [d for d in res if isinstance(d, Despesa) and d.beneficiario_tipo == "servidor"]
    assert ver and srv
    assert all(d.nome_beneficiario for d in ver)
    # o objetivo cita o nome de quem viajou: em servidor, fica só o destino
    assert all(d.nome_beneficiario is None and "SERVIDOR" not in (d.descricao or "") for d in srv)


def test_prefeitura_linha_de_outro_orgao_e_falha_de_leitura():
    from coleta.fontes.cmc_prefeitura.fonte import conferir_orgao
    from coleta.nucleo.erros import FalhaTransitoria
    mapa, dados = ler_grade(_grade_prefeitura())
    conferir_orgao(dados, mapa, 1)  # a amostra é toda da Câmara
    contaminada = [list(c) for c in dados]
    contaminada[0][mapa["orgao"]] = "SECRETARIA MUNICIPAL DA EDUCAÇÃO.SME"
    with pytest.raises(FalhaTransitoria):
        conferir_orgao(contaminada, mapa, 1)


def test_prefeitura_portal_mudou():
    with pytest.raises(PortalMudou):
        ler_grade([["Coluna nova", "Outra"], ["a", "b"]])


# ---------------------------------------------------------------- Betha (tela)
def test_betha_primeira_pagina_das_diarias():
    html = (AMOSTRAS / "cmc_betha" / "diarias_2026_pagina1.html").read_text(encoding="utf-8")
    achado = re.search(r"bth-powernumber__value[^>]*>\s*(\d+)", html)
    assert achado
    contador = int(achado.group(1))
    assert contador == 54
    cab = [chave_coluna(re.sub(r"<[^>]+>", "", h)) for h in re.findall(r"<th[^>]*>(.*?)</th>", html, re.S)]
    # o rótulo de cada célula é para a versão de celular e fica escondido por CSS;
    # o robô lê innerText, que não inclui o escondido. Aqui, sem CSS, tira-se à mão.
    corpo = re.sub(r'<span[^>]*class="titleTableColumn"[^>]*>.*?</span>', "", html[html.index("<tbody"):], flags=re.S)
    linhas = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", corpo, re.S):
        cel = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cel) >= len(cab) - 1:
            linhas.append({"_pagina": 1, **dict(zip(cab, cel, strict=False))})
    assert len(linhas) == contador  # o robô põe 100 por página: as 54 cabem numa
    f = CmcBetha()
    res = Resultado()
    f.ctx = None
    f._diarias(ItemInventario(chave="diarias-2026", descricao="", periodo="2026"), linhas, [], ["h"], "u", res)
    assert len(res.despesas) + len(res.pendencias) == contador
    nomes_trocados = set(json.loads((AMOSTRAS / "cmc_betha" / "nomes_trocados.json").read_text(encoding="utf-8")))
    for d in res.despesas:
        if d.beneficiario_tipo == "servidor":
            assert d.nome_beneficiario is None
        else:
            assert d.nome_beneficiario and d.nome_beneficiario not in nomes_trocados


# ---------------------------------------------------------------- CEAP (arquivo anual)
def _ceap():
    with zipfile.ZipFile(AMOSTRAS / "camara_deputados" / "Ano-2025-amostra.csv.zip") as z, z.open("Ano-2025.csv") as f:
        linhas = list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", newline=""), delimiter=";"))
    oc: dict = {}
    return [ler_linha_ceap(l, 2025, "ceap-2025", "camara_deputados", PROC, oc) for l in linhas], linhas


def test_ceap_negativos_e_liderancas():
    res, linhas = _ceap()
    assert len(res) == len(linhas)
    desp = [d for d in res if isinstance(d, Despesa)]
    passagens_neg = [d for d in desp if d.categoria_original.startswith("PASSAGEM") and d.valor < 0]
    # compensação de bilhete: líquido e documento negativos (a conferência aceita só esse caso)
    assert any(Decimal(d.extra["valor_documento"]) < 0 for d in passagens_neg)
    aux = [d for d in desp if d.categoria_original.startswith("COMPLEMENTA") and d.valor < 0]
    assert aux and all(Decimal(d.extra["valor_documento"]) > 0 for d in aux)
    assert any(d.beneficiario_tipo == "lideranca" and d.ref_parlamentar is None for d in desp)


def test_ceap_cpf_de_pessoa_fisica_sai_mascarado():
    res, _ = _ceap()
    cpfs = [d for d in res if isinstance(d, Despesa) and d.fornecedor_tipo == "cpf"]
    assert cpfs and all((d.fornecedor_doc or "").startswith("***") for d in cpfs)


def test_ceap_chave_estavel_e_sem_colisao():
    a, _ = _ceap()
    b, _ = _ceap()
    assert [d.chave for d in a] == [d.chave for d in b]
    assert len({d.chave for d in a}) == len(a)


# ---------------------------------------------------------------- TSE
def test_tse_so_vereador_de_curitiba():
    with (AMOSTRAS / "tse" / "consulta_cand_2024_PR_amostra.csv").open(encoding="latin-1", newline="") as f:
        cands, eleitos = ler_candidaturas(f, 2024, lambda loc: PROC)
    assert cands and all(c.municipio == "CURITIBA" for c in cands)
    assert all(c.partido for c in cands)
    assert eleitos <= len(cands)
