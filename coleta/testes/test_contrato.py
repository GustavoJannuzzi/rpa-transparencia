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


async def test_betha_generico_acha_a_consulta_pelo_texto_do_menu():
    """O mesmo caminho do `descobrir`: o menu que a página recebe tem um item
    "Diárias", ele aparece na tela, e a consulta tem as colunas de diária."""
    import json as _json

    from coleta import entidades
    from coleta.fontes.betha.fonte import API as BETHA_API, COLUNAS_DIARIAS, JS_TEXTOS_MENU, candidatas_diarias
    from coleta.nucleo.texto import normalizar_nome

    e = next(x for x in entidades.betha() if x.fonte == "betha_fazenda_rio_grande")
    pw, nav, p = await _pagina(config.UA_ROBO)
    try:
        async with p.expect_response(lambda r: r.url.split("?")[0] == f"{BETHA_API}/menu", timeout=60000) as resp:
            await p.goto(e.tela, wait_until="networkidle")
        menu = _json.loads(await (await resp.value).body())
        achadas = candidatas_diarias(menu)
        assert achadas, "o menu não tem mais um item 'Diárias'"
        await p.wait_for_timeout(2000)
        assert "DIARIAS" in {normalizar_nome(t) for t in await p.evaluate(JS_TEXTOS_MENU)}
        await p.goto(f"{e.tela}/consulta/{achadas[0][1]['id']}", wait_until="networkidle")
        await p.locator("table.table-card").first.wait_for(timeout=30000)
        assert (await p.locator(".bth-powernumber__value").first.inner_text()).strip().isdigit()
        assert COLUNAS_DIARIAS <= {chave_coluna(t) for t in await p.locator("table.table-card thead th").all_inner_texts()}
    finally:
        await nav.close()
        await pw.stop()


async def test_equiplano_formulario_entidade_e_exercicios():
    """O formulário de diárias tem a Câmara configurada no select, e o AJAX devolve os exercícios."""
    from coleta import entidades
    from coleta.fontes.equiplano.fonte import SEL_CSV, SEL_ENTIDADE, SEL_INICIO, SEL_VISUALIZAR, eh_a_camara

    e = next(x for x in entidades.equiplano() if x.fonte == "equiplano_francisco_beltrao")
    pw, nav, p = await _pagina(config.UA_ROBO)
    try:
        await p.goto(e.tela, wait_until="networkidle")
        opcoes = dict(await p.eval_on_selector(SEL_ENTIDADE, "s => Array.from(s.options).map(o => [o.value, o.text.trim()])"))
        assert eh_a_camara(opcoes[str(e.entidade)], e.municipio)
        for sel in (SEL_INICIO, SEL_CSV, SEL_VISUALIZAR):
            assert await p.locator(sel).count() == 1, sel
        async with p.expect_response(lambda r: "loadAjaxExercicios" in r.url) as resp:
            await p.select_option(SEL_ENTIDADE, str(e.entidade))
        anos = [o["valor"] for o in (await (await resp.value).json())["opcoesParaSelect"]]
        assert "2025" in anos
    finally:
        await nav.close()
        await pw.stop()


# ---------------------------------------------------------------- casas novas (um teste por fornecedor)
def _cliente(**kw) -> httpx.Client:
    return httpx.Client(headers=H, timeout=httpx.Timeout(60, connect=30), **kw)


def _sem_rede(e: Exception):
    """O portal não respondeu daqui (ex.: o runner do GitHub, fora do Brasil): isso é rede,
    não portal que mudou. O teste é pulado com o motivo, em vez de abrir a issue."""
    pytest.skip(f"o portal não respondeu desta rede ({type(e).__name__}); não é mudança de layout")


def test_elotech_generico_entidades_e_diarias():
    from coleta import entidades
    from coleta.fontes.elotech.fonte import CAMPOS_DIARIA as CAMPOS

    e = next(x for x in entidades.elotech() if x.fonte == "elotech_maringa")
    try:
        with _cliente() as c:
            lista = c.get(f"{e.api}/api/entidades", headers={**H, "Accept": "application/json"}).json()
            camara = next(x for x in lista if str(x["id"]) == str(e.entidade))
            assert "".join(ch for ch in camara["cnpj"] if ch.isdigit()) == e.cnpj
            j = c.get(f"{e.api}/api/diarias?exercicio=2025&dataInicial=2025-01-01&dataFinal=2025-12-31&page=0&size=5",
                      headers={**H, "entidade": str(e.entidade), "exercicio": "2025"}).json()
            assert {"totalElements", "content"} <= set(j) and CAMPOS <= set(j["content"][0])
    except (httpx.ConnectTimeout, httpx.ConnectError) as erro:
        _sem_rede(erro)


