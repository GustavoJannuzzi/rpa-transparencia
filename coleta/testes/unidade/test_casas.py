"""As fontes novas, nas amostras anonimizadas de 26/11/2026: o adaptador genérico do
Elotech (Maringá), a CLDF (CSV e planilha), a API da ALMG e o arquivo da ALESP. Mais a
pausa que vem do robots.txt e as regras da conferência que valem para casa nova."""

from __future__ import annotations

import io
import json
from decimal import Decimal

import httpx
import pytest

from coleta import entidades
from coleta.de_para import cargo, eh_cargo_parlamentar
from coleta.fontes import FONTES
from coleta.fontes.alesp.fonte import registros
from coleta.fontes.almg.fonte import conferir_formato_mes
from coleta.fontes.cldf.fonte import formato_do_arquivo, ler_arquivo, ler_data, ler_valor, linha_deslocada
from coleta.fontes.elotech.fonte import ElotechAPI
from coleta.modelo import Despesa, ItemInventario, Procedencia
from coleta.nucleo.conferencia import conferir
from coleta.nucleo.educacao import Educacao
from coleta.nucleo.erros import PortalMudou
from coleta.nucleo.texto import documento_de_numero

from ..conftest import AMOSTRAS

PROC = Procedencia(fonte="t", url="u", hash_original="h", coletado_em="2026-11-26")
MARINGA = next(e for e in entidades.elotech() if e.fonte == "elotech_maringa")


