"""Contrato: um teste por fonte contra o portal de verdade. Avisa quando o layout
mudou. Separado dos testes normais: python -m pytest -m contrato"""

from __future__ import annotations

import httpx
import pytest
from playwright.async_api import async_playwright

from coleta import config
from coleta.fontes.camara_deputados.fonte import API, ARQUIVO, COLUNAS as COLUNAS_CEAP
from coleta.fontes.cmc_betha.fonte import CONSULTAS, PORTAL, chave_coluna
from coleta.fontes.cmc_elotech.fonte import API as ELO, CAMPOS_DIARIA, CAMPOS_SERVIDOR
from coleta.fontes.cmc_legado.fonte import INICIO, MENU, RE_BOTAO
from coleta.fontes.cmc_prefeitura.fonte import ORGAO, SEL, URL as PMC, ler_grade
from coleta.fontes.tse.fonte import URL as TSE

pytestmark = pytest.mark.contrato
H = {"User-Agent": config.UA_ROBO}


def test_camara_api_e_arquivo():
    with httpx.Client(headers=H, timeout=60, follow_redirects=True) as c:
        d = c.get(f"{API}/deputados?idLegislatura=57&itens=2", headers={**H, "Accept": "application/json"}).json()["dados"]
        assert {"id", "nome", "siglaPartido", "siglaUf"} <= set(d[0])
        r = c.head(ARQUIVO.format(ano=2025))
        assert r.status_code == 200 and int(r.headers["content-length"]) > 1_000_000
        # cabeçalho do CSV: os primeiros bytes do zip bastam para ver que é um zip
        assert c.get(ARQUIVO.format(ano=2025), headers={**H, "Range": "bytes=0-3"}).content[:2] == b"PK"
    assert {"ideCadastro", "vlrLiquido", "vlrDocumento"} <= COLUNAS_CEAP


def test_elotech_api():
    with httpx.Client(headers=H, timeout=60) as c:
        docs = c.get(f"{ELO}/v3/api-docs").json()
        assert "/api/servidores" in docs["paths"]
        j = c.get(f"{ELO}/api/diarias?exercicio=2023&dataInicial=2023-01-01&dataFinal=2023-12-31&page=0&size=5",
                  headers={**H, "entidade": "1", "exercicio": "2023"}).json()
        assert j["totalElements"] >= 1 and CAMPOS_DIARIA <= set(j["content"][0])
        s = c.get(f"{ELO}/api/servidores?entidade=1&exercicio=2026&page=0&size=3", headers={**H, "entidade": "1", "exercicio": "2026"}).json()
        assert CAMPOS_SERVIDOR <= set(s["content"][0])


def test_tse_arquivo():
    with httpx.Client(headers=H, timeout=60) as c:
        assert c.head(TSE.format(ano=2024)).status_code == 200


async def _pagina(ua: str):
    pw = await async_playwright().start()
    nav = await pw.chromium.launch()
    ctx = await nav.new_context(user_agent=ua, locale="pt-BR")
    return pw, nav, await ctx.new_page()


async def test_legado_menu_e_botoes():
    pw, nav, p = await _pagina(config.UA_ROBO)
    try:
        await p.goto(INICIO, wait_until="networkidle")
        await p.get_by_role("link", name=MENU).first.click()
        await p.get_by_role("button", name=RE_BOTAO).first.wait_for(timeout=20000)
        textos = await p.get_by_role("button").all_inner_texts()
        assert len([t for t in textos if RE_BOTAO.search(t)]) >= 4
    finally:
        await nav.close()
        await pw.stop()


async def test_prefeitura_filtros_e_postback():
    pw, nav, p = await _pagina(config.UA_NAVEGADOR_ROBO)
    try:
        await p.goto(PMC, wait_until="networkidle")
        assert await p.evaluate("typeof __doPostBack === 'function'")
        orgaos = await p.eval_on_selector(SEL["orgao"], "e => Array.from(e.options).map(o => o.value)")
        assert ORGAO in orgaos
        cab = await p.locator(SEL["grade"]).evaluate("t => Array.from(t.rows[0].cells).map(c => c.innerText)")
        mapa, _ = ler_grade([cab])  # o mesmo leitor do robô; PortalMudou se faltar coluna
        assert {"doc", "solicitante", "cargo", "inicio", "valor"} <= set(mapa)
    finally:
        await nav.close()
        await pw.stop()


async def test_betha_diarias_tabela_e_contador():
    pw, nav, p = await _pagina(config.UA_ROBO)
    try:
        await p.goto(f"{PORTAL}/consulta/{CONSULTAS['diarias-2026']['id']}", wait_until="networkidle")
        await p.locator("table.table-card").first.wait_for(timeout=30000)
        assert (await p.locator(".bth-powernumber__value").first.inner_text()).strip().isdigit()
        rotulos = {chave_coluna(t) for t in await p.locator("table.table-card thead th").all_inner_texts()}
        assert {"CREDOR", "CARGO DO CREDOR", "NUMERO", "PERIODO"} <= rotulos
    finally:
        await nav.close()
        await pw.stop()
