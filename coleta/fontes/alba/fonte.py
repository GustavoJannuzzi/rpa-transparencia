"""Assembleia da Bahia: as verbas indenizatórias pela tela, no navegador.

O caminho, visto em 26/11/2026 em `transparencia/verbas-idenizatorias` (com o erro
de grafia na URL):
- o formulário (GET) filtra por categoria, deputado (id numérico no select), mês e
  ano; a lista vem paginada de 20 em 20, com "Nº processo | Nº NF | Competência |
  Deputado | Categoria | Valor | Detalhes" (177 páginas só em 2026, sem filtro);
- cada "DETALHES" é uma página (`verbas-idenizatorias/{id}/`) com "Categoria | Nº
  nota/recibo | CPF/CNPJ | Nome do fornecedor | Valor | Glosa | Anexo NF"; o anexo é
  o PDF da nota (`fserver/:anexo:...pdf`), que fica como link: são milhares de PDFs
  escaneados, e o número que importa está na tela;
- o servidor às vezes demora (no levantamento, o detalhe estourou 20 s no curl).

O robô percorre um item por deputado e ano, filtrando pelo id do próprio select (que
é a identidade do deputado aqui). Ele vai página a página pelo botão "Próxima" e abre
cada detalhe. A conferência é a linha da lista × o detalhe (mesmo processo, mesma NF,
mesmo valor) e, no ano, a soma das linhas de todos os deputados × as linhas da lista
sem filtro (o número de páginas que a própria paginação mostra).

Janela: 2025–2026, escolhida pelo tempo. Cada nota é uma página, e o ano tem ~3.500
notas: com a pausa de 1 s, um ano leva ~2 h. Os quatro anos da legislatura dariam
~8 h; ficam 2025 e 2026, e 2023–2024 entram numa rodada longa à parte (mudar `de` em
`entidades.toml`).

Para poupar disco, o original guardado de cada página é o trecho da tabela (o resto
são ~55 KB de menu e rodapé, iguais em todas as páginas).
"""

from __future__ import annotations

import re
from decimal import Decimal
from html import unescape

from ...modelo import Descoberta, ItemInventario, Pendencia, PessoaFonte, Resultado, TotalOficial
from ...nucleo.erros import FalhaTransitoria, PortalMudou
from ...nucleo.evidencia import guardar_original
from ...nucleo.texto import ValorIlegivel, chave_hash, dinheiro_br
from ..assembleia_tela import Conferencias, FonteAssembleiaTela, decodificar, tabelas_html, titulo_nome

RE_DETALHE = re.compile(r"/transparencia/verbas-idenizatorias/(\d+)/?")
RE_TABELA = re.compile(r'<table class="tabela-cab[^"]*".*?</table>', re.S)


def trecho(html: str) -> str:
    """O que vale guardar de uma página do portal: as tabelas de dados e a paginação."""
    partes = RE_TABELA.findall(html)
    pag = re.search(r'<ul class="pagination.*?</ul>', html, re.S)
    if pag:
        partes.append(pag.group(0))
    return "\n".join(partes)


def opcoes_deputado(html: str) -> list[tuple[str, str]]:
    m = re.search(r'<select id="deputado_no".*?</select>', html, re.S)
    if not m:
        raise PortalMudou("o formulário da ALBA não tem mais o select de deputado (#deputado_no)")
    out = []
    for v, t in re.findall(r'<option value="(\d+)">\s*(?:<span>)?([^<]+)', m.group(0)):
        out.append((v, re.sub(r"^\s*Dep(?:\.|utad[oa])\s+", "", re.sub(r"\s+", " ", unescape(t))).strip()))
    return out


def ultima_pagina(html: str) -> int:
    """O índice da última página (0 quando não há paginação)."""
    # no HTML o '&' vem como '&amp;': '...&amp;page=176&amp;size=20" title="Última Página"'
    m = re.search(r'href="[^"]*\bpage=(\d+)[^"]*"\s+title="Última', html)
    return int(m.group(1)) if m else 0


def ler_lista(html: str) -> list[dict]:
    for t in tabelas_html(html):
        cab = [c.texto.upper() for c in (t[0] if t else [])]
        if not (cab and re.match(r"N\W*\s*PROCESSO", cab[0])):
            continue
        if len(cab) < 7 or "CATEGORIA" not in cab[4] or "VALOR" not in cab[5]:
            raise PortalMudou(f"a lista da ALBA mudou as colunas: {cab}")
        linhas = []
        for l in t[1:]:
            if len(l) < 7:
                continue
            link = next((h for h in l[6].links if RE_DETALHE.search(h)), None)
            if not link:
                raise PortalMudou("linha da lista da ALBA sem o link de detalhes")
            linhas.append({"processo": l[0].texto, "nf": l[1].texto, "competencia": l[2].texto, "deputado": l[3].texto,
                           "categoria": re.sub(r"\s+", " ", l[4].texto).strip(), "valor_texto": l[5].texto,
                           "detalhe": link, "id": RE_DETALHE.search(link).group(1)})  # type: ignore[union-attr]
        return linhas
    return []


