"""As assembleias lidas pela tela (AP, CE, TO): os leitores com as amostras de
26/11/2026 e a conferência que manda para a revisão o que a tela não fecha."""

from __future__ import annotations

import json
from decimal import Decimal

from coleta.fontes.alap.fonte import ler_detalhe as ap_detalhe, ler_resultado, opcoes
from coleta.fontes.alece.fonte import assinatura, codigo_do_detalhe, ler_csv, ler_detalhe as ce_detalhe, ler_lista, nome_sem_prefixo
from coleta.fontes.aleto.fonte import conferir_pdf, ler_pdf
from coleta.fontes.assembleia_tela import decodificar, desfazer_dupla_codificacao, separar_partido, titulo_nome
from coleta.nucleo.conferencia import conferir
from coleta.nucleo.texto import cpfs_expostos, documento_fornecedor

from .conftest import AMOSTRAS


def _ler(rel: str) -> str:
    return decodificar((AMOSTRAS / rel).read_bytes())


# ---------------------------------------------------------------- AP
def test_alap_o_mes_tem_elementos_que_somam_o_total_e_o_historico_com_o_complementar():
    pag = ler_resultado(_ler("alap/resultado_2025_09.html"))
    assert pag["mes_ref"] == (2025, 9)
    assert [e["elemento"] for e in pag["elementos"]][:2] == ["3390.30.01", "3390.39.14"]
    soma = sum(Decimal(e["valor_texto"].replace(".", "").replace(",", ".")) for e in pag["elementos"])
    assert soma == pag["total"] == Decimal("50036.00")
    # o POST de setembro já traz o complementar junto: 42.036 + 8.000
    assert pag["historico"][(2025, 9)] == {"regular": Decimal("42036.00"), "complementar": Decimal("8000.00")}
    assert sum(pag["historico"][(2025, 9)].values()) == pag["total"]


def test_alap_detalhe_separa_cnpj_da_razao_social_e_guarda_o_documento_digitalizado():
    det = ap_detalhe(_ler("alap/detalhe_2025_09.html"))
    (n,) = det["notas"]
    assert n["documento"] == "29.892.281/0001-16" and n["fornecedor"] == "A R L EMPREENDIMENTO LTDA"
    assert n["id_item"] == "25266" and n["nf"] == "1383" and det["total"] == Decimal("5000.00")


def test_alap_gabinetes_vem_em_utf8_codificado_duas_vezes_e_o_robo_desfaz():
    bruto = (AMOSTRAS / "alap/gabinetes_ajax.html").read_bytes().decode("utf-8")
    assert "SERRÃ\x83O" in bruto  # como o servidor manda
    rotulos = [r for _, r in opcoes(decodificar((AMOSTRAS / "alap/gabinetes_ajax.html").read_bytes()))]
    assert "ALLINY SERRÃO - UNIÃO" in rotulos
    assert desfazer_dupla_codificacao("Combustíveis") == "Combustíveis"


def test_nome_e_partido_como_a_casa_escreve():
    assert separar_partido("ROBERTO GOES -UNIÃO") == ("ROBERTO GOES", "UNIÃO")
    assert separar_partido("RODOLFO  VALE - PC do B") == ("RODOLFO VALE", "PCdoB")
    assert separar_partido("DR. JACI") == ("DR. JACI", None)
    assert titulo_nome("DR. VICTOR") == "Dr. Victor" and titulo_nome("JOSE DA SILVA") == "Jose da Silva"
    assert titulo_nome("Claudia Lelis") == "Claudia Lelis"


# ---------------------------------------------------------------- CE
def test_alece_a_chave_do_detalhe_e_base64_do_ano_mes_e_nome_exato():
    pag = ler_lista(_ler("alece/lista_2026_09_p1.html"))
    rotulo, codigo = pag["linhas"][0]
    assert rotulo == "DEP AGENOR NETO" and codigo == codigo_do_detalhe(2026, "09", rotulo)
    # o contador da casa diz 30 na página 1, mas a lista mostra 29 (fica como observação)
    assert pag["contador"] == (1, 30, 53) and len(pag["linhas"]) == 29
    assert pag["proxima"] and "page=2" in pag["proxima"]
    # espaço duplo é outra chave: a casa trata como outra entrada
    assert codigo_do_detalhe(2026, "10", "DEP CLAUDIO  PINHO") != codigo_do_detalhe(2026, "10", "DEP CLAUDIO PINHO")
    assert nome_sem_prefixo("DEP CLAUDIO  PINHO") == "CLAUDIO PINHO"