def test_cldf_conjunto_lista_recursos_por_ano():
    import re

    from coleta import entidades
    from coleta.fontes.cldf.fonte import RE_DOWNLOAD, RE_RECURSO

    url = entidades.assembleias()["cldf"].extra["conjunto"]
    try:
        with _cliente(follow_redirects=True) as c:
            html = c.get(url).text
            recursos = RE_RECURSO.findall(html)
            assert recursos and RE_DOWNLOAD.findall(html)
            assert any(re.search(r"20\d\d", t) for _, _, t in recursos)
    except (httpx.ConnectTimeout, httpx.ConnectError) as erro:
        _sem_rede(erro)


def test_almg_api_lista_e_datas():
    from coleta import entidades

    api = entidades.assembleias()["almg"].extra["api"]
    try:
        with _cliente() as c:
            lista = c.get(f"{api}/deputados/em_exercicio?formato=json").json()["list"]
            assert len(lista) >= 70 and {"id", "nome", "partido"} <= set(lista[0])
            datas = c.get(f"{api}/prestacao_contas/verbas_indenizatorias/deputados/{lista[0]['id']}/datas?formato=json").json()
            assert "listaFechamentoVerba" in datas
    except (httpx.ConnectTimeout, httpx.ConnectError) as erro:
        _sem_rede(erro)


def test_alesp_arquivo_e_campos():
    from coleta import entidades
    from coleta.fontes.alesp.fonte import CAMPOS

    a = entidades.assembleias()["alesp"].extra
    try:
        with _cliente() as c:
            h = c.head(a["arquivo"])
            assert h.status_code == 200 and h.headers.get("last-modified")
            inicio = c.get(a["arquivo"], headers={**H, "Range": "bytes=0-2000"}).text
            assert inicio.lstrip().startswith('{"despesas":[')
            assert all(f'"{campo}"' in inicio for campo in CAMPOS)
    except (httpx.ConnectTimeout, httpx.ConnectError) as erro:
        _sem_rede(erro)


# ---------------------------------------------------------------- atividade nas sessões
def test_sapl_robots_e_campos_da_api():
    """Um SAPL (Irati, o menor da lista): o robots.txt continua deixando a API e pedindo
    60 s, e os recursos usados ainda trazem os campos. Dois pedidos, com a pausa pedida."""
    import time
    import urllib.robotparser

    from coleta import entidades
    from coleta.fontes.sapl.fonte import CAMPOS

    e = next(x for x in entidades.sapl() if x.fonte == "sapl_irati")
    try:
        with _cliente() as c:
            rp = urllib.robotparser.RobotFileParser()
            rp.parse(c.get(f"{e.host}/robots.txt").text.splitlines())
            assert rp.can_fetch(config.UA_ROBO, f"{e.api}/sessao/sessaoplenaria/")
            atraso = rp.crawl_delay(config.UA_ROBO)
            time.sleep(float(atraso or 1))
            j = c.get(f"{e.api}/sessao/sessaoplenaria/?page_size=2&o=-id", headers={**H, "Accept": "application/json"}).json()
            assert {"pagination", "results"} <= set(j) and isinstance(j["pagination"]["total_entries"], int)
            assert CAMPOS["sessaoplenaria"] <= set(j["results"][0])
    except (httpx.ConnectTimeout, httpx.ConnectError) as erro:
        _sem_rede(erro)


async def test_frequencia_curitiba_cartoes_e_anexos():
    """A consulta de frequência do Betha: cartões com ano e período, e o "Ver arquivos"
    que devolve o PDF num link pré-assinado."""
    from coleta.fontes.cmc_frequencia.fonte import CONSULTA, URL_CONSULTA, competencia_do_cartao

    pw, nav, p = await _pagina(config.UA_ROBO)
    try:
        hits: list[dict] = []

        async def ao_responder(r):
            if f"/busca-textual/{CONSULTA}?" in r.url and r.request.method == "POST":
                hits.extend((await r.json()).get("hits", []))

        p.on("response", ao_responder)
        await p.goto(URL_CONSULTA, wait_until="networkidle")
        await p.locator("table.table-card").first.wait_for(timeout=30000)
        assert hits and all(competencia_do_cartao(int(h["sourceAsMap"]["ano"]), str(h["sourceAsMap"]["periodo"])) for h in hits)
        async with p.expect_response(lambda r: f"/busca/{CONSULTA}/anexos/" in r.url, timeout=45000) as resp:
            await p.locator("table.table-card tbody tr").first.locator("td.detalhamentoArquivos").click()
        anexos = await (await resp.value).json()
        assert anexos and {"url", "nome", "tipo"} <= set(anexos[0]) and "X-Amz-Expires" in anexos[0]["url"]
    finally:
        await nav.close()
        await pw.stop()
