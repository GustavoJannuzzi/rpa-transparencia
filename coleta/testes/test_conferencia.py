"""Conferência: casos montados que têm de cair na revisão (ou passar)."""

from __future__ import annotations

import json

from coleta.nucleo.conferencia import conferir

N = 0


def despesa(con, fonte, *, valor, ano=2016, comp="2016-05", ref=None, tipo_b="parlamentar", cargo="Vereador",
            categoria="Diária", extra=None, data=None, nome=None, fornecedor="EMPRESA X LTDA", forn_doc=None, item=None):
    global N
    N += 1
    chave = f"k{N}"
    con.execute(
        """INSERT INTO despesas(chave, fonte, item, tipo, ref_parlamentar, beneficiario_tipo, nome_beneficiario, cargo_original,
             data, competencia, ano, categoria_original, fornecedor_doc, fornecedor_tipo, fornecedor_nome, valor, url, hash_original,
             coletado_em, extra) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (chave, fonte, item or f"i-{ano}", "cota_federal" if fonte == "camara_deputados" else "diaria_municipal", ref, tipo_b,
         nome, cargo if fonte != "camara_deputados" else None, data, comp, ano, categoria, forn_doc,
         "cnpj" if forn_doc else None, fornecedor if fonte == "camara_deputados" else None, valor, "u", "h", "2026-11-25",
         json.dumps(extra or {})),
    )
    return chave


def total(con, fonte, escopo, metrica, valor):
    con.execute("INSERT OR REPLACE INTO totais_oficiais(fonte, escopo, metrica, valor) VALUES(?,?,?,?)", (fonte, escopo, metrica, str(valor)))


def pessoa(con, fonte, ref, nome, mat=None, periodo="2016"):
    con.execute("INSERT OR REPLACE INTO pessoas_fonte(fonte, ref, periodo, nome, matricula, casa) VALUES(?,?,?,?,?,?)",
                (fonte, ref, periodo, nome, mat, "cmc"))


def inventario(con, fonte, chave="i"):
    con.execute("INSERT OR IGNORE INTO inventario(fonte, chave, situacao) VALUES(?,?,'ok')", (fonte, chave))


def situacao(con, chave):
    return con.execute("SELECT situacao, motivo FROM despesa_situacao WHERE chave=?", (chave,)).fetchone()


def test_total_do_mes_que_nao_fecha_manda_o_mes_para_revisao(con):
    pessoa(con, "cmc_legado", "mat:1", "FULANO DE TAL", "1")
    bloco = {"competencia_do_bloco": True, "consistencia": "ok", "marcas": []}
    a = despesa(con, "cmc_legado", valor="100.00", ref="mat:1", nome="Fulano de Tal", extra=bloco)
    b = despesa(con, "cmc_legado", valor="50.00", tipo_b="servidor", cargo="Técnico Administrativo", extra=bloco)
    total(con, "cmc_legado", "2016-05", "valor_diarias", "200.00")
    inventario(con, "cmc_legado")
    conferir(con)
    assert situacao(con, a)["situacao"] == "revisao" and situacao(con, b)["situacao"] == "revisao"
    assert con.execute("SELECT COUNT(*) FROM revisao WHERE tipo='total' AND chave='2016-05'").fetchone()[0] == 1


def test_linha_devolvida_que_a_propria_fonte_nao_soma_fica_fora_da_soma(con):
    pessoa(con, "cmc_legado", "mat:1", "FULANO DE TAL", "1")
    a = despesa(con, "cmc_legado", valor="140.00", comp="2016-04", ref="mat:1", nome="Fulano",
                extra={"competencia_do_bloco": True, "consistencia": "ok", "marcas": []})
    b = despesa(con, "cmc_legado", valor="200.00", comp="2016-04", ref="mat:1", nome="Fulano",
                extra={"competencia_do_bloco": True, "consistencia": "ok", "marcas": ["devolvida"]})
    total(con, "cmc_legado", "2016-04", "valor_diarias", "140.00")
    inventario(con, "cmc_legado")
    conferir(con)
    assert situacao(con, a)["situacao"] == "ok"
    assert situacao(con, b)["situacao"] == "fora_da_soma"


def test_linha_que_nao_fecha_vai_para_revisao_mesmo_com_total_certo(con):
    pessoa(con, "cmc_legado", "mat:1", "FULANO DE TAL", "1")
    a = despesa(con, "cmc_legado", valor="390.00", ref="mat:1", nome="Fulano",
                extra={"competencia_do_bloco": True, "consistencia": "diverge: 1 × 290 + 1 × 200 = 490", "marcas": []})
    total(con, "cmc_legado", "2016-05", "valor_diarias", "390.00")
    inventario(con, "cmc_legado")
    conferir(con)
    assert situacao(con, a)["situacao"] == "revisao"


def test_categoria_sem_de_para_e_negativos(con):
    con.execute("INSERT INTO pessoas_fonte(fonte, ref, periodo, nome, partido, uf, casa) VALUES('camara_deputados','10','57:XYZ','Dep A','XYZ','PR','camara-deputados')")
    nova = despesa(con, "camara_deputados", valor="10.00", ano=2025, comp="2025-01", ref="10", categoria="CATEGORIA QUE NÃO EXISTIA",
                   extra={"ano_arquivo": 2025, "valor_documento": "10.00"})
    compensa = despesa(con, "camara_deputados", valor="-500.00", ano=2025, comp="2025-01", ref="10", categoria="PASSAGEM AÉREA - SIGEPA",
                       extra={"ano_arquivo": 2025, "valor_documento": "-500.00"})
    sem_explicacao = despesa(con, "camara_deputados", valor="-247", ano=2025, comp="2025-01", ref="10",
                             categoria="COMPLEMENTAÇÃO DO AUXÍLIO-MORADIA", extra={"ano_arquivo": 2025, "valor_documento": "247"})
    sem_fornecedor = despesa(con, "camara_deputados", valor="20.00", ano=2025, comp="2025-01", ref="10", categoria="TELEFONIA",
                             fornecedor="", extra={"ano_arquivo": 2025, "valor_documento": "20.00"})
    inventario(con, "camara_deputados")
    conferir(con)
    assert situacao(con, nova)["situacao"] == "revisao" and "de-para" in situacao(con, nova)["motivo"]
    assert situacao(con, compensa)["situacao"] == "ok"
    assert situacao(con, sem_explicacao)["situacao"] == "revisao"
    assert situacao(con, sem_fornecedor)["situacao"] == "revisao"


def test_mesmo_registro_na_fronteira_entre_dois_sistemas(con):
    pessoa(con, "cmc_prefeitura", "mat:7", "CICLANA DA SILVA", "7", "2026")
    pessoa(con, "cmc_betha", "nome:CICLANA DA SILVA", "CICLANA DA SILVA", None, "2026")
    betha = despesa(con, "cmc_betha", valor="580.00", ano=2026, comp="2026-03", ref="nome:CICLANA DA SILVA", nome="CICLANA DA SILVA",
                    cargo="VEREADORA", data="2026-03-10")
    igual = despesa(con, "cmc_prefeitura", valor="580.00", ano=2026, comp="2026-03", ref="mat:7", nome="CICLANA DA SILVA",
                    cargo="Vereadora", data="2026-03-10", categoria="Diárias")
    so_aqui = despesa(con, "cmc_prefeitura", valor="300.00", ano=2026, comp="2026-04", ref="mat:7", nome="CICLANA DA SILVA",
                      cargo="Vereadora", data="2026-04-02", categoria="Diárias")
    inventario(con, "cmc_prefeitura")
    inventario(con, "cmc_betha")
    conferir(con)
    # 2026 é do Betha: a linha da Prefeitura não é publicada de novo, serve para conferir
    assert situacao(con, igual)["situacao"] == "conferencia_cruzada"
    assert situacao(con, betha)["situacao"] == "ok"
    assert con.execute("SELECT COUNT(*) FROM revisao WHERE tipo='fronteira' AND chave=?", (so_aqui,)).fetchone()[0] == 1
    conf = con.execute("SELECT obtido FROM conferencias WHERE verificacao='fronteira_betha_2026'").fetchone()[0]
    assert conf.startswith("1 com par")


def test_cargo_de_vereador_fora_da_guarda_de_privacidade(con):
    a = despesa(con, "cmc_elotech", valor="100.00", ano=2021, comp="2021-05", tipo_b="servidor", cargo="Veradora",
                extra={"consistencia": "ok", "marcas": [], "quantidade": 1})
    inventario(con, "cmc_elotech")
    conferir(con)
    s = situacao(con, a)
    assert s["situacao"] == "revisao" and "guarda de privacidade" in s["motivo"]


def test_equacao_origem_igual_coletado_mais_revisao(con):
    pessoa(con, "cmc_betha", "nome:CICLANA DA SILVA", "CICLANA DA SILVA", None, "2026")
    for _ in range(3):
        despesa(con, "cmc_betha", valor="10.00", ano=2026, comp="2026-01", ref="nome:CICLANA DA SILVA", nome="Ciclana", cargo="VEREADORA", data="2026-01-05")
    total(con, "cmc_betha", "diarias-2026", "registros", 4)  # a fonte diz 4, o robô gravou 3
    inventario(con, "cmc_betha")
    conferir(con)
    r = con.execute("SELECT esperado, obtido, resultado FROM conferencias WHERE fonte='cmc_betha' AND verificacao='origem_igual_coletado_mais_revisao'").fetchone()
    assert (r["esperado"], r["obtido"], r["resultado"]) == ("4", "3", "diverge")


def test_ano_em_que_os_dois_caminhos_de_consulta_divergem_vai_para_revisao(con):
    pessoa(con, "cmc_prefeitura", "mat:7", "CICLANA DA SILVA", "7", "2025")
    a = despesa(con, "cmc_prefeitura", valor="300.00", ano=2025, comp="2025-04", ref="mat:7", nome="CICLANA DA SILVA",
                cargo="Vereadora", data="2025-04-02", categoria="Diárias")
    b = despesa(con, "cmc_prefeitura", valor="200.00", ano=2024, comp="2024-04", ref="mat:7", nome="CICLANA DA SILVA",
                cargo="Vereadora", data="2024-04-02", categoria="Diárias")
    total(con, "cmc_prefeitura", "diarias-2025", "ano_inteiro_x_mes_a_mes", "diverge")
    total(con, "cmc_prefeitura", "diarias-2024", "ano_inteiro_x_mes_a_mes", "confere")
    inventario(con, "cmc_prefeitura")
    conferir(con)
    assert situacao(con, a)["situacao"] == "revisao"
    assert situacao(con, b)["situacao"] == "ok"
    assert con.execute("SELECT COUNT(*) FROM revisao WHERE tipo='consulta' AND chave='diarias-2025'").fetchone()[0] == 1