def test_alece_tela_e_csv_trazem_os_mesmos_empenhos_e_o_cpf_sai_mascarado():
    det = ce_detalhe(_ler("alece/detalhe_2026_09.html"))
    csv = ler_csv(_ler("alece/mes_2026_09.csv"))
    soma = sum(Decimal(n["valor_texto"].replace(".", "").replace(",", ".")) for n in det["notas"])
    assert soma == det["total"]
    tela = sorted(assinatura("DEP AGENOR NETO", n["empenho"], n["documento"], n["valor_texto"]) for n in det["notas"])
    do_csv = sorted(assinatura(l["DEPUTADO"], l["EMPENHO"], l["CNPJ"], l["VALOR"]) for l in csv)
    assert tela == do_csv
    # o reembolso ao próprio deputado vem com 11 dígitos na coluna "CNPJ": vira CPF mascarado
    reembolso = next(n for n in det["notas"] if len(n["documento"]) == 11)
    doc, tipo = documento_fornecedor(reembolso["documento"])
    assert tipo == "cpf" and doc is not None and doc.startswith("***") and cpfs_expostos(doc) == 0


# ---------------------------------------------------------------- TO
def test_aleto_o_saldo_de_cada_linha_fecha_pelas_coordenadas_mesmo_com_data_escrita_errado():
    palavras = json.loads((AMOSTRAS / "aleto/pdf_2025_07.json").read_text(encoding="utf-8"))["palavras"]
    pdf = ler_pdf(palavras)
    assert pdf["deputado"] == "CLAUDIA LELIS" and pdf["mes"] == 7
    itens = [n["item"] for n in pdf["notas"]]
    assert 13 not in itens and len(itens) == 41  # a planilha da casa pula o 13
    n29 = next(n for n in pdf["notas"] if n["item"] == 29)
    assert n29["data"] == "0107/2025" and n29["valor_texto"] == "250,00" and n29["saldo_texto"] == "20.583,56"
    fecha, problemas = conferir_pdf(pdf)
    assert fecha, problemas


def test_aleto_uma_nota_a_menos_quebra_a_corrente_do_saldo():
    palavras = json.loads((AMOSTRAS / "aleto/pdf_2025_07.json").read_text(encoding="utf-8"))["palavras"]
    pdf = ler_pdf(palavras)
    pdf["notas"] = [n for n in pdf["notas"] if n["item"] != 20]
    fecha, problemas = conferir_pdf(pdf)
    assert not fecha and any("saldo na linha" in p for p in problemas) and any("total das despesas" in p for p in problemas)


