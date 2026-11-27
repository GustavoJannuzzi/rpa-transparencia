"""Assembleia de Pernambuco: a verba indenizatória (CEAP) pela tela do app React.

O caminho, visto em 26/11/2026 em `financas/verbas-indenizatorias`:
- quatro níveis, todos puxados pela própria tela: o select de deputado (163 nomes, de
  várias legislaturas, id numérico) e o de ano fazem a tela pedir os meses com
  prestação (`verbaindenizatoria-dep-meses.php`); escolher o mês faz a tela pedir os
  pedidos do mês (`verbaindenizatoria.php`, com `docid`, número e total) e, para
  cada pedido, as notas (`verbaindenizatorianotas.php?docid=`: rubrica, data, CNPJ,
  empresa e valor);
- a rubrica da nota é o `numero_categoria` da tabela de rubricas do ano
  (`verbaindenizatoria-rubricas.php`, com o teto de cada uma), que a tela mostra como
  título de cada nota ("ASSESSORIA JURÍDICA").

O select é controlado pelo React: trocar o valor por script não dispara a busca, então
o robô escolhe como uma pessoa (o Playwright dispara os eventos de verdade) e lê as
respostas que a tela recebe. A conferência é a soma das notas de cada pedido × o
total do pedido (o mesmo número que a tela mostra em "PEDIDO Nº 77 - R$ 59880.00").
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from decimal import Decimal

from ...modelo import Descoberta, ItemInventario, Pendencia, PessoaFonte, Resultado, TotalOficial
from ...nucleo.banco import agora
from ...nucleo.erros import FalhaTransitoria, PortalMudou
from ...nucleo.evidencia import guardar_original
from ...nucleo.texto import ValorIlegivel, chave_hash, data_br, decimal_ponto
from ..assembleia_tela import Conferencias, FonteAssembleiaTela

SERVICOS = "https://www.alepe.pe.gov.br/servicos/transparencia/adm"
CAMPOS_NOTA = {"rubrica", "data", "cnpj", "empresa", "valor"}
CAMPOS_PEDIDO = {"docid", "numero", "total"}


class Alepe(FonteAssembleiaTela):
    inicio = "https://transparencia.alepe.pe.gov.br/financas/verbas-indenizatorias"
    o_que_tem = ("Cota para o exercício da atividade parlamentar (CEAP) de cada deputado estadual, nota a nota, com a empresa e o CNPJ, "
                 "lida na tela (deputado, meses, pedidos e notas), com a rubrica de cada nota.")

    def __init__(self, ent) -> None:
        super().__init__(ent)
        self._respostas: list = []
        self._ouvindo = False

    def ao_renovar(self) -> None:
        self._ouvindo = False

    # ---- a tela e as respostas que ela recebe ----------------------------
    async def _abrir(self) -> list[tuple[str, str]]:
        assert self.pagina is not None
        if not self._ouvindo:
            self.pagina.on("response", self._ao_responder)
            self._ouvindo = True
        self._respostas.clear()
        await self.ir(self.inicio, wait_until="networkidle")
        if await self.pagina.locator("select#parlamentar").count() == 0 or await self.pagina.locator("select#ano").count() == 0:
            raise PortalMudou("a tela da verba da ALEPE não tem mais os selects de deputado e ano")
        opcoes = await self.pagina.eval_on_selector_all("select#parlamentar option", "os => os.map(o => [o.value, o.textContent.trim()])")
        return [(v, t) for v, t in opcoes if v]

    def _ao_responder(self, r) -> None:
        if "/servicos/transparencia/adm/" in r.url:
            self._respostas.append(r)

    async def _esperar(self, trecho: str, n: int = 1, timeout: float | None = None) -> list:
        """Espera `n` respostas cujo endereço tem `trecho` (chegadas depois do último gesto)."""
        limite = (timeout or self.timeout_resposta / 1000)
        passo = 0.1
        while limite > 0:
            achadas = [r for r in self._respostas if trecho in r.url]
            if len(achadas) >= n:
                return achadas
            await asyncio.sleep(passo)
            limite -= passo
        raise FalhaTransitoria(f"a tela não recebeu {n} resposta(s) de {trecho}")

    async def _json(self, r, tipo: str = "json"):
        if r.status >= 500 or r.status == 429:
            raise FalhaTransitoria(f"HTTP {r.status} em {r.url}")
        try:
            corpo = await r.body()
        except Exception as e:
            raise FalhaTransitoria(f"corpo indisponível em {r.url}") from e
        h = guardar_original(self.con, self.id, corpo, r.url, tipo)
        try:
            return json.loads(corpo or b"[]"), h
        except ValueError as e:
            raise PortalMudou(f"a ALEPE respondeu sem JSON em {r.url}") from e

    async def _escolher(self, seletor: str, valor: str, trecho: str, n: int = 1) -> list:
        """Escolhe no select (na vez do domínio) e espera as respostas que a tela pede."""
        assert self.pagina is not None
        if await self.pagina.eval_on_selector(seletor, "s => s.value") == valor:
            # já escolhido (o ano corrente vem marcado): a resposta veio ao abrir a página
            return await self._esperar(trecho, n)
        self._respostas.clear()
        async with self.educacao.vez(SERVICOS):
            await self.pagina.select_option(seletor, valor)
            return await self._esperar(trecho, n)

    async def _selecionar(self, seletor: str, valor: str) -> None:
        """Escolhe no select na vez do domínio, sem limpar as respostas já recebidas."""
        assert self.pagina is not None
        if await self.pagina.eval_on_selector(seletor, "s => s.value") == valor:
            return
        async with self.educacao.vez(SERVICOS):
            await self.pagina.select_option(seletor, valor)

    async def _deputado_no_ano(self, dep: str, ano: int) -> tuple[list[int], str, str]:
        """Escolhe o deputado e depois o ano, nessa ordem (a tela só pede os meses assim),
        e lê os meses com prestação que a tela recebe."""
        await self._selecionar("select#parlamentar", dep)
        await self._selecionar("select#ano", str(ano))
        r = (await self._esperar(f"dep-meses.php?dep={dep}&ano={ano}"))[-1]
        j, h = await self._json(r)
        return sorted(int(x["mes"]) for x in j), r.url, h

    # ---- inventário -----------------------------------------------------
    async def descobrir(self) -> Descoberta:
        assert self.pagina is not None
        deputados = await self._abrir()
        itens, totais = [], []
        hoje = agora()[:7]
        com_mes: dict[int, int] = {}
        for dep, nome in deputados:
            for ano in range(self.de, self.ate + 1):
                meses, _, _ = await self._deputado_no_ano(dep, ano)
                meses = [m for m in meses if f"{ano}-{m:02d}" <= hoje]
                if not meses:
                    continue
                com_mes[ano] = com_mes.get(ano, 0) + 1
                itens.append(ItemInventario(chave=f"ceap-{dep}-{ano}", descricao=f"CEAP de {nome} em {ano}", periodo=str(ano),
                                            parametros={"deputado": dep, "nome": nome, "ano": ano, "meses": meses}))
        for ano in range(self.de, self.ate + 1):
            totais.append(TotalOficial(fonte=self.id, escopo=str(ano), metrica="deputados_com_prestacao", valor=str(com_mes.get(ano, 0)),
                                       texto_original=f"de {len(deputados)} nomes no select",
                                       procedencia=self.procedencia(self.inicio, "", f"meses de cada deputado em {ano}")))
        return Descoberta(itens=itens, totais=totais)

    # ---- um deputado num ano --------------------------------------------
    async def coletar_item(self, item: ItemInventario) -> Resultado:
        self.disco()
        assert self.pagina is not None
        p = item.parametros
        dep, ano, nome = str(p["deputado"]), int(p["ano"]), str(p["nome"])
        ref = f"id:{dep}"
        res = Resultado()
        conf = Conferencias(self.id, item.chave)
        await self._abrir()
        meses, url_meses, h_meses = await self._deputado_no_ano(dep, ano)
        rubricas_j, _ = await self._json((await self._esperar(f"rubricas.php?ano={ano}"))[-1])
        rubricas = {int(x["numero_categoria"]): x["nome_categoria"] for x in rubricas_j}
        proc_item = self.procedencia(url_meses, h_meses, f"meses de {nome} em {ano}")
        n_notas = 0
        for mes in [m for m in p["meses"] if m in meses]:
            pedidos_r = await self._escolher("select#mes", str(mes), f"verbaindenizatoria.php?dep={dep}&ano={ano}&mes={mes}")
            pedidos, h_ped = await self._json(pedidos_r[0])
            for x in pedidos:
                faltam = CAMPOS_PEDIDO - set(x)
                if faltam:
                    raise PortalMudou(f"pedido da ALEPE sem os campos {sorted(faltam)}")
            docids = [str(x["docid"]) for x in pedidos]
            notas_r = await self._esperar("verbaindenizatorianotas.php", len(docids)) if docids else []
            por_doc = {}
            for r in notas_r:
                d = r.url.rsplit("docid=", 1)[-1].split("&")[0]
                por_doc[d] = r
            for ped in pedidos:
                doc = str(ped["docid"])
                if doc not in por_doc:
                    raise FalhaTransitoria(f"a tela não pediu as notas do pedido {doc}")
                notas, h_n = await self._json(por_doc[doc])
                url_n = por_doc[doc].url
                escopo = f"{dep}-{ano}-{mes:02d}-{doc}"
                soma = Decimal(0)
                lidas = 0
                for k, n in enumerate(notas):
                    faltam = CAMPOS_NOTA - set(n)
                    if faltam:
                        raise PortalMudou(f"nota da ALEPE sem os campos {sorted(faltam)}")
                    n_notas += 1
                    proc = self.procedencia(url_n, h_n, f"pedido {ped['numero']}, nota {k + 1}")
                    chave = chave_hash(self.id, doc, k, n.get("rubrica"), n.get("sequencial"), n.get("cnpj"), n.get("valor"))
                    try:
                        valor = decimal_ponto(n["valor"])
                    except ValorIlegivel as e:
                        res.pendencias.append(Pendencia(fonte=self.id, chave=chave, motivo="valor ilegível",
                                                        texto_original=f"{nome} {mes:02d}/{ano} pedido {ped['numero']}: {e}", procedencia=proc))
                        continue
                    try:
                        quando: date | None = data_br(n["data"]) if n.get("data") else None
                    except ValueError:
                        quando = None
                    rubrica = rubricas.get(int(n["rubrica"])) if str(n.get("rubrica") or "").isdigit() else None
                    soma += valor
                    lidas += 1
                    res.despesas.append(self.nota(
                        chave=chave, item=item.chave, ref=ref, nome=nome, data=quando, competencia=f"{ano}-{mes:02d}",
                        categoria=rubrica or "", documento=n["cnpj"], fornecedor=(n["empresa"] or "").strip().upper() or None, valor=valor,
                        proc=proc,
                        extra={"pedido": ped["numero"], "docid": doc, "rubrica": n.get("rubrica"), "sequencial": n.get("sequencial"),
                               "escopos_conferencia": [escopo], **({"rubrica_sem_nome": True} if rubrica is None else {})}))
                try:
                    total: Decimal | None = decimal_ponto(ped["total"])
                except ValorIlegivel:
                    total = None
                conf.conferir(escopo, total, soma, self.procedencia(pedidos_r[0].url, h_ped, f"pedido {ped['numero']}"),
                              f"{nome} {mes:02d}/{ano}, pedido {ped['numero']}: total do pedido × soma das notas",
                              lidas_todas=lidas == len(notas))
        conf.fechar(res, n_notas, proc_item, f"{len(p['meses'])} meses")
        res.pessoas.append(PessoaFonte(fonte=self.id, ref=ref, periodo=str(ano), nome=nome, uf="PE", casa=self.ent.casa, matricula=dep,
                                       extra={"partido_de": None, "id_de": "valor do deputado no select da tela"}, procedencia=proc_item))
        return res
