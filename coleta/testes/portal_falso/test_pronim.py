"""Govbr Pronim sem rede, contra um portal falso local (`pronim_falso`) cuja tabela
mostra o CPF sem máscara, como o de verdade.

O que estes testes provam: o robô lê o documento só na memória e mascara a página
antes de gravar qualquer coisa. Nem o banco, nem o original guardado com hash, nem
a evidência de erro têm CPF, em nenhum dos três jeitos que a tela mostra
(formatado, 11 dígitos colados, sem o zero à esquerda)."""

from __future__ import annotations

from playwright.async_api import async_playwright

from coleta.entidades import EntidadePronim
from coleta.fontes.base import Contexto
from coleta.fontes.pronim.fonte import CARGO_OUTROS, CARGO_PARLAMENTAR, Pronim
from coleta.nucleo import execucao
from coleta.nucleo.banco import conectar
from coleta.nucleo.conferencia import conferir
from coleta.nucleo.texto import cpfs_expostos

from ..apoio.pronim_falso import (
    COLABORADORA,
    CPF_COLABORADORA,
    CPF_PREFEITURA,
    CPF_SERVIDOR,
    CPF_VEREADORA,
    MUNICIPIO,
    PREFEITURA,
    SERVIDOR,
    VEREADORA,
    Portal,
)
from ..apoio.replay_legado import transporte_sem_rede

DOCUMENTOS = [CPF_VEREADORA, CPF_SERVIDOR, CPF_COLABORADORA, CPF_PREFEITURA]


def _digitos(d: str) -> str:
    return "".join(c for c in d if c.isdigit())


def _sem_documento(texto: str, onde) -> None:
    """Nenhum dos três documentos, em nenhum formato, e nenhum CPF pela regra dos verificadores."""
    corrido = texto.replace(".", "").replace("-", "").replace("/", "")
    for d in DOCUMENTOS:
        assert _digitos(d) not in corrido, (onde, "documento inteiro")
    assert cpfs_expostos(texto) == 0, onde


def _ent(base: str) -> EntidadePronim:
    return EntidadePronim(fonte="pronim_teste", casa="cm-vila-exemplo", municipio=MUNICIPIO, ibge=4199999, regiao="Teste",
                          base=base, de=2025, ate=2025)


async def _rodar(dados_tmp, monkeypatch, falhas=None):
    portal = Portal(falhas)
    monkeypatch.setattr(Pronim, "pausa", 0.0)
    con = conectar()
    try:
        async with async_playwright() as pw:
            nav = await pw.chromium.launch()
            f = Pronim(_ent(portal.base))
            await f.abrir(Contexto(con=con, navegador=nav, transporte_http=transporte_sem_rede()))
            try:
                n = await execucao.descobrir(f)
                placar = await execucao.coletar(f)
            finally:
                await f.fechar()
                await nav.close()
    finally:
        portal.fechar()
    return con, n, placar, portal


def _arquivos(dados_tmp):
    return [p for p in dados_tmp.rglob("*") if p.is_file() and p.suffix != ".db" and not p.name.endswith(("-wal", "-shm"))]


# ---------------------------------------------------------------- o robô inteiro
async def test_pronim_mascara_o_cpf_na_memoria_antes_de_gravar_qualquer_coisa(dados_tmp, monkeypatch):
    con, n, placar, portal = await _rodar(dados_tmp, monkeypatch)
    try:
        assert n == 1 and placar.ok == 1 and placar.erro == 0
        assert portal.gerados == 14  # o ano inteiro, os agentes políticos e os 12 meses

        d = [dict(r) for r in con.execute("SELECT * FROM despesas WHERE fonte='pronim_teste' ORDER BY competencia, valor")]
        assert [(x["competencia"], x["valor"], x["beneficiario_tipo"]) for x in d] == [
            ("2025-02", "1694.49", "parlamentar"), ("2025-02", "484.14", "servidor"), ("2025-05", "484.14", "parlamentar"),
            ("2025-09", "0.00", "servidor"), ("2025-11", "121.04", "servidor")]
        assert all(x["granularidade"] == "agregado" for x in d)
        ver = [x for x in d if x["beneficiario_tipo"] == "parlamentar"]
        assert {x["nome_beneficiario"] for x in ver} == {VEREADORA} and {x["cargo_original"] for x in ver} == {CARGO_PARLAMENTAR}
        assert all(x["nome_beneficiario"] is None and x["cargo_original"] == CARGO_OUTROS for x in d if x not in ver)
        t = {r["metrica"]: r for r in con.execute("SELECT * FROM totais_oficiais WHERE fonte='pronim_teste' AND escopo='diarias-2025'")}
        assert t["ano_inteiro_x_mes_a_mes"]["valor"] == "confere" and t["empenhado_no_ano"]["valor"] == "3510.02"

        # o banco inteiro: nenhum documento e nenhum nome de quem não é vereador
        dump = "\n".join(con.iterdump())
        _sem_documento(dump, "banco")
        assert SERVIDOR not in dump and COLABORADORA not in dump
        # a unidade gestora é a da Câmara, não a consolidada (que traz credor da Prefeitura)
        assert "999.99" not in {x["valor"] for x in d} and PREFEITURA not in dump
        # os originais (14 páginas de resultado, com hash) e tudo mais que foi para o disco
        originais = [p for p in _arquivos(dados_tmp) if p.suffix == ".html"]
        assert len(originais) >= 14 and all("omitido pelo rob" in p.read_text(encoding="utf-8") for p in originais if "Valor Empenhado" in p.read_text(encoding="utf-8"))
        for p in _arquivos(dados_tmp):
            _sem_documento(p.read_bytes().decode("latin-1"), p)
        assert not list(dados_tmp.rglob("rastro.zip")) and not list(dados_tmp.rglob("*.webm"))

        conferir(con)
        conf = {r["verificacao"]: r for r in con.execute("SELECT * FROM conferencias WHERE fonte='pronim_teste'")}
        assert conf["origem_igual_coletado_mais_revisao"]["resultado"] == "confere"
        sit = {r["valor"]: r["situacao"] for r in con.execute(
            "SELECT d.valor, s.situacao FROM despesas d JOIN despesa_situacao s USING(chave) WHERE d.fonte='pronim_teste'")}
        assert sit["0.00"] == "fora_da_soma"  # anulado inteiro na fonte
    finally:
        con.close()


async def test_erro_com_o_cpf_na_tela_deixa_evidencia_sem_cpf(dados_tmp, monkeypatch):
    # a tela devolve o resultado com outro período nos "Filtros Utilizados": o robô para (portal mudou)
    # com a tabela, e os CPFs, na tela
    con, _, placar, _ = await _rodar(dados_tmp, monkeypatch, falhas=["periodo_errado"])
    try:
        assert placar.erro == 1 and "outros filtros" in (placar.parou or "")
        ev = con.execute("SELECT evidencia, ultimo_erro FROM inventario WHERE fonte='pronim_teste'").fetchone()
        pasta = dados_tmp / ev["evidencia"]
        assert (pasta / "tela.png").exists() and (pasta / "pagina.html").exists()
        _sem_documento(ev["ultimo_erro"], "mensagem de erro")
        for p in _arquivos(dados_tmp):
            _sem_documento(p.read_bytes().decode("latin-1"), p)
        assert "omitido pelo rob" in (pasta / "pagina.html").read_text(encoding="utf-8")
    finally:
        con.close()