def ler_detalhe(html: str) -> list[dict]:
    for t in tabelas_html(html):
        cab = [c.texto.upper() for c in (t[0] if t else [])]
        if not (cab and cab[0] == "CATEGORIA" and any("FORNECEDOR" in c for c in cab)):
            continue
        esperado = ["CATEGORIA", "Nº NOTA/RECIBO", "CPF/CNPJ", "NOME DO FORNECEDOR", "VALOR", "GLOSA", "ANEXO NF"]
        if cab[:7] != esperado:
            raise PortalMudou(f"o detalhe da ALBA mudou as colunas: {cab}")
        return [{"categoria": re.sub(r"\s+", " ", l[0].texto).strip(), "nota": l[1].texto, "documento": l[2].texto, "fornecedor": l[3].texto,
                 "valor_texto": l[4].texto, "glosa_texto": l[5].texto, "anexo": next(iter(l[6].links), None)}
                for l in t[1:] if len(l) >= 7]
    raise PortalMudou("o detalhe da ALBA veio sem a tabela da nota")


class Alba(FonteAssembleiaTela):
    inicio = "https://www.al.ba.gov.br/transparencia/verbas-idenizatorias"
    timeout_resposta = 90000  # o servidor às vezes demora
    o_que_tem = ("Verba indenizatória de cada deputado estadual, nota a nota, com o fornecedor e o CNPJ, lida na lista paginada e no "
                 "detalhe de cada nota, com o link do PDF da nota.")

    def __init__(self, ent) -> None:
        super().__init__(ent)
        self.de = int(ent.extra.get("de", self.de))
        self.ate = int(ent.extra.get("ate", self.ate))
        self.sistema.cobre_de, self.sistema.cobre_ate = self.de, self.ate

    async def abrir(self, ctx) -> None:
        await super().abrir(ctx)
        assert self.pagina is not None
        # o servidor às vezes leva mais de 45 s para devolver uma página (e dá 500 no meio)
        self.pagina.set_default_navigation_timeout(self.timeout_resposta)

    async def _buscar(self, ano: int, deputado: str = "") -> tuple[str, str, str]:
        """Preenche o formulário e clica em BUSCAR. Devolve (url, html, hash)."""
        assert self.pagina is not None
        await self.ir(self.inicio, wait_until="domcontentloaded")
        if await self.pagina.locator("select#ano").count() == 0:
            raise PortalMudou("o formulário da ALBA não tem mais o select de ano")
        await self.pagina.select_option("select#ano", str(ano))
        await self.pagina.select_option("#deputado_no", deputado)
        return await self._navegar(lambda: self.pagina.click("form[action='/transparencia/verbas-idenizatorias'] button[type=submit]:not([formaction])"))

    async def _navegar(self, acao) -> tuple[str, str, str]:
        assert self.pagina is not None
        r, corpo, _ = await self.gesto(acao, lambda r: r.request.resource_type == "document" and "verbas-idenizatorias" in r.url, tipo="html",
                                    guardar=False)
        assert r is not None
        await self.pagina.wait_for_load_state("domcontentloaded")
        html = decodificar(corpo)
        if r.status >= 400:
            raise FalhaTransitoria(f"HTTP {r.status} em {r.url}")
        h = guardar_original(self.con, self.id, trecho(html).encode("utf-8"), r.url, "html")
        return r.url, html, h

    async def descobrir(self) -> Descoberta:
        assert self.pagina is not None
        await self.ir(self.inicio, wait_until="domcontentloaded")
        deputados = opcoes_deputado(await self.pagina.content())
        itens, totais = [], []
        for ano in range(self.de, self.ate + 1):
            url, html, h = await self._buscar(ano)
            ultima = ultima_pagina(html)
            # as linhas do ano: 20 por página até a penúltima, mais as da última
            n_ultima = len(ler_lista(html))
            if ultima:
                ult = self.pagina.locator("a.paginate-button-next[title^='Última']").first
                url, html_u, h = await self._navegar(ult.click)
                n_ultima = len(ler_lista(html_u))
            totais.append(TotalOficial(fonte=self.id, escopo=str(ano), metrica="linhas_da_lista_do_ano", valor=str(20 * ultima + n_ultima),
                                       texto_original=f"{ultima + 1} páginas de 20; {n_ultima} na última",
                                       procedencia=self.procedencia(url, h, "paginação sem filtro")))
            for did, nome in deputados:
                itens.append(ItemInventario(chave=f"verbas-{did}-{ano}", descricao=f"Verbas de {nome} em {ano}", periodo=str(ano),
                                            parametros={"deputado": did, "nome": nome, "ano": ano}))
        return Descoberta(itens=itens, totais=totais)

    async def coletar_item(self, item: ItemInventario) -> Resultado:
        self.disco()
        assert self.pagina is not None
        p = item.parametros
        did, ano, nome = str(p["deputado"]), int(p["ano"]), str(p["nome"])
        ref = f"id:{did}"
        res = Resultado()
        conf = Conferencias(self.id, item.chave)
        url, html, h = await self._buscar(ano, did)
        proc_lista = self.procedencia(url, h, f"lista de {nome} em {ano}")
        linhas = ler_lista(html)
        ultima = ultima_pagina(html)
        pagina = 0
        while pagina < ultima:
            prox = self.pagina.locator("a.paginate-button-next[title^='Próxima']").first
            if await prox.count() == 0:
                raise PortalMudou("a lista da ALBA tem mais páginas, mas não tem o botão 'Próxima'")
            _, html, _ = await self._navegar(prox.click)
            linhas += ler_lista(html)
            pagina += 1
            if pagina > 200:
                raise PortalMudou("a paginação da ALBA não termina")
        nomes_na_lista = {l["deputado"] for l in linhas}
        n_notas = 0
        for l in linhas:
            detalhe = self.absoluto(l["detalhe"])
            await self.ir(detalhe, wait_until="domcontentloaded")
            html_d = await self.pagina.content()
            hd = guardar_original(self.con, self.id, trecho(html_d).encode("utf-8"), detalhe, "html")
            notas = ler_detalhe(html_d)
            escopo = f"{did}-{ano}-{l['id']}"
            soma = Decimal(0)
            lidas = 0
            for j, n in enumerate(notas):
                n_notas += 1
                proc = self.procedencia(detalhe, hd, f"processo {l['processo']}, nota {n['nota']}")
                chave = chave_hash(self.id, l["id"], j, n["nota"], n["documento"], n["valor_texto"])
                try:
                    valor = dinheiro_br(n["valor_texto"])
                    glosa = dinheiro_br(n["glosa_texto"]) if n["glosa_texto"].strip() else Decimal(0)
                except ValorIlegivel as e:
                    res.pendencias.append(Pendencia(fonte=self.id, chave=chave, motivo="valor ilegível",
                                                    texto_original=f"{nome} processo {l['processo']}: {e}", procedencia=proc))
                    continue
                soma += valor
                lidas += 1
                mes, _, ano_c = l["competencia"].partition("/")
                competencia = f"{ano_c}-{mes.zfill(2)}" if ano_c.isdigit() and mes.isdigit() else f"{ano}-01"
                res.despesas.append(self.nota(
                    chave=chave, item=item.chave, ref=ref, nome=titulo_nome(nome), data=None, competencia=competencia,
                    categoria=n["categoria"] or l["categoria"], documento=n["documento"], fornecedor=n["fornecedor"],
                    valor=valor - glosa, proc=proc,
                    documento_url=self.absoluto(n["anexo"], detalhe) if n["anexo"] else None,
                    extra={"processo": l["processo"], "nf": n["nota"], "valor_apresentado": str(valor), "glosa": str(glosa),
                           "id_detalhe": l["id"], "competencia_na_fonte": l["competencia"], "escopos_conferencia": [escopo],
                           **({"competencia_ilegivel": True} if not (ano_c.isdigit() and mes.isdigit()) else {})}))
            try:
                valor_lista: Decimal | None = dinheiro_br(l["valor_texto"])
            except ValorIlegivel:
                valor_lista = None
            conf.conferir(escopo, valor_lista, soma, proc_lista, f"{nome}, processo {l['processo']} NF {l['nf']}: valor da lista × detalhe",
                          lidas_todas=lidas == len(notas), outra=(len(notas) > 0, "o detalhe veio sem nota"))
        res.totais.append(TotalOficial(fonte=self.id, escopo=item.chave, metrica="linhas_da_lista", valor=str(len(linhas)),
                                       texto_original=f"{ultima + 1} página(s)", procedencia=proc_lista))
        conf.fechar(res, n_notas, proc_lista, f"{len(linhas)} linhas na lista")
        if linhas:
            res.pessoas.append(PessoaFonte(fonte=self.id, ref=ref, periodo=str(ano), nome=titulo_nome(nome), uf="BA", casa=self.ent.casa,
                                           matricula=did, extra={"grafias_na_fonte": sorted({nome} | nomes_na_lista),
                                                                 "id_de": "valor do deputado no select da consulta", "partido_de": None},
                                           procedencia=proc_lista))
        return res

