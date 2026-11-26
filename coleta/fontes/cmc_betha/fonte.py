"""Câmara de Curitiba no Betha (2026): robô de navegador.

Aplicação Vue sem API pública. O robô abre cada consulta como uma pessoa, lê o
contador "Registros encontrados", põe 100 por página e vai clicando em
"Próxima", lendo a tabela da tela. A resposta que a própria tela recebe serve de
conferência linha a linha (e completa a finalidade, que a tabela corta em
"... (Ver mais)"). Se tela e dado divergem, é portal que mudou.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from decimal import Decimal

from ... import config
from ...de_para import eh_cargo_parlamentar
from ...modelo import Descoberta, Despesa, GabineteRetrato, ItemInventario, Pendencia, PessoaFonte, Resultado, SistemaOrigem, TotalOficial
from ...nucleo.banco import agora
from ...nucleo.erros import FalhaTransitoria, PortalMudou
from ...nucleo.evidencia import guardar_original
from ...nucleo.texto import ValorIlegivel, chave_hash, dinheiro_br, normalizar_nome
from ..base import FonteNavegador

PORTAL = "https://transparencia.betha.cloud/#/pYH4AbLiIyAHwETflX8gpQ=="
CONSULTAS = {
    "diarias-2026": {"id": 324825, "descricao": "Diárias 2026", "periodo": "2026"},
    "servidores-ativos": {"id": 360082, "descricao": "Servidores Públicos – Ativos (gabinetes)", "periodo": "atual"},
    "vereadores": {"id": 360083, "descricao": "Vereadores – Remunerações (lista atual)", "periodo": "atual"},
}
RE_GABINETE = re.compile(r"^GAB\.?\s*VER\.?\s*(.+)$", re.I)


def chave_coluna(rotulo: str) -> str:
    return normalizar_nome(rotulo)


class CmcBetha(FonteNavegador):
    id = "cmc_betha"
    # Com "HeadlessChrome" no User-Agent o Betha devolve 403; com o do robô, abre.
    ua = config.UA_ROBO
    pausa = 1.5
    sistema = SistemaOrigem(
        fonte="cmc_betha", casa="cmc", sistema="Portal da Transparência Betha", fornecedor="Betha Sistemas",
        modo="robo", cobre_de=2026, cobre_ate=2026, endereco=PORTAL,
        o_que_tem="Diárias de 2026, servidores ativos por gabinete (Organograma) e a lista de vereadores.",
    )

    async def descobrir(self) -> Descoberta:
        itens = [ItemInventario(chave=k, descricao=v["descricao"], periodo=v["periodo"], parametros={"consulta": v["id"]})
                 for k, v in CONSULTAS.items()]
        return Descoberta(itens=itens)

    # ------------------------------------------------------------------
    async def _ler_consulta(self, consulta: int):
        """Devolve (linhas: list[dict rótulo->texto], contador oficial, atualização, hits do JSON, hashes)."""
        assert self.pagina is not None
        hits: list[dict] = []

        async def ao_responder(r):
            if f"/busca-textual/{consulta}?" in r.url and r.request.method == "POST":
                try:
                    j = await r.json()
                    hits.extend(h.get("sourceAsMap", {}) for h in j.get("hits", []))
                except Exception:
                    pass

        self.pagina.on("response", ao_responder)
        try:
            url = f"{PORTAL}/consulta/{consulta}"
            await self.ir(url, wait_until="networkidle")
            if "403" in (await self.pagina.title() or "") or await self.pagina.locator("text=403 Forbidden").count():
                raise PortalMudou("o Betha devolveu 403 (User-Agent recusado?)")
            tabela = self.pagina.locator("table.table-card").first
            try:
                await tabela.wait_for(timeout=30000)
            except Exception as e:
                raise FalhaTransitoria("a tabela da consulta não apareceu") from e
            contador_txt = await self.pagina.locator(".bth-powernumber__value").first.inner_text()
            if not contador_txt.strip().isdigit():
                raise PortalMudou(f"contador 'Registros encontrados' ilegível: {contador_txt!r}")
            contador = int(contador_txt.strip())
            corpo = await self.pagina.inner_text("body")
            m = re.search(r"Última atualização dos dados em (\d{2}/\d{2}/\d{4} \d{2}:\d{2})", corpo)
            atualizacao = m.group(1) if m else None
            rotulos = [chave_coluna(t) for t in await tabela.locator("thead th").all_inner_texts()]
            seletor = self.pagina.locator("select.responsive-result-pag").first
            if await seletor.count():
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
                if await proxima.count() == 0 or await proxima.is_disabled():
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
            return linhas, contador, atualizacao, hits, hashes, url
        finally:
            self.pagina.remove_listener("response", ao_responder)

    async def coletar_item(self, item: ItemInventario) -> Resultado:
        consulta = int(item.parametros["consulta"])
        linhas, contador, atualizacao, hits, hashes, url = await self._ler_consulta(consulta)
        proc0 = self.procedencia(url, hashes[0], "contador 'Registros encontrados'")
        res = Resultado(totais=[
            TotalOficial(fonte=self.id, escopo=item.chave, metrica="registros", valor=str(contador),
                         texto_original=f"Registros encontrados: {contador}", procedencia=proc0),
        ])
        if atualizacao:
            res.totais.append(TotalOficial(fonte=self.id, escopo=item.chave, metrica="atualizado_em", valor=atualizacao,
                                           texto_original=f"Última atualização dos dados em {atualizacao}", procedencia=proc0))
        if item.chave.startswith("diarias"):
            self._diarias(item, linhas, hits, hashes, url, res)
        elif item.chave == "servidores-ativos":
            self._gabinetes(linhas, hashes, url, res, atualizacao)
        else:
            self._vereadores(linhas, hashes, url, res)
        return res

    # ------------------------------------------------------------------
    def _diarias(self, item, linhas, hits, hashes, url, res: Resultado) -> None:
        exig = {"ANO", "CREDOR", "CARGO DO CREDOR", "NUMERO", "VALOR PREVISTO DIARIA R", "PERIODO"}
        if linhas and not exig <= set(linhas[0]):
            raise PortalMudou(f"colunas das diárias mudaram: {sorted(linhas[0])}")
        por_numero = defaultdict(list)
        for h in hits:
            por_numero[str(h.get("numeroDiaria"))].append(h)
        vistos: dict[str, int] = {}
        for i, l in enumerate(linhas, start=1):
            proc = self.procedencia(url, hashes[l["_pagina"] - 1], f"página {l['_pagina']}, linha {i}")
            cargo = l["CARGO DO CREDOR"]
            parlamentar = eh_cargo_parlamentar(cargo)
            base = chave_hash(self.id, l["ANO"], l["NUMERO"], l["PERIODO"], l["VALOR PREVISTO DIARIA R"], cargo)
            n = vistos.get(base, 0)
            vistos[base] = n + 1
            chave = chave_hash(base, n)
            try:
                valor = dinheiro_br(l["VALOR PREVISTO DIARIA R"])
            except ValorIlegivel:
                res.pendencias.append(Pendencia(fonte=self.id, chave=chave, motivo=f"valor ilegível: {l['VALOR PREVISTO DIARIA R']!r}",
                                                texto_original=f"número {l['NUMERO']}, cargo '{cargo}'", procedencia=proc))
                continue
            m = re.match(r"(\d{2})-(\d{2})-(\d{4})", l["PERIODO"])
            if not m:
                res.pendencias.append(Pendencia(fonte=self.id, chave=chave, motivo=f"período ilegível: {l['PERIODO']!r}",
                                                texto_original=f"número {l['NUMERO']}, cargo '{cargo}'", procedencia=proc))
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
            finalidade = (par[0].get("finalidade") if par else None) or l.get("FINALIDADE", "")
            nome = l["CREDOR"] if parlamentar else None
            ano = int(l["ANO"])
            res.despesas.append(Despesa(
                chave=chave, fonte=self.id, item=item.chave, tipo="diaria_municipal",
                ref_parlamentar=f"nome:{normalizar_nome(nome)}" if parlamentar else None,
                beneficiario_tipo="parlamentar" if parlamentar else "servidor", nome_beneficiario=nome,
                cargo_original=cargo, data=inicio, competencia=f"{inicio.year}-{inicio.month:02d}", ano=ano,
                categoria_original="Diária", valor=valor, documento_url=f"{PORTAL}/consulta/{CONSULTAS['diarias-2026']['id']}",
                descricao=((l.get("LOCAL DE DESTINO", "") + " — " + finalidade) if parlamentar else l.get("LOCAL DE DESTINO", "")) or None,
                procedencia=proc,
                extra={"numero": l["NUMERO"], "quantidade": l.get("QUANTIDADE"), "periodo_original": l["PERIODO"],
                       "valor_e_previsto": True, "conferido_com_resposta_da_tela": bool(par)},
            ))
            if parlamentar:
                res.pessoas.append(PessoaFonte(fonte=self.id, ref=f"nome:{normalizar_nome(nome)}", periodo=str(ano),
                                               nome=nome, casa="cmc", procedencia=proc))

    def _gabinetes(self, linhas, hashes, url, res: Resultado, atualizacao: str | None) -> None:
        if not linhas:
            raise PortalMudou("consulta de servidores ativos veio vazia")
        cols = set(linhas[0])
        col_org = next((c for c in cols if c.startswith("ORGANOGRAMA")), None)
        col_rem = next((c for c in cols if c.startswith("REMUNERACAO")), None)
        col_sit = next((c for c in cols if c.startswith("SITUACAO")), None)
        if not col_org or not col_rem:
            raise PortalMudou(f"servidores sem Organograma/Remuneração: {sorted(cols)}")
        grupos: dict[str, list[Decimal]] = defaultdict(list)
        for i, l in enumerate(linhas, start=1):
            org = l[col_org].strip()
            if not RE_GABINETE.match(org):
                continue
            if col_sit and l[col_sit] and normalizar_nome(l[col_sit]) not in ("ATIVO", "TRABALHANDO", "EM ATIVIDADE"):
                continue
            try:
                grupos[org].append(dinheiro_br(l[col_rem]))
            except ValorIlegivel:
                proc = self.procedencia(url, hashes[l["_pagina"] - 1], f"página {l['_pagina']}, linha {i}")
                res.pendencias.append(Pendencia(fonte=self.id, chave=chave_hash(self.id, "gab", org, i),
                                                motivo=f"remuneração ilegível: {l[col_rem]!r}",
                                                texto_original=f"gabinete '{org}' (pessoa sem nome)", procedencia=proc))
        hoje = agora()[:10]
        data_ref = hoje
        if atualizacao:
            d, m_, a = atualizacao[:10].split("/")
            data_ref = f"{a}-{m_}-{d}"
        proc = self.procedencia(url, hashes[0], "todas as páginas, coluna Organograma")
        for org, valores in grupos.items():
            m = RE_GABINETE.match(org)
            assert m is not None  # grupos só tem lotação que casou com RE_GABINETE, acima
            res.gabinetes.append(GabineteRetrato(
                fonte=self.id, lotacao_original=org, competencia=data_ref[:7],
                ref_parlamentar=f"gab:{normalizar_nome(m.group(1))}", data_referencia=data_ref,
                pessoas=len(valores), custo=sum(valores, Decimal("0")), procedencia=proc))

    def _vereadores(self, linhas, hashes, url, res: Resultado) -> None:
        if not linhas:
            raise PortalMudou("lista de vereadores veio vazia")
        col_nome = next((c for c in linhas[0] if c.startswith("NOME")), None)
        col_mat = next((c for c in linhas[0] if c.startswith("MATRICULA")), None)
        if not col_nome:
            raise PortalMudou(f"lista de vereadores sem coluna de nome: {sorted(linhas[0])}")
        for i, l in enumerate(linhas, start=1):
            proc = self.procedencia(url, hashes[l["_pagina"] - 1], f"página {l['_pagina']}, linha {i}")
            nome = l[col_nome].strip()
            mat = (l.get(col_mat) or "").strip() or None if col_mat else None
            res.pessoas.append(PessoaFonte(
                fonte=self.id, ref=f"mat:{mat}" if mat else f"nome:{normalizar_nome(nome)}", periodo="atual",
                nome=nome, matricula=mat, casa="cmc", extra={"colunas": sorted(k for k in l if k != "_pagina")},
                procedencia=proc))
