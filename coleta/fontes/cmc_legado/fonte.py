"""Câmara de Curitiba, sistema legado (até 2016): robô de navegador + PDF.

O portal é uma aplicação React em que cada relatório é um botão que gera um PDF.
Abrir a subpágina direto não funciona; o caminho é clicar no menu, como uma
pessoa faria. O robô clica no botão, captura o download, guarda o PDF com hash e
lê a tabela.
"""

from __future__ import annotations

import asyncio
import re

from ... import config
from ...modelo import Descoberta, Despesa, ItemInventario, Pendencia, PessoaFonte, Resultado, SistemaOrigem, TotalOficial
from ...nucleo.erros import FalhaTransitoria, PortalMudou
from ...nucleo.evidencia import guardar_original
from ...nucleo.texto import chave_hash, normalizar_nome
from ..base import FonteNavegador
from .parser import RelatorioDiarias, ler_pdf

INICIO = "https://transparencia-legada.cmc.pr.gov.br/"
API_DOWNLOAD = "https://transparencia-legada.cmc.pr.gov.br:3000/api/download/"
MENU = "RECEITAS E DESPESAS"
RE_BOTAO = re.compile(r"Relat[oó]rio de Di[aá]rias de Custo\s*-\s*(\d{4})")


class CmcLegado(FonteNavegador):
    id = "cmc_legado"
    ua = config.UA_ROBO
    sistema = SistemaOrigem(
        fonte="cmc_legado", casa="cmc", sistema="Portal legado da Câmara", fornecedor="sistema próprio (legado)",
        modo="robo_pdf", cobre_de=2013, cobre_ate=2016, endereco=INICIO,
        o_que_tem="Diárias de vereadores e servidores (2013–2016) em relatórios PDF gerados por botão.",
    )

    async def _abrir_menu(self) -> None:
        assert self.pagina is not None
        await self.ir(INICIO, wait_until="networkidle")
        link = self.pagina.get_by_role("link", name=MENU).first
        if await link.count() == 0:
            raise PortalMudou(f"o menu '{MENU}' sumiu da página inicial")
        await link.click()
        try:
            await self.pagina.get_by_role("button", name=RE_BOTAO).first.wait_for(timeout=20000)
        except Exception as e:
            raise PortalMudou("a página de Receitas e Despesas abriu sem os botões de diárias") from e

    async def descobrir(self) -> Descoberta:
        await self._abrir_menu()
        assert self.pagina is not None
        textos = await self.pagina.get_by_role("button").all_inner_texts()
        anos = sorted({int(m.group(1)) for t in textos if (m := RE_BOTAO.search(t))})
        if not anos:
            raise PortalMudou("nenhum botão 'Relatório de Diárias de Custo' na página")
        h = guardar_original(self.con, self.id, (await self.pagina.content()).encode("utf-8"), self.pagina.url, "html")
        proc = self.procedencia(self.pagina.url, h, "lista de botões de relatório")
        itens = [ItemInventario(chave=f"diarias-{a}", descricao=f"Relatório de Diárias de Custo - {a}", periodo=str(a),
                                parametros={"ano": a, "botao": f"Relatório de Diárias de Custo - {a}"}) for a in anos]
        totais = [TotalOficial(fonte=self.id, escopo="inventario", metrica="relatorios_de_diarias", valor=str(len(anos)),
                               texto_original=", ".join(map(str, anos)), procedencia=proc)]
        return Descoberta(itens=itens, totais=totais)

    async def coletar_item(self, item: ItemInventario) -> Resultado:
        assert self.pagina is not None
        ano = int(item.parametros["ano"])
        await self._abrir_menu()
        botao = self.pagina.get_by_role("button", name=re.compile(rf"Di[aá]rias de Custo\s*-\s*{ano}"))
        if await botao.count() != 1:
            raise PortalMudou(f"esperava 1 botão de diárias {ano}, achei {await botao.count()}")

        await self.educacao.verificar_robots(API_DOWNLOAD, self.http)
        async with self.educacao.vez(API_DOWNLOAD):
            # O que vier primeiro: o download, ou um alerta da aplicação ("Sua sessão
            # expirou.", "Arquivo não disponível."). Alerta é falha de verdade, e o
            # robô recomeça do início em vez de esperar um download que não vem.
            baixou = asyncio.ensure_future(self.pagina.wait_for_event("download", timeout=60000))
            alertou = asyncio.ensure_future(self.pagina.wait_for_event("dialog", timeout=60000))
            await botao.click()
            pronto, _ = await asyncio.wait({baixou, alertou}, return_when=asyncio.FIRST_COMPLETED)
            for t in (baixou, alertou):
                if t not in pronto:
                    t.cancel()
            if alertou in pronto and not alertou.exception():
                d = alertou.result()
                msg = d.message
                try:
                    await d.dismiss()
                except Exception:
                    pass
                raise FalhaTransitoria(f"o portal avisou: {msg}")
            if baixou.exception():
                raise FalhaTransitoria(f"o download do relatório {ano} não veio: {type(baixou.exception()).__name__}")
            download = baixou.result()
        caminho = await download.path()
        if caminho is None:
            raise FalhaTransitoria(f"download do relatório {ano} falhou: {await download.failure()}")
        conteudo = open(caminho, "rb").read()
        if not conteudo.startswith(b"%PDF"):
            raise PortalMudou(f"o botão de {ano} devolveu algo que não é PDF ({conteudo[:20]!r})")
        url = API_DOWNLOAD + download.suggested_filename
        h = guardar_original(self.con, self.id, conteudo, url, "pdf")
        rel = ler_pdf(conteudo, ano)
        return self._resultado(rel, item, url, h)

    def _resultado(self, rel: RelatorioDiarias, item: ItemInventario, url: str, h: str) -> Resultado:
        r = Resultado()
        vistos: dict[str, int] = {}
        for l in rel.linhas:
            local = f"página {l.pagina}, linha {l.linha} da tabela"
            base = chave_hash(self.id, rel.ano, l.portaria, l.cargo, l.periodo_original, l.valor_total_original,
                              l.beneficiario or "", l.matricula or "")
            n = vistos.get(base, 0)
            vistos[base] = n + 1
            chave = chave_hash(base, n)
            if l.valor_total is None or l.ilegivel:
                r.pendencias.append(Pendencia(
                    fonte=self.id, chave=chave, motivo=l.ilegivel or "valor ilegível",
                    texto_original=f"portaria '{l.portaria}', cargo '{l.cargo}', valor '{l.valor_total_original}'",
                    procedencia=self.procedencia(url, h, local)))
                continue
            data = l.data_inicio
            mes = l.competencia_bloco or (data.month if data else (l.data_portaria.month if l.data_portaria else None))
            if mes is None:
                r.pendencias.append(Pendencia(
                    fonte=self.id, chave=chave, motivo="sem mês: período e portaria ilegíveis e sem bloco de total",
                    texto_original=f"portaria '{l.portaria}', período '{l.periodo_original}'",
                    procedencia=self.procedencia(url, h, local)))
                continue
            ref = None
            if l.parlamentar:
                ref = f"mat:{l.matricula}" if l.matricula else f"nome:{normalizar_nome(l.beneficiario)}"
            r.despesas.append(Despesa(
                chave=chave, fonte=self.id, item=item.chave, tipo="diaria_municipal",
                ref_parlamentar=ref, beneficiario_tipo="parlamentar" if l.parlamentar else "servidor",
                nome_beneficiario=l.beneficiario, cargo_original=l.cargo,
                data=data, competencia=f"{rel.ano}-{mes:02d}", ano=rel.ano,
                categoria_original="Diária", valor=l.valor_total,
                documento_url=url,
                descricao=(f"{l.destino} — {l.evento}" if l.parlamentar and l.evento else l.destino) or None,
                procedencia=self.procedencia(url, h, local),
                extra={
                    "portaria": l.portaria, "periodo_original": l.periodo_original,
                    "qtde_original": l.qtde_original, "valor_unit_original": l.valor_unit_original,
                    "consistencia": l.consistencia, "marcas": l.marcas, "nota_data": l.nota_data,
                    "competencia_do_bloco": l.competencia_bloco is not None,
                    "hospedagem": str(l.hospedagem) if l.hospedagem is not None else None,
                    "transporte": str(l.transporte) if l.transporte is not None else None,
                    "meio_transporte": l.meio_transporte,
                    "dom": l.dom,
                },
            ))
            if l.parlamentar:
                r.pessoas.append(PessoaFonte(
                    fonte=self.id, ref=ref, periodo=str(rel.ano), nome=l.beneficiario, matricula=l.matricula,
                    casa="cmc", procedencia=self.procedencia(url, h, local)))
        proc = self.procedencia(url, h, "linhas de total do PDF")
        for t in rel.totais:
            for metrica, v in (("valor_diarias", t.diarias), ("valor_hospedagem", t.hospedagem), ("valor_transporte", t.transporte)):
                if v is not None:
                    r.totais.append(TotalOficial(fonte=self.id, escopo=t.escopo, metrica=metrica, valor=str(v),
                                                 texto_original=t.texto, procedencia=proc))
        r.totais.append(TotalOficial(fonte=self.id, escopo=str(rel.ano), metrica="linhas_lidas",
                                     valor=str(len(rel.linhas)), texto_original=f"{rel.paginas} página(s), colunas {rel.colunas}",
                                     procedencia=proc))
        return r
