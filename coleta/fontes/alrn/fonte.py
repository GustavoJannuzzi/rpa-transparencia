"""Assembleia do Rio Grande do Norte: as cotas parlamentares pela tela do app Angular.

O caminho, visto em 26/11/2026 em `transparencia.al.rn.leg.br/verbas`:
- os filtros são `mat-select` do Angular Material (não são `<select>`: abrem um painel
  fora do componente), para legislatura, ano, meses e parlamentares; "PESQUISAR" mostra
  a frase "os parlamentares utilizaram um total de R$ …" e as abas "Gráficos" e
  "Tabela" (paginada de 10 em 10: 3.193 linhas em 2026);
- os dados vêm de `api-transparencia.al.rn.leg.br`, que responde 401 a quem não é o
  app e leva parâmetros anti-cache aleatórios. O robô não tenta reproduzir isso: ele
  usa a tela, e lê a resposta que a própria tela recebe ao pesquisar (as linhas, a
  contagem e a soma).

A conferência é da tela contra a resposta: a contagem e a soma da resposta batem com
as linhas; a soma é a da frase da tela; o paginador ("1 – 100 de N") diz N; e a
tabela, lida página a página, mostra as mesmas linhas (deputado, data, documento,
valor). O total de cada categoria que a resposta traz (`dadosEditorias`) também
fecha com as linhas.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from ...modelo import Descoberta, ItemInventario, Pendencia, PessoaFonte, Resultado, TotalOficial
from ...nucleo.erros import FalhaTransitoria, PortalMudou
from ...nucleo.texto import ValorIlegivel, chave_hash, decimal_ponto, dinheiro_br, sem_acento, so_digitos
from ..assembleia_tela import Conferencias, FonteAssembleiaTela

CAMPOS = {"id", "data", "cnpj", "cpf", "fornecedor", "mes_id", "deputado", "valor", "nome_categoria", "numero"}
RE_TOTAL = re.compile(r"utilizaram um total de\s*R\$\s*([\d.]+,\d{2})")
RE_RANGE = re.compile(r"(\d+)\s*[–-]\s*(\d+)\s+de\s+(\d+)")


def centavos(v) -> Decimal:
    """O que vem em float na resposta (7215827.399999997) em centavos exatos."""
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def ler_despesas(j: dict) -> dict:
    if not isinstance(j, dict) or not {"data", "count", "somatorio"} <= set(j):
        raise PortalMudou("a resposta das despesas da ALRN veio em outro formato")
    for x in j["data"][:50]:
        faltam = CAMPOS - set(x)
        if faltam:
            raise PortalMudou(f"linha da ALRN sem os campos {sorted(faltam)}")
    return j


def chave_tela(parlamentar: str, data_txt: str, doc: str, valor_txt: str) -> tuple[str, str, str, str]:
    """Uma linha como a tabela da tela mostra, para comparar com a resposta."""
    return (sem_acento(parlamentar).upper().strip(), data_txt.strip(), so_digitos(doc), valor_txt.replace("R$", "").strip())


def chave_resposta(x: dict) -> tuple[str, str, str, str]:
    d = x.get("data") or ""
    data_txt = f"{d[8:10]}/{d[5:7]}/{d[:4]}" if len(d) >= 10 else ""
    v = centavos(x["valor"])
    inteiro, _, frac = f"{v:.2f}".partition(".")
    valor_txt = f"{int(inteiro):,}".replace(",", ".") + "," + frac
    return (sem_acento((x.get("deputado") or {}).get("nome") or "").upper().strip(), data_txt, so_digitos(x.get("cnpj") or x.get("cpf")), valor_txt)


class Alrn(FonteAssembleiaTela):
    inicio = "https://transparencia.al.rn.leg.br/verbas"
    o_que_tem = ("Cota parlamentar de cada deputado estadual, nota a nota, com o fornecedor e o CNPJ, lida na tela do app (a API da casa "
                 "não responde fora dele), conferida contra a tabela paginada e o total que a tela escreve.")

    async def _mat(self, controle: str, texto: str) -> None:
        """Escolhe uma opção num mat-select: abre o painel e clica na opção pelo texto."""
        assert self.pagina is not None
        gatilho = self.pagina.locator(f"mat-select[formcontrolname='{controle}']")
        if await gatilho.count() == 0:
            raise PortalMudou(f"a tela da ALRN não tem mais o filtro {controle}")
        if texto.lower() in (await gatilho.inner_text()).lower():
            return
        await gatilho.click()
        opcao = self.pagina.locator("mat-option", has_text=texto).first
        try:
            await opcao.wait_for(timeout=15000)
        except Exception as e:
            raise PortalMudou(f"o filtro {controle} da ALRN não tem a opção {texto!r}") from e
        await self.gesto(opcao.click)
        if await self.pagina.locator(".cdk-overlay-pane mat-option").count():
            await self.pagina.keyboard.press("Escape")

    async def _opcoes(self, controle: str) -> list[str]:
        assert self.pagina is not None
        await self.pagina.locator(f"mat-select[formcontrolname='{controle}']").click()
        await self.pagina.locator("mat-option").first.wait_for(timeout=15000)
        textos = [t.strip() for t in await self.pagina.locator("mat-option").all_inner_texts()]
        await self.pagina.keyboard.press("Escape")
        await self.pagina.locator(".cdk-overlay-pane mat-option").first.wait_for(state="detached", timeout=10000)
        return textos

    def __init__(self, ent) -> None:
        super().__init__(ent)
        self._meses: dict[int, list] = {}
        self._ouvindo = False

    def ao_renovar(self) -> None:
        self._ouvindo = False

    def _ao_responder(self, r) -> None:
        m = re.search(r"/verbas/meses/(\d{4})", r.url)
        if m and r.status == 200:
            self._meses.setdefault(int(m.group(1)), []).append(r)

    async def _meses_do_ano(self, ano: int) -> dict[str, int]:
        """id do mês na fonte -> mês, pela resposta que a tela recebeu ao escolher o ano."""
        for r in reversed(self._meses.get(ano, [])):
            try:
                j = json.loads(await r.body())
            except Exception:
                continue
            out = {}
            for m in j if isinstance(j, list) else []:
                if isinstance(m, dict) and "id" in m and "mes" in m and str(m["mes"]).isdigit():
                    out[str(m["id"])] = int(m["mes"])
            if out:
                return out
        return {}

    async def _abrir(self) -> None:
        assert self.pagina is not None
        if not self._ouvindo:
            self.pagina.on("response", self._ao_responder)
            self._ouvindo = True
        await self.ir(self.inicio, wait_until="networkidle")
        await self.pagina.locator("mat-select[formcontrolname='anoControl']").wait_for(timeout=30000)

    async def descobrir(self) -> Descoberta:
        await self._abrir()
        itens = []
        legislaturas = await self._opcoes("legislaturasControl")
        for leg in legislaturas:
            numero = re.match(r"(\d+)ª", leg)
            if not numero:
                continue
            await self._mat("legislaturasControl", leg.split(" (")[0].strip())
            for ano_txt in await self._opcoes("anoControl"):
                if ano_txt.isdigit() and self.de <= int(ano_txt) <= self.ate:
                    itens.append(ItemInventario(chave=f"cotas-{numero.group(1)}-{ano_txt}", descricao=f"Cotas de {ano_txt} na {leg.split(' (')[0]}",
                                                periodo=ano_txt, parametros={"legislatura": leg.split(" (")[0].strip(), "ano": int(ano_txt)}))
        return Descoberta(itens=itens)

    async def coletar_item(self, item: ItemInventario) -> Resultado:
        self.disco()
        assert self.pagina is not None
        p = item.parametros
        leg, ano = str(p["legislatura"]), int(p["ano"])
        res = Resultado()
        conf = Conferencias(self.id, item.chave)
        await self._abrir()
        await self._mat("legislaturasControl", leg)
        await self._mat("anoControl", str(ano))
        r, corpo, h = await self.gesto(self.pagina.get_by_role("button", name="PESQUISAR").click, lambda r: "/verbas/despesas/" in r.url,
                                       tipo="json")
        meses_resp = await self._meses_do_ano(ano)
        assert r is not None and h is not None
        if r.status == 401:
            raise FalhaTransitoria("a API da ALRN recusou o pedido da própria tela (401)")
        j = ler_despesas(json.loads(corpo))
        proc = self.procedencia(r.url, h, f"resposta da pesquisa de {ano} na {leg}")
        linhas = j["data"]
        # 1. a resposta: contagem e soma × as linhas; os totais por categoria × as linhas
        soma = sum((decimal_ponto(x["valor"]) for x in linhas), Decimal(0))
        por_cat: dict[str, Decimal] = {}
        for x in linhas:
            por_cat[str(x.get("editoria_id"))] = por_cat.get(str(x.get("editoria_id")), Decimal(0)) + decimal_ponto(x["valor"])
        cats_ok = all(centavos(e["totalValor"]) == por_cat.get(str(e["DeputadosVerbasGabinete_editoria_id"]), Decimal(0))
                      for e in j.get("dadosEditorias") or [])
        # 2. a tela: a frase do total e o paginador
        await self.pagina.locator("text=utilizaram um total de").first.wait_for(timeout=30000)
        frase = RE_TOTAL.search(await self.pagina.inner_text("body"))
        total_frase = dinheiro_br(frase.group(1)) if frase else None
        na_tabela = await self._ler_tabela()
        da_resposta = Counter(chave_resposta(x) for x in linhas)
        faltam = sum((da_resposta - na_tabela["linhas"]).values())
        sobram = sum((na_tabela["linhas"] - da_resposta).values())
        conf.conferir(item.chave, total_frase, soma, proc, f"{ano} na {leg}: total escrito na tela × soma das linhas",
                      outra=(int(j["count"]) == len(linhas) == na_tabela["n"] and centavos(j["somatorio"]) == soma and cats_ok
                             and not faltam and not sobram,
                             f"resposta: count {j['count']}, somatório {centavos(j['somatorio'])}, {len(linhas)} linhas; paginador {na_tabela['n']}; "
                             f"categorias {'fecham' if cats_ok else 'não fecham'}; {faltam} linha(s) só na resposta, {sobram} só na tabela"))
        pessoas: dict[int, str] = {}
        for k, x in enumerate(linhas):
            dep = x.get("deputado") or {}
            did, nome = int(dep.get("id") or x.get("deputado_id")), (dep.get("nome") or "").strip()
            pessoas[did] = nome
            pr = self.procedencia(r.url, h, f"linha {k + 1} (id {x['id']})")
            chave = chave_hash(self.id, x["id"], x.get("numero"), x.get("valor"))
            try:
                valor = decimal_ponto(x["valor"])
            except ValorIlegivel as e:
                res.pendencias.append(Pendencia(fonte=self.id, chave=chave, motivo="valor ilegível", texto_original=f"{nome}: {e}", procedencia=pr))
                continue
            try:
                quando = date.fromisoformat(x["data"][:10]) if x.get("data") else None
            except ValueError:
                quando = None
            mes = meses_resp.get(str(x.get("mes_id"))) or (quando.month if quando else None)
            competencia = f"{ano}-{mes:02d}" if mes else f"{ano}-01"
            res.despesas.append(self.nota(
                chave=chave, item=item.chave, ref=f"id:{did}", nome=nome, data=quando, competencia=competencia,
                categoria=(x.get("nome_categoria") or "").strip(), documento=x.get("cnpj") or x.get("cpf"), fornecedor=x.get("fornecedor"),
                valor=valor, proc=pr,
                extra={"numero": x.get("numero"), "titulo_na_fonte": (x.get("titulo") or "").strip() or None, "mes_id": x.get("mes_id"),
                       "id_na_fonte": x["id"], "escopos_conferencia": [item.chave],
                       **({} if mes and str(x.get("mes_id")) in meses_resp else {"competencia_pela_data": True})}))
        conf.fechar(res, len(linhas), proc, f"count {j['count']}")
        for did, nome in pessoas.items():
            res.pessoas.append(PessoaFonte(fonte=self.id, ref=f"id:{did}", periodo=str(ano), nome=nome, uf="RN", casa=self.ent.casa,
                                           matricula=str(did), extra={"partido_de": None, "legislatura": leg}, procedencia=proc))
        res.totais.append(TotalOficial(fonte=self.id, escopo=item.chave, metrica="total_escrito_na_tela", valor=str(total_frase),
                                       texto_original=frase.group(0) if frase else None, procedencia=proc))
        return res

    async def _ler_tabela(self) -> dict:
        """A aba Tabela, com o maior tamanho de página que o paginador oferece, página a página."""
        assert self.pagina is not None
        await self.pagina.get_by_role("tab", name="Tabela").click()
        tabela = self.pagina.locator("table").first
        await tabela.wait_for(timeout=30000)
        tamanho = self.pagina.locator("mat-paginator mat-select").first
        if await tamanho.count():
            await tamanho.click()
            opcoes = [t.strip() for t in await self.pagina.locator("mat-option").all_inner_texts()]
            maior = max((o for o in opcoes if o.isdigit()), key=int, default=None)
            if maior:
                await self.pagina.locator("mat-option", has_text=maior).last.click()
            else:
                await self.pagina.keyboard.press("Escape")
        rotulo = (await self.pagina.locator(".mat-mdc-paginator-range-label").first.inner_text()).strip()
        m = RE_RANGE.search(rotulo)
        if not m:
            raise PortalMudou(f"o paginador da ALRN mudou: {rotulo!r}")
        n = int(m.group(3))
        cab = [t.strip().upper() for t in await tabela.locator("thead th").all_inner_texts()]
        if cab[:6] != ["PARLAMENTAR", "DATA", "CNPJ / CPF", "FORNECEDOR", "CATEGORIA", "VALOR"]:
            raise PortalMudou(f"a tabela da ALRN mudou as colunas: {cab}")
        linhas: Counter = Counter()
        paginas = 0
        while True:
            for cel in await tabela.evaluate("t => Array.from(t.tBodies[0]?.rows || []).map(r => Array.from(r.cells).map(c => c.innerText.trim()))"):
                if len(cel) >= 6:
                    linhas[chave_tela(cel[0], cel[1], cel[2], cel[5])] += 1
            proxima = self.pagina.get_by_role("button", name="Próxima página")
            if await proxima.count() == 0 or await proxima.is_disabled():
                break
            await proxima.click()
            paginas += 1
            if paginas > 2000:
                raise PortalMudou("a paginação da tabela da ALRN não termina")
        return {"n": n, "linhas": linhas, "paginas": paginas + 1}