def _json(rel: str):
    return json.loads((AMOSTRAS / rel).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- configuração
def test_toda_entidade_tem_fonte_casa_e_id_que_a_plataforma_aceita():
    import re

    ids = [f.id for f in FONTES]
    assert len(ids) == len(set(ids))
    # a plataforma confere data-fonte com [a-z_ ]: id de fonte sem número nem hífen
    assert all(re.fullmatch(r"[a-z_]+", i) for i in ids), ids
    casas = entidades.casas()
    assert all(f.sistema.casa in casas for f in FONTES)
    ufs = {c.uf for c in casas.values() if c.tipo == "assembleia"}
    assert {"DF", "MG", "SP", "AP", "CE", "TO"} <= ufs
    # toda assembleia coletada tem a sua linha no levantamento das 27 (é de lá que vem a Cobertura)
    from coleta.destinos.cobertura import _ler_csv

    assert ufs <= {l["uf"] for l in _ler_csv("assembleias.csv")}
    # Curitiba, 12 no Elotech, 13 no Betha, 10 no Equiplano e 6 no Pronim
    assert sum(1 for c in casas.values() if c.tipo == "camara_municipal") == 1 + 12 + 13 + 10 + 6


def test_o_endereco_mostrado_e_uma_pagina_e_nao_a_raiz_de_uma_api():
    import re

    # a raiz da API da ALMG (/api/v2) responde 404 a quem clica: a plataforma mostra a documentação
    raizes = [f.id for f in FONTES if re.search(r"/api(/v\d+)?/?$", f.sistema.endereco)]
    assert raizes == []
    assert next(f for f in FONTES if f.id == "almg").sistema.endereco == "https://dadosabertos.almg.gov.br/documentacao/index"


# ---------------------------------------------------------------- robots.txt
async def test_a_pausa_vem_do_crawl_delay_do_robots_com_piso():
    def responder(req: httpx.Request) -> httpx.Response:
        if req.url.host == "lento.example":
            return httpx.Response(200, text="User-agent: *\nDisallow: /api/\nCrawl-Delay: 10\n", headers={"content-type": "text/plain"})
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as c:
        ed = Educacao(pausa=1.0)
        await ed.verificar_robots("https://lento.example/dataset/x", c)
        await ed.verificar_robots("https://rapido.example/x", c)
        assert ed.pausa_de("https://lento.example/qualquer") == 10.0
        assert ed.pausa_de("https://rapido.example/x") == 1.0  # sem robots: vale o piso
        assert "Crawl-delay de 10 s" in ed.politicas["https://lento.example"]
        with pytest.raises(Exception, match="robots"):
            await ed.verificar_robots("https://lento.example/api/action", c)


# ---------------------------------------------------------------- Elotech genérico
def test_cargo_de_parlamentar_em_varias_grafias_e_servidor_por_regra():
    assert eh_cargo_parlamentar("Presidente Da Camara") and eh_cargo_parlamentar("PRESIDENTE CAMARA")
    assert not eh_cargo_parlamentar("Presidente da Comissão de Licitação")
    # fonte sem tabela revisada: cargo comum é servidor; o que parece vereador vai para revisão
    assert cargo("elotech_maringa", "Motorista da Câmara Municipal de Maringá") == "servidor"
    assert cargo("elotech_maringa", "Veriador") is None and cargo("elotech_maringa", "") is None
    # as fontes de Curitiba continuam só com a tabela
    assert cargo("cmc_elotech", "Motorista da Câmara Municipal de Maringá") is None


def test_diaria_sem_cargo_so_guarda_nome_de_quem_esta_no_cadastro_de_vereadores():
    f = ElotechAPI(MARINGA)
    serv = _json("elotech/maringa_servidores_2025.json")["content"]
    from coleta.fontes.elotech.fonte import eh_natureza_parlamentar
    from coleta.nucleo.texto import normalizar_nome

    vereadores = {normalizar_nome(x["nome"]) for x in serv if eh_natureza_parlamentar(x["descricaoNatureza"])}
    item = ItemInventario(chave="diarias-2025", descricao="", periodo="2025", parametros={"ano": 2025})
    out = [f._uma_diaria(x, 2025, item, f"k{i}", PROC, vereadores) for i, x in enumerate(_json("elotech/maringa_diarias_2025.json")["content"])]
    despesas = [d for d in out if isinstance(d, Despesa)]
    assert len(out) == 41
    casadas = [d for d in despesas if d.extra.get("nota_cargo")]
    assert casadas and all(d.beneficiario_tipo == "parlamentar" and d.nome_beneficiario for d in casadas)
    sem_cargo = [d for d in despesas if d.extra["cargo_vazio"] and not d.extra.get("nota_cargo")]
    assert sem_cargo and all(d.nome_beneficiario is None and d.beneficiario_tipo == "servidor" for d in sem_cargo)
    assert all(d.casa == "cm-maringa" and d.documento_url.endswith("/diarias") for d in despesas)  # type: ignore[union-attr]
    # o motivo da viagem (texto livre) não vai para a descrição fora de Curitiba
    assert not any("omitido" in (d.descricao or "") for d in despesas)


# ---------------------------------------------------------------- CLDF
def test_cldf_le_csv_e_planilha_com_cabecalhos_diferentes():
    csv_ = ler_arquivo(AMOSTRAS / "cldf" / "verbas_2023_amostra.csv", "csv")
    xlsx = ler_arquivo(AMOSTRAS / "cldf" / "verbas_2025_amostra.xlsx", "xlsx")
    for linhas in (csv_, xlsx):
        assert {"parlamentar", "cpf_parlamentar", "data", "valor", "categoria", "cnpj"} <= set(linhas[0])
    # o CNPJ gravado como número na planilha volta com os 14 dígitos, conferidos
    assert csv_[0]["cnpj"] == "13347016000117" and "sem o '.0'" in (csv_[0]["nota_documento"] or "")
    assert formato_do_arquivo([l["data"] or "" for l in xlsx]) == "misto"
    assert sum(1 for l in xlsx if linha_deslocada(l)) == 2


@pytest.mark.parametrize(("texto", "formato", "esperado"), [
    ("2023-05-02 00:00:00", "sem_prova", "2023-05-02"),
    ("45301.0", "sem_prova", "2024-01-10"),
    ("1/16/2025", "misto", "2025-01-16"),
    ("21/03/2025", "misto", "2025-03-21"),
    ("01/04/2026", "dia_mes", "2026-04-01"),
    ("09 de março de 2023", "sem_prova", "2023-03-09"),
])
def test_cldf_data_so_quando_inequivoca(texto, formato, esperado):
    assert ler_data(texto, formato).isoformat() == esperado


@pytest.mark.parametrize("texto", ["3/4/2025", "30/092023", "29/08/205", ""])
def test_cldf_data_ambigua_ou_ilegivel_nao_e_chutada(texto):
    with pytest.raises(ValueError):
        ler_data(texto, "misto")


def test_cldf_valor_nos_formatos_da_fonte():
    assert ler_valor("R$ 5.600,00")[0] == Decimal("5600.00")
    assert ler_valor("173,07")[0] == Decimal("173.07")
    assert ler_valor("500.0")[0] == Decimal("500.0")
    v, nota = ler_valor("1261.8399999999999")
    assert v == Decimal("1261.84") and nota


def test_documento_gravado_como_numero_so_volta_quando_os_digitos_fecham():
    assert documento_de_numero("82024000137.0")[0] == "00082024000137"  # CNPJ que começa com 000
    assert documento_de_numero("2558157000162")[0] == "02558157000162"
    assert documento_de_numero("02.558.157/0001-62")[0] == "02.558.157/0001-62"  # texto fica como veio
    assert documento_de_numero("123.0")[1] and documento_de_numero("123.0")[0] == "123"


# ---------------------------------------------------------------- ALMG
def test_almg_a_soma_das_notas_fecha_com_o_total_de_cada_tipo():
    tipos = conferir_formato_mes(_json("almg/verba_mes.json"))
    for t in tipos:
        assert sum(Decimal(str(n["valorReembolsado"])) for n in t["listaDetalheVerba"]) == Decimal(str(t["valor"]))


def test_almg_formato_mudou_para_a_coleta():
    with pytest.raises(PortalMudou):
        conferir_formato_mes({"list": [{"codTipoDespesa": 1, "valor": 1}]})


# ---------------------------------------------------------------- ALESP
def test_alesp_le_em_fluxo_com_buffer_pequeno_e_valor_exato():
    texto = (AMOSTRAS / "alesp" / "despesas_amostra.json").read_text(encoding="utf-8")
    regs = list(registros(io.StringIO(texto)))
    # número com casas decimais vira Decimal exato na leitura (nunca float); inteiro fica inteiro
    assert len(regs) == 24 and all(isinstance(x["valor"], (Decimal, int)) for x in regs)
    assert any(isinstance(x["valor"], Decimal) for x in regs)


# ---------------------------------------------------------------- conferência de casa nova
def _despesa(con, fonte, chave, *, tipo, casa, categoria, valor="100.00", ref="id:1", granularidade="nota", extra=None, cargo_=None,
             tipo_b="parlamentar", fornecedor="EMPRESA X LTDA"):
    con.execute(
        """INSERT INTO despesas(chave, fonte, item, tipo, ref_parlamentar, beneficiario_tipo, cargo_original, competencia, ano,
             categoria_original, fornecedor_doc, fornecedor_tipo, fornecedor_nome, valor, url, hash_original, coletado_em, extra, casa,
             granularidade) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (chave, fonte, "i", tipo, ref, tipo_b, cargo_, "2025-09", 2025, categoria, "11.222.333/0001-81", "cnpj", fornecedor, valor,
         "u", "h", "2026-11-26", json.dumps(extra or {}), casa, granularidade))


def test_conferencia_de_assembleia_e_de_camara_nova(con):
    con.execute("INSERT INTO pessoas_fonte(fonte, ref, periodo, nome, partido, casa, extra) VALUES('almg','id:1','2025','Fulana','PV','al-mg','{}')")
    con.execute("INSERT INTO pessoas_fonte(fonte, ref, periodo, nome, casa, extra) VALUES('alesp','mat:1','2023-2026','Ciclano','al-sp','{}')")
    con.execute("INSERT INTO pessoas_fonte(fonte, ref, periodo, nome, casa, extra) VALUES('cldf','nome:X','2023-2026','X','al-df','{}')")
    _despesa(con, "almg", "a1", tipo="verba_estadual", casa="al-mg", categoria="Combustível e lubrificante")
    _despesa(con, "almg", "a2", tipo="verba_estadual", casa="al-mg", categoria="Combustível e lubrificante", valor="0")
    _despesa(con, "alesp", "s1", tipo="verba_estadual", casa="al-sp", categoria="A - COMBUSTÍVEIS E LUBRIFICANTES", ref="mat:1", granularidade="agregado")
    _despesa(con, "cldf", "d1", tipo="verba_estadual", casa="al-df", categoria="", ref="nome:X")
    _despesa(con, "cldf", "d2", tipo="verba_estadual", casa="al-df", categoria="Combustível", ref="nome:X",
             extra={"fora_do_outro_arquivo": "Verbas 2023 (xlsx)"})
    _despesa(con, "elotech_maringa", "m1", tipo="diaria_municipal", casa="cm-maringa", categoria="Diária", ref=None, cargo_="",
             tipo_b="servidor", extra={"cargo_vazio": True, "consistencia": "ok"})
    _despesa(con, "elotech_maringa", "m2", tipo="diaria_municipal", casa="cm-maringa", categoria="Diária", ref=None, cargo_="Motorista",
             tipo_b="servidor", extra={"consistencia": "ok"})
    # cargo vazio, mas o nome está no cadastro de vereadores do ano: é vereador
    con.execute("INSERT INTO pessoas_fonte(fonte, ref, periodo, nome, casa, extra) VALUES('elotech_maringa','nome:BELTRANO','2025','BELTRANO','cm-maringa','{}')")
    _despesa(con, "elotech_maringa", "m3", tipo="diaria_municipal", casa="cm-maringa", categoria="Diária", ref="nome:BELTRANO", cargo_="",
             extra={"cargo_vazio": True, "nota_cargo": "cargo vazio na fonte; o nome é o de um vereador", "consistencia": "ok"})
    for f in ("almg", "alesp", "cldf", "elotech_maringa"):
        con.execute("INSERT INTO inventario(fonte, chave, situacao) VALUES(?, 'i', 'ok')", (f,))
    conferir(con)
    s = {r[0]: (r[1], r[2] or "", r[3]) for r in con.execute("SELECT chave, situacao, motivo, parlamentar_id FROM despesa_situacao")}
    assert s["a1"][0] == "ok" and s["a1"][2] == "est-mg-1"
    assert s["a2"][0] == "fora_da_soma" and "reembolsado zero" in s["a2"][1]
    assert s["s1"][0] == "ok" and s["s1"][2] == "est-sp-1"
    assert s["d1"][0] == "revisao" and "classificação vazia" in s["d1"][1]
    assert s["d2"][0] == "revisao" and "também publica" in s["d2"][1]
    assert s["m1"][0] == "revisao" and "não informa o cargo" in s["m1"][1]
    assert s["m2"][0] == "ok"  # servidor por regra: entra só na soma, sem nome
    assert s["m3"][0] == "ok" and s["m3"][2] == "ver-maringa-beltrano"
    partido = con.execute("SELECT partido_atual FROM parlamentares WHERE id='est-mg-1'").fetchone()[0]
    assert partido == "PV"


def test_ano_em_revisao_de_um_portal_so_vale_para_a_casa_dele():
    """A divergência do portal da Prefeitura de Curitiba em 2024 e 2025 aparecia como
    "em revisão" na página de vereadores de outras 38 câmaras."""
    from coleta.destinos.json_plataforma import _periodos_em_revisao

    anos_rev = {"cmc_prefeitura": [2024, 2025], "pronim_salto_do_lontra": [2023]}
    mandato = [2021, 2022, 2023, 2024, 2025, 2026]
    assert _periodos_em_revisao("cmc", mandato, anos_rev) == [
        {"fonte": "cmc_prefeitura", "anos": [2024, 2025], "motivo": "consulta_prefeitura"}]
    assert _periodos_em_revisao("cm-salto-do-lontra", mandato, anos_rev) == [
        {"fonte": "pronim_salto_do_lontra", "anos": [2023], "motivo": "consulta_prefeitura"}]
    assert _periodos_em_revisao("cm-maringa", mandato, anos_rev) == []
    # só os anos do mandato contam
    assert _periodos_em_revisao("cmc", [2026], anos_rev) == []