# ---------------------------------------------------------------- conferência
def _nota(con, fonte, chave, casa, ref, valor, extra, categoria, competencia="2026-10"):
    con.execute(
        """INSERT INTO despesas(chave, fonte, item, tipo, ref_parlamentar, beneficiario_tipo, competencia, ano, categoria_original,
             fornecedor_doc, fornecedor_tipo, fornecedor_nome, valor, url, hash_original, coletado_em, extra, casa, granularidade)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (chave, fonte, "i", "verba_estadual", ref, "parlamentar", competencia, 2026, categoria, "11.222.333/0001-81", "cnpj", "EMPRESA X",
         valor, "u", "h", "2026-11-26", json.dumps(extra), casa, "nota"))


def _total(con, fonte, escopo, metrica, valor, texto=None):
    con.execute("INSERT INTO totais_oficiais(fonte, escopo, metrica, valor, texto_original, url, hash_original, coletado_em) VALUES(?,?,?,?,?,?,?,?)",
                (fonte, escopo, metrica, valor, texto, "u", "h", "2026-11-26"))


def test_conferencia_da_tela_manda_para_revisao_o_escopo_que_nao_fecha_e_o_nome_parecido(con):
    cat = "Verba de Desempenho Parlamentar"
    nomes = ("ANTONIO HENRIQUE", "ANTONIO HEMRIQUE", "LIA GOMES", "TIN GOMES", "ALMIR BIE",
             "ALMIR BIE COMBUSTIVEIS E LUBRIFICANTES AUTOMOTIVOS", "PLANO DE SAUDE")
    for n in nomes:
        con.execute("INSERT INTO pessoas_fonte(fonte, ref, periodo, nome, casa, extra) VALUES('alece',?,?,?,'al-ce','{}')",
                    (f"nome:{n}", "2026", n.title()))
    linhas = 0

    def nota(chave, nome, valor="100.00", competencia="2026-10", **extra):
        nonlocal linhas
        linhas += 1
        _nota(con, "alece", chave, "al-ce", f"nome:{nome}", valor, {"escopos_conferencia": [f"{competencia}-DEP {nome}"], **extra}, cat,
              competencia)

    for m in ("2026-08", "2026-09", "2026-10"):  # os deputados de verdade aparecem mês a mês
        nota(f"ah-{m}", "ANTONIO HENRIQUE", competencia=m)
        nota(f"tin-{m}", "TIN GOMES", competencia=m)
        nota(f"lia-{m}", "LIA GOMES", competencia=m)
        nota(f"almir-{m}", "ALMIR BIE", competencia=m)
    nota("c3", "ANTONIO HEMRIQUE", "-20.00", anulacao_explicada=True)
    nota("c4", "LIA GOMES", "50.00")
    nota("c5", "LIA GOMES", "-5.00")
    nota("suf", "ALMIR BIE COMBUSTIVEIS E LUBRIFICANTES AUTOMOTIVOS", "30.00", competencia="2026-02")
    nota("plano", "PLANO DE SAUDE", "10.00")
    con.execute("INSERT INTO inventario(fonte, chave, situacao) VALUES('alece', 'verbas-2026-10', 'ok')")
    _total(con, "alece", "verbas-2026-10", "linhas_na_origem", str(linhas))
    _total(con, "alece", "verbas-2026-10", "escopos_que_fecham", "2/3",
           json.dumps([{"escopo": "2026-10-DEP LIA GOMES", "texto": "TOTAL GERAL 50 × soma 45", "url": "u"}]))
    _total(con, "alece", "verbas-2026-10", "contador_x_lidos", "3/4")
    conferir(con)
    s = {r[0]: (r[1], r[2] or "", r[3]) for r in con.execute("SELECT chave, situacao, motivo, parlamentar_id FROM despesa_situacao")}
    assert s["ah-2026-09"] == ("ok", "", "est-ce-antonio-henrique")
    # dois nomes frequentes a 2 letras um do outro são duas pessoas (Tin Gomes e Lia Gomes)
    assert s["tin-2026-09"] == ("ok", "", "est-ce-tin-gomes") and s["lia-2026-09"][2] == "est-ce-lia-gomes"
    # o nome quase igual e raro, sem linha na tabela de grafias, fica sem identidade e vai para a revisão
    assert s["c3"][0] == "revisao" and "sem identidade" in s["c3"][1] and "anulação de empenho" in s["c3"][1]
    # o sufixo que a fonte colou no nome sai: a nota é do deputado
    assert s["suf"] == ("ok", "", "est-ce-almir-bie")
    assert con.execute("SELECT nome FROM parlamentares WHERE id='est-ce-almir-bie'").fetchone()[0] == "Almir Bie"
    # o nome que aparece uma vez só, sem bater com ninguém, não vira deputado
    assert s["plano"][0] == "revisao"
    # o escopo que não fecha leva as notas dele para a revisão
    assert s["c4"][0] == "revisao" and "não fecha" in s["c4"][1]
    assert s["c5"][0] == "revisao" and "valor negativo" in s["c5"][1]
    conf = {r[0]: (r[1], r[2], r[3]) for r in con.execute(
        "SELECT verificacao, esperado, obtido, resultado FROM conferencias WHERE fonte='alece'")}
    assert conf["soma_das_notas_x_total_da_tela"][2] == "parcial"
    assert conf["contador_da_tela_x_linhas_lidas"][2] == "observacao"
    assert conf["origem_igual_coletado_mais_revisao"] == (str(linhas), str(linhas), "confere")
    motivos = {r[0]: r[1] for r in con.execute("SELECT chave, motivo FROM revisao WHERE fonte='alece' AND tipo='identidade'")}
    assert "ANTONIO HENRIQUE" in motivos["nome:ANTONIO HEMRIQUE"] and "num mês só" in motivos["nome:PLANO DE SAUDE"]
    assert "nome:TIN GOMES" not in motivos


# ---------------------------------------------------------------- BA
def test_alba_lista_paginada_e_detalhe_da_nota():
    from coleta.fontes.alba.fonte import ler_detalhe as ba_detalhe, ler_lista as ba_lista, ultima_pagina

    html = _ler("alba/lista_hassan_2026.html")
    linhas = ba_lista(html)
    assert len(linhas) == 20 and ultima_pagina(html) == 1  # duas páginas: 0 e 1
    l = next(x for x in linhas if x["id"] == "103334")
    assert (l["processo"], l["nf"], l["competencia"], l["valor_texto"]) == ("217140", "3", "11/2026", "R$ 10.000,00")
    (n,) = ba_detalhe(_ler("alba/detalhe_103334.html"))
    assert n["documento"] == "05.087.278/0001-61" and n["valor_texto"] == "R$ 10.000,00" and n["glosa_texto"] == "R$ 0,00"
    assert n["anexo"] and n["anexo"].endswith(".pdf")


def test_alba_a_paginacao_vem_com_amp_no_html():
    from coleta.fontes.alba.fonte import ultima_pagina

    assert ultima_pagina('<a href="?ano=2026&amp;inicio=0&amp;page=176&amp;size=20" title="Última Página">') == 176
    assert ultima_pagina("<p>sem paginação</p>") == 0


# ---------------------------------------------------------------- GO
def test_alego_lancamentos_somam_o_grupo_o_total_e_o_dado_aberto():
    from coleta.fontes.alego.fonte import _dec, ler_exibir, sem_numero

    det = ler_exibir(json.loads((AMOSTRAS / "alego/exibir_808_2026_09.json").read_text(encoding="utf-8")))
    (aberto,) = json.loads((AMOSTRAS / "alego/aberto_2026_09_808.json").read_text(encoding="utf-8"))
    soma = Decimal(0)
    for g in det["grupos"]:
        s = sum((_dec(l["valor_indenizado"]) for l in g["lancamentos"]), Decimal(0))
        assert s == _dec(g["indenizado"]), g["descricao"]
        soma += s
    assert soma == _dec(det["indenizado"]) == _dec(aberto["valor_indenizado"]) == Decimal("26417.08")
    assert sem_numero("02 -  COMUNICAÇÃO, TELEFONE E DADOS") == "COMUNICAÇÃO, TELEFONE E DADOS"


# ---------------------------------------------------------------- PE
def test_alepe_notas_do_pedido_somam_o_total_e_a_rubrica_vem_do_numero_da_categoria():
    pedidos = json.loads((AMOSTRAS / "alepe/pedidos_4508_2025_01.json").read_text(encoding="utf-8"))
    notas = json.loads((AMOSTRAS / f"alepe/notas_{pedidos[0]['docid']}.json").read_text(encoding="utf-8"))
    rubricas = {int(r["numero_categoria"]): r["nome_categoria"] for r in json.loads((AMOSTRAS / "alepe/rubricas_2025.json").read_text(encoding="utf-8"))}
    assert sum(Decimal(n["valor"]) for n in notas) == Decimal(pedidos[0]["total"])
    assert rubricas[int(notas[0]["rubrica"])] == "ASSESSORIA JURÍDICA"


# ---------------------------------------------------------------- RN
def test_alrn_a_linha_da_resposta_e_a_da_tabela_da_tela_sao_a_mesma():
    from coleta.fontes.alrn.fonte import centavos, chave_resposta, chave_tela, ler_despesas

    j = ler_despesas(json.loads((AMOSTRAS / "alrn/despesas_amostra.json").read_text(encoding="utf-8")))
    x = j["data"][0]
    assert chave_resposta(x) == chave_tela("TOMBA FARIAS", "31/07/2025", "35.304.542/0008-09", "R$ 278,46")
    assert centavos(7215827.399999997) == Decimal("7215827.40")
    assert sum(Decimal(l["valor"]) for l in j["data"]) == centavos(j["somatorio"]) and j["count"] == len(j["data"])


def test_aleto_pdf_sem_linha_de_cabecalho_acha_as_colunas_pelas_notas():
    """Fev/2023 vem sem a linha "Item ... Valor Saldo", com "anteriror" e uma observação de combustível deduzido."""
    palavras = json.loads((AMOSTRAS / "aleto/pdf_2023_02_sem_cabecalho.json").read_text(encoding="utf-8"))["palavras"]
    pdf = ler_pdf(palavras)
    assert pdf["mes"] == 2 and len(pdf["notas"]) == 10
    assert pdf["quadro"]["total_despesas"] == Decimal("44978.72") and "saldo_anterior" in pdf["quadro"]
    fecha, problemas = conferir_pdf(pdf)
    assert fecha, problemas
