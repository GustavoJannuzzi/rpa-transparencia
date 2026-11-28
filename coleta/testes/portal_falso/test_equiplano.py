"""Equiplano sem rede: o robô de tela inteiro contra um portal falso local
(`equiplano_falso`) que devolve CPF e RG inteiros, com falhas injetadas."""

from __future__ import annotations

from playwright.async_api import async_playwright

from coleta.entidades import EntidadeEquiplano
from coleta.fontes.base import Contexto
from coleta.fontes.equiplano.fonte import Equiplano
from coleta.nucleo import execucao
from coleta.nucleo.banco import conectar
from coleta.nucleo.conferencia import conferir
from coleta.nucleo.texto import cpfs_expostos

from ..apoio.equiplano_falso import CPF_SERVIDORA, CPF_SOLTO, CPF_VEREADORA, ENTIDADE, MUNICIPIO, NOME_SERVIDORA, NOME_VEREADORA, Portal
from ..apoio.replay_legado import transporte_sem_rede


def _so_digitos(cpf: str) -> str:
    return "".join(c for c in cpf if c.isdigit())


def _ent(host: str = "http://127.0.0.1:1") -> EntidadeEquiplano:
    return EntidadeEquiplano(fonte="equiplano_teste", casa="cm-vila-exemplo", municipio=MUNICIPIO, ibge=4199999, regiao="Teste",
                             host=host, entidade=ENTIDADE, de=2024, ate=2025)


# ---------------------------------------------------------------- o robô inteiro, no navegador
async def test_equiplano_ponta_a_ponta_com_falhas_e_sem_cpf_gravado(dados_tmp, monkeypatch):
    # a primeira chamada ao AJAX (no descobrir) passa; a segunda dá 500; a recarga perde a entidade uma vez
    portal = Portal({"ajax": ["", "500"], "recarga": ["perde_entidade"]})
    monkeypatch.setattr(Equiplano, "pausa", 0.0)
    con = conectar()
    try:
        async with async_playwright() as pw:
            nav = await pw.chromium.launch()
            f = Equiplano(_ent(portal.host))
            await f.abrir(Contexto(con=con, navegador=nav, transporte_http=transporte_sem_rede()))
            try:
                n = await execucao.descobrir(f)
                placar = await execucao.coletar(f)
            finally:
                await f.fechar()
                await nav.close()
        assert n == 2
        assert placar.ok == 2 and placar.erro == 0 and placar.tentativas_extras == 2

        d = {r["valor"]: r for r in con.execute("SELECT * FROM despesas WHERE fonte='equiplano_teste'")}
        assert set(d) == {"1694.49", "484.14", "0.00"}
        assert d["1694.49"]["nome_beneficiario"] == NOME_VEREADORA and d["484.14"]["nome_beneficiario"] is None
        vazio = con.execute("SELECT valor, texto_original FROM totais_oficiais WHERE escopo='diarias-2024' AND metrica='registros'").fetchone()
        assert vazio["valor"] == "0" and "Não houve concessão" in vazio["texto_original"]

        # nada gravado tem CPF: nem o banco, nem o original, nem a evidência das falhas
        dump = "\n".join(con.iterdump())
        assert cpfs_expostos(dump) == 0 and NOME_SERVIDORA not in dump
        for cpf in (CPF_VEREADORA, CPF_SERVIDORA, CPF_SOLTO):
            assert _so_digitos(cpf) not in dump
        arquivos = [p for p in dados_tmp.rglob("*") if p.is_file() and p.suffix != ".db" and "-wal" not in p.name and "-shm" not in p.name]
        assert any(p.suffix == ".csv" for p in arquivos)
        for p in arquivos:
            texto = p.read_bytes().decode("latin-1")
            assert cpfs_expostos(texto) == 0, p
            assert not any(_so_digitos(c) in texto.replace(".", "").replace("-", "") for c in (CPF_VEREADORA, CPF_SERVIDORA)), p
        assert not list(dados_tmp.rglob("rastro.zip"))  # o rastro do Playwright guardaria a resposta inteira

        # a conferência fecha a conta do papel
        conferir(con)
        conf = {(r["verificacao"], r["escopo"]): r for r in con.execute("SELECT * FROM conferencias WHERE fonte='equiplano_teste'")}
        assert conf[("origem_igual_coletado_mais_revisao", "todas as linhas")]["resultado"] == "confere"
        assert conf[("total_do_relatorio", "diarias-2025")]["obtido"] == "2178.63"
        assert conf[("total_do_relatorio", "diarias-2025")]["resultado"] == "confere"
        sit = {r["valor"]: r["situacao"] for r in con.execute(
            "SELECT d.valor, s.situacao FROM despesas d JOIN despesa_situacao s USING(chave) WHERE d.fonte='equiplano_teste'")}
        assert sit["0.00"] == "fora_da_soma"  # estornado inteiro
    finally:
        con.close()
        portal.fechar()
