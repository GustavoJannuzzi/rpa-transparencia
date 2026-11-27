"""Betha Cloud: um robô de navegador para qualquer câmara que usa o portal.

O Betha é uma aplicação Vue sem API pública. O robô abre o portal como uma
pessoa: a página carrega o cadastro do portal e o menu, e é dela que o robô tira
o que muda de uma câmara para outra.

- **O portal certo.** O código do portal (`#/<portal>`) vem de `entidades.toml`.
  O `descobrir` confere o código IBGE que o próprio portal informa e para se não
  bater, como o CNPJ no Elotech.
- **A consulta pelo texto do menu.** Cada câmara monta o próprio menu: o mesmo
  modelo de consulta aparece em "Receitas e Despesas > Diárias", "Pessoal >
  Diárias" ou "DIÁRIAS", com o título "Diárias", "Diárias." ou "Diárias 2026", e
  com um número diferente em cada portal. O robô procura o item pelo texto, no
  menu que a tela mostra, e tira o número da consulta do menu que a própria
  página recebeu. Quando dois itens têm o mesmo texto (Bandeirantes tem
  "Diárias" e "DIÁRIAS"), fica a consulta que tem as colunas de diária; a outra é
  registrada como descartada, com as colunas que tinha.
- **A leitura.** Contador "Registros encontrados", 100 por página e "Próxima"
  até o fim, lendo a tabela da tela. Cada linha é conferida com a resposta que a
  tela recebeu (mesmo número, credor, valor e período); se a tela e o dado não
  batem, o portal mudou. "0 registros" é resultado: a câmara tem a consulta e
  não a alimenta.

O que a fonte mostra e o robô não grava: o CPF do credor (vem mascarado, e o
robô nem lê a coluna) e a finalidade da viagem, que é texto livre e pode citar
servidor pelo nome. Só Curitiba, revisada linha a linha na fase 1, publica a
finalidade. Servidor nunca tem nome gravado: o cargo decide na leitura.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterator
from datetime import date
from decimal import Decimal

from ... import config
from ...de_para import eh_cargo_parlamentar
from ...entidades import EntidadeBetha
from ...modelo import Descoberta, Despesa, ItemInventario, Pendencia, PessoaFonte, Resultado, SistemaOrigem, TotalOficial
from ...nucleo.erros import FalhaTransitoria, PortalMudou
from ...nucleo.evidencia import guardar_original
from ...nucleo.texto import ValorIlegivel, chave_hash, dinheiro_br, normalizar_nome
from ..base import FonteNavegador

API = "https://api.transparencia.betha.cloud/transparencia/api"
# Texto do item de menu da consulta de diárias, depois de normalizar (sem acento,
# pontuação nem número): "Diárias", "Diárias.", "DIÁRIAS", "Diárias 2026".
TEXTO_MENU_DIARIAS = "DIARIAS"
# Colunas sem as quais a linha não é uma diária por pessoa (o modelo de consulta do
# Betha; a câmara escolhe a ordem e pode esconder o CPF, que o robô não lê).
COLUNAS_DIARIAS = frozenset({"ANO", "CREDOR", "CARGO DO CREDOR", "NUMERO", "VALOR PREVISTO DIARIA R", "PERIODO"})
RE_PERIODO = re.compile(r"(\d{2})-(\d{2})-(\d{4})")


def chave_coluna(rotulo: str) -> str:
    return normalizar_nome(rotulo)


def consultas_do_menu(menu: list[dict], caminho: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], dict]]:
    """Cada consulta do menu (o JSON que a página recebe), com o caminho de grupos até ela."""
    for m in menu:
        c2 = (*caminho, str(m.get("nome") or ""))
        for c in m.get("consultas") or []:
            yield c2, c
        yield from consultas_do_menu(m.get("subMenus") or [], c2)


def candidatas_diarias(menu: list[dict]) -> list[tuple[tuple[str, ...], dict]]:
    """Consultas do menu cujo título, normalizado, é o de diárias."""
    return [(caminho, c) for caminho, c in consultas_do_menu(menu)
            if c.get("tipo") == "CONSULTA_PADRAO" and normalizar_nome(c.get("titulo")) == TEXTO_MENU_DIARIAS]


# Textos do menu na tela (o item é <a>, às vezes com o texto num <span> dentro)
JS_TEXTOS_MENU = """() => Array.from(document.querySelectorAll('a, a span')).map(e => (e.textContent || '').trim()).filter(Boolean)"""


class BethaCloud(FonteNavegador):
    grupo = "betha"
    # Com "HeadlessChrome" no User-Agent o Betha devolve 403; com o do robô, abre.
    ua = config.UA_ROBO
    pausa = 1.5
    # o texto livre da finalidade pode citar servidor; só Curitiba (revisada) o publica
    motivo_livre = False

    def __init__(self, ent: EntidadeBetha) -> None:
        self.ent = ent
        self.id = ent.fonte
        self.portal = ent.tela
        self.sistema = SistemaOrigem(
            fonte=ent.fonte, casa=ent.casa, sistema="Portal da Transparência Betha", fornecedor="Betha Sistemas", modo="robo",
            cobre_de=ent.de, cobre_ate=ent.ate, endereco=ent.tela,
            o_que_tem=(f"Diárias da Câmara de {ent.municipio}, como a consulta \"Diárias\" do portal mostra, com o cargo de "
                       "quem recebeu; o valor é o previsto na concessão."),
        )
        super().__init__()

    # ------------------------------------------------------------------ descobrir
    async def _abrir_portal(self) -> tuple[dict, list[dict], str]:
        """Abre a página inicial do portal: o cadastro do portal e o menu, como a página recebe."""
        assert self.pagina is not None
        recebido: dict[str, bytes] = {}

        async def ao_responder(r):
            base = r.url.split("?")[0]
            if r.request.method == "GET" and base in (f"{API}/portal", f"{API}/menu"):
                try:
                    recebido[base.rsplit("/", 1)[1]] = await r.body()
                except Exception:
                    pass

        self.pagina.on("response", ao_responder)
        try:
            await self.ir(self.portal, wait_until="networkidle")
            await self._recusou()
            for _ in range(20):
                if "portal" in recebido and "menu" in recebido:
                    break
                await self.pagina.wait_for_timeout(500)
            else:
                raise FalhaTransitoria("o portal não carregou o cadastro ou o menu")
        finally:
            self.pagina.remove_listener("response", ao_responder)
        h = guardar_original(self.con, self.id, recebido["portal"] + b"\n" + recebido["menu"], f"{self.portal} (portal e menu)", "json")
        try:
            portal, menu = json.loads(recebido["portal"]), json.loads(recebido["menu"])
        except ValueError as e:
            raise PortalMudou("o cadastro ou o menu do portal não veio em JSON") from e
        return portal, menu, h

    async def _no_menu_da_tela(self, titulos: list[str]) -> None:
        """Espera o menu da tela mostrar cada título (o Vue desenha o menu depois de recebê-lo)."""
        assert self.pagina is not None
        alvo = {normalizar_nome(t) for t in titulos}
        vistos: set[str] = set()
        for _ in range(30):
            vistos = {normalizar_nome(t) for t in await self.pagina.evaluate(JS_TEXTOS_MENU)}
            if alvo <= vistos:
                return
            await self.pagina.wait_for_timeout(500)
        raise PortalMudou(f"as consultas {sorted(alvo - vistos)} estão no menu que a página recebeu, mas não no menu da tela")

    async def _recusou(self) -> None:
        assert self.pagina is not None
        if "403" in (await self.pagina.title() or "") or await self.pagina.locator("text=403 Forbidden").count():
            raise PortalMudou("o Betha devolveu 403 (User-Agent recusado?)")

    async def _abrir_consulta(self, consulta: int) -> str:
        """Abre a consulta e espera a busca dela (a SPA troca só o `#`: sem esperar a
        resposta da consulta nova, a tabela na tela ainda é a da anterior)."""
        assert self.pagina is not None
        url = f"{self.portal}/consulta/{consulta}"
        try:
            async with self.pagina.expect_response(
                    lambda r: f"/busca-textual/{consulta}?" in r.url and r.request.method == "POST", timeout=45000):
                await self.ir(url, wait_until="networkidle")
        except FalhaTransitoria:
            raise
        except Exception as e:
            await self._recusou()
            raise FalhaTransitoria(f"a consulta {consulta} não fez a busca dela") from e
        await self._recusou()
        try:
            await self.pagina.locator("table.table-card").first.wait_for(timeout=30000)
        except Exception as e:
            raise FalhaTransitoria(f"a tabela da consulta {consulta} não apareceu") from e
        await self.pagina.wait_for_timeout(500)
        return url

    async def _colunas(self, consulta: int) -> tuple[list[str], str]:
        """Abre a consulta e lê só o cabeçalho da tabela."""
        assert self.pagina is not None
        url = await self._abrir_consulta(consulta)
        return [chave_coluna(t) for t in await self.pagina.locator("table.table-card thead th").all_inner_texts()], url

    async def descobrir(self) -> Descoberta:
        portal, menu, h = await self._abrir_portal()
        proc = self.procedencia(self.portal, h, "cadastro do portal e menu, como a página recebe")
        if str(portal.get("codigoIbge")) != str(self.ent.ibge):
            raise PortalMudou(f"o portal {self.ent.portal} é de outro município (IBGE {portal.get('codigoIbge')}, "
                              f"'{portal.get('nome')}'); a configuração aponta para o portal errado")
        if "CAMARA" not in normalizar_nome(portal.get("nome")) and "LEGISLATIV" not in normalizar_nome(portal.get("nome")):
            raise PortalMudou(f"o portal {self.ent.portal} não é de uma câmara ('{portal.get('nome')}')")
        totais = [TotalOficial(fonte=self.id, escopo="portal", metrica="entidade", valor=str(portal.get("nome")),
                               texto_original=f"código IBGE {portal.get('codigoIbge')}", procedencia=proc)]
        candidatas = candidatas_diarias(menu)
        if candidatas:
            # o item tem de estar no menu que a tela mostra, com o mesmo texto
            await self._no_menu_da_tela([c["titulo"] for _, c in candidatas])
        itens: list[ItemInventario] = []
        for caminho, c in candidatas:
            cid = int(c["id"])
            colunas, url = await self._colunas(cid)
            onde = " > ".join(p for p in caminho if p)
            if COLUNAS_DIARIAS <= set(colunas):
                itens.append(ItemInventario(chave=f"diarias-consulta-{cid}", descricao=f"{c['titulo']} (menu {onde})", periodo="todos",
                                            parametros={"consulta": cid, "titulo": c["titulo"], "menu": onde}))
            else:
                totais.append(TotalOficial(fonte=self.id, escopo=f"consulta-{cid}", metrica="consulta_descartada", valor=c["titulo"],
                                           texto_original=f"menu {onde}; colunas {', '.join(colunas)}",
                                           procedencia=self.procedencia(url, h, "cabeçalho da tabela")))
        if not itens:
            achadas = "; ".join(f"'{c['titulo']}' ({c['id']})" for _, c in candidatas) or "nenhuma"
            raise PortalMudou(f"o menu não tem a consulta de diárias com o cargo de quem recebeu (com o texto '{TEXTO_MENU_DIARIAS}': {achadas})")
        return Descoberta(itens=itens, totais=totais)

    # ------------------------------------------------------------------ leitura da consulta
    async def _ler_consulta(self, consulta: int):
        """Devolve (linhas: list[dict rótulo->texto], contador oficial, atualização, hits da resposta da tela,
        hashes das páginas, url, rótulos das colunas, título da consulta)."""
        assert self.pagina is not None
        hits: list[dict] = []
        titulo: dict[str, str] = {}

        async def ao_responder(r):
            if f"/busca-textual/{consulta}?" in r.url and r.request.method == "POST":
                try:
                    j = await r.json()
                    hits.extend(h.get("sourceAsMap", {}) for h in j.get("hits", []))
                except Exception:
                    pass
            elif re.search(rf"/api/consulta/{consulta}\?_=", r.url):
                try:
                    titulo["t"] = (await r.json()).get("titulo") or ""
                except Exception:
                    pass

        self.pagina.on("response", ao_responder)
        try:
            url = await self._abrir_consulta(consulta)
            tabela = self.pagina.locator("table.table-card").first
            contador_txt = await self.pagina.locator(".bth-powernumber__value").first.inner_text()
            if not contador_txt.strip().isdigit():
                raise PortalMudou(f"contador 'Registros encontrados' ilegível: {contador_txt!r}")
            contador = int(contador_txt.strip())
            corpo = await self.pagina.inner_text("body")
            m = re.search(r"Última atualização dos dados em (\d{2}/\d{2}/\d{4} \d{2}:\d{2})", corpo)
            atualizacao = m.group(1) if m else None
            rotulos = [chave_coluna(t) for t in await tabela.locator("thead th").all_inner_texts()]
            seletor = self.pagina.locator("select.responsive-result-pag").first
            if contador and await seletor.count():
                async with self.educacao.vez(url):
                    async with self.pagina.expect_response(lambda r: f"/busca-textual/{consulta}?" in r.url, timeout=45000):
                        hits.clear()
                        await seletor.select_option("100")
                await self.pagina.wait_for_timeout(800)
            linhas: list[dict] = []
            hashes: list[str] = []
            pagina_n = 1
            while True:
                html = await self.pagina.content()
                hashes.append(guardar_original(self.con, self.id, html.encode("utf-8"), f"{url}&pagina={pagina_n}", "html"))
                corpo_tab = await tabela.evaluate(
                    "t => Array.from(t.tBodies[0]?.rows || []).map(r => Array.from(r.cells).map(c => c.innerText.trim()))")
                for cel in corpo_tab:
                    if len(cel) < len(rotulos) - 1:
                        continue
                    linhas.append({"_pagina": pagina_n, **{rotulos[i]: cel[i] for i in range(min(len(rotulos), len(cel)))}})
                proxima = self.pagina.locator("button.btn-pagination", has_text="Próxima").first
                if not contador or await proxima.count() == 0 or await proxima.is_disabled():
                    break
                async with self.educacao.vez(url):
                    async with self.pagina.expect_response(lambda r: f"/busca-textual/{consulta}?" in r.url, timeout=45000):
                        await proxima.click()
                await self.pagina.wait_for_timeout(600)
                pagina_n += 1
                if pagina_n > 200:
                    raise PortalMudou("paginação do Betha não termina")
            if len(linhas) != contador:
                raise FalhaTransitoria(f"o contador diz {contador} e a tela mostrou {len(linhas)} linhas")
            return linhas, contador, atualizacao, hits, hashes, url, rotulos, titulo.get("t")
        finally:
            self.pagina.remove_listener("response", ao_responder)

    async def coletar_item(self, item: ItemInventario) -> Resultado:
        consulta = int(item.parametros["consulta"])
        linhas, contador, atualizacao, hits, hashes, url, rotulos, titulo = await self._ler_consulta(consulta)
        if titulo is not None and normalizar_nome(titulo) != TEXTO_MENU_DIARIAS:
            raise PortalMudou(f"a consulta {consulta} agora se chama '{titulo}'; rode o descobrir de novo")
        proc0 = self.procedencia(url, hashes[0], "contador 'Registros encontrados'")
        res = Resultado(totais=[
            TotalOficial(fonte=self.id, escopo=item.chave, metrica="registros", valor=str(contador),
                         texto_original=f"Registros encontrados: {contador}", procedencia=proc0),
        ])
        if atualizacao:
            res.totais.append(TotalOficial(fonte=self.id, escopo=item.chave, metrica="atualizado_em", valor=atualizacao,
                                           texto_original=f"Última atualização dos dados em {atualizacao}", procedencia=proc0))
        self._diarias(item, linhas, hits, hashes, url, res, rotulos)
        return res

    # ------------------------------------------------------------------ diárias
    def _diarias(self, item, linhas, hits, hashes, url, res: Resultado, rotulos: list[str] | None = None) -> None:
        colunas = set(rotulos) if rotulos is not None else (set(linhas[0]) if linhas else set(COLUNAS_DIARIAS))
        if not COLUNAS_DIARIAS <= colunas:
            raise PortalMudou(f"colunas das diárias mudaram: {sorted(colunas)}")
        por_numero = defaultdict(list)
        for h in hits:
            por_numero[str(h.get("numeroDiaria"))].append(h)
        vistos: dict[str, int] = {}
        for i, l in enumerate(linhas, start=1):
            proc = self.procedencia(url, hashes[l["_pagina"] - 1], f"página {l['_pagina']}, linha {i}")
            cargo_tela = l["CARGO DO CREDOR"]
            # "-" na coluna é o jeito da tela de dizer que não há cargo
            cargo = cargo_tela if normalizar_nome(cargo_tela) else ""
            parlamentar = eh_cargo_parlamentar(cargo)
            base = chave_hash(self.id, l["ANO"], l["NUMERO"], l["PERIODO"], l["VALOR PREVISTO DIARIA R"], cargo_tela)
            n = vistos.get(base, 0)
            vistos[base] = n + 1
            chave = chave_hash(base, n)
            try:
                valor = dinheiro_br(l["VALOR PREVISTO DIARIA R"])
            except ValorIlegivel:
                res.pendencias.append(Pendencia(fonte=self.id, chave=chave, motivo=f"valor ilegível: {l['VALOR PREVISTO DIARIA R']!r}",
                                                texto_original=f"número {l['NUMERO']}, cargo '{cargo}'", procedencia=proc))
                continue
            m = RE_PERIODO.match(l["PERIODO"])
            if not m or not l["ANO"].strip().isdigit():
                res.pendencias.append(Pendencia(fonte=self.id, chave=chave, motivo=f"período ilegível: {l['PERIODO']!r}",
                                                texto_original=f"número {l['NUMERO']}, ano {l['ANO']!r}, cargo '{cargo}'", procedencia=proc))
                continue
            inicio = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            # Conferência linha a linha com o que a tela recebeu
            # (o mesmo número aparece em duas linhas quando há diária e complemento)
            par = [h for h in por_numero.get(l["NUMERO"], [])
                   if normalizar_nome(h.get("credor")) == normalizar_nome(l["CREDOR"])
                   and Decimal(str(h.get("valorTotal"))) == valor
                   and (h.get("periodoDiarias") or "") == l["PERIODO"]]
            if hits and not par:
                raise PortalMudou(f"linha da tela sem par igual na resposta da tela (número {l['NUMERO']}, {valor})")
            nome = l["CREDOR"].strip() if parlamentar else None
            ano = int(l["ANO"])
            destino = l.get("LOCAL DE DESTINO", "").strip()
            if self.motivo_livre and parlamentar:
                finalidade = (par[0].get("finalidade") if par else None) or l.get("FINALIDADE", "")
                descricao = (destino + " — " + finalidade) or None
            else:
                descricao = destino or None
            res.despesas.append(Despesa(
                chave=chave, fonte=self.id, item=item.chave, tipo="diaria_municipal", casa=self.ent.casa,
                ref_parlamentar=f"nome:{normalizar_nome(nome)}" if parlamentar else None,
                beneficiario_tipo="parlamentar" if parlamentar else "servidor", nome_beneficiario=nome,
                cargo_original=cargo, data=inicio, competencia=f"{inicio.year}-{inicio.month:02d}", ano=ano,
                categoria_original="Diária", valor=valor, documento_url=url, descricao=descricao, procedencia=proc,
                extra={"numero": l["NUMERO"], "quantidade": l.get("QUANTIDADE"), "periodo_original": l["PERIODO"],
                       "valor_e_previsto": True, "conferido_com_resposta_da_tela": bool(par)},
            ))
            if parlamentar:
                res.pessoas.append(PessoaFonte(fonte=self.id, ref=f"nome:{normalizar_nome(nome)}", periodo=str(ano),
                                               nome=nome, casa=self.ent.casa, procedencia=proc))
