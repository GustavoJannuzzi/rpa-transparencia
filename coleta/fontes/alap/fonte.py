"""Assembleia do Amapá: a CEAP (cota parlamentar) pela tela, no navegador.

O caminho, visto em 26/11/2026 em `pagina.php?pg=ceap`:
- três selects em cascata: o ano está no HTML; ao escolher o ano, a página pede os
  meses (`mes_ceap_json.php`, AJAX); ao escolher o mês, os gabinetes
  (`gabinete_ceap_json.php`, "NOME - PARTIDO" com um id numérico);
- "Consultar" faz um POST e a página volta com o total do mês por elemento de
  despesa ("3390.30.01 - Combustíveis e Lubrificantes Automotivos"), o TOTAL do mês e
  o histórico do ano, mês a mês, com o saldo e os meses complementares
  ("Setembro/2025 (compl.)");
- cada "ver detalhes" abre um modal com um iframe
  (`ceap_exibir_detalhado.php`) com as notas daquele elemento: "CNPJ - RAZÃO
  SOCIAL", objeto, número da NF ou cupom (com o link do documento digitalizado) e
  valor, mais o TOTAL.

A conferência tem três degraus, todos com números da própria tela: as notas de
cada elemento somam o valor do elemento (e o TOTAL do iframe); os elementos somam o
TOTAL do mês; e o TOTAL do mês é o do histórico do ano, com o complementar somado
(o POST do mês já traz o complementar junto). O `robots.txt` responde 403 (sem
política legível): o robô pede no piso de pausa do projeto, uma coisa por vez.
"""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

from ...modelo import Descoberta, ItemInventario, Pendencia, PessoaFonte, Resultado, TotalOficial
from ...nucleo.erros import FalhaTransitoria, PortalMudou
from ...nucleo.texto import ValorIlegivel, chave_hash, dinheiro_br
from ..assembleia_tela import Conferencias, FonteAssembleiaTela, decodificar, separar_partido, tabelas_html, texto_html, titulo_nome

MESES = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
RE_HISTORICO = re.compile(r"(Janeiro|Fevereiro|Mar[çc]o|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)/(\d{4})"
                          r"\s*(\(compl\.\))?\s*R\$\s*(-?[\d.]+,\d{2})\s*Saldo:\s*R\$\s*(-?[\d.]+,\d{2})", re.I)
RE_EMPRESA = re.compile(r"^\s*([\d][\d./-]{9,19}\d)\s*-\s*(.+)$", re.S)
RE_ELEMENTO = re.compile(r"^\s*(\d{4}\.\d{2}\.\d{2})\s*-\s*(.+)$", re.S)
RE_OPCAO = re.compile(r"<option\s+value=\"([^\"]*)\"[^>]*>([^<]*)", re.I)


def opcoes(html: str) -> list[tuple[str, str]]:
    """As opções de um <select> que a página recebe por AJAX, sem a vazia."""
    from html import unescape

    return [(v, re.sub(r"\s+", " ", unescape(t)).strip()) for v, t in RE_OPCAO.findall(html) if v]


def _mes_num(nome: str) -> int:
    from ...nucleo.texto import sem_acento

    return MESES.index(sem_acento(nome).lower()) + 1


def ler_resultado(html: str) -> dict:
    """A página do POST: elementos do mês (rótulo, valor, link do detalhe), TOTAL do
    mês e o histórico do ano. Sem a tabela, a casa não publicou nada no mês."""
    elementos: list[dict] = []
    total: Decimal | None = None
    achou = False
    for t in tabelas_html(html):
        cab = [c.texto.upper() for c in (t[0] if t else [])]
        if not (cab and cab[0].startswith("DESPESAS") and any("VALOR" in c for c in cab)):
            continue
        achou = True
        for linha in t[1:]:
            if not linha:
                continue
            primeira = linha[0].texto.strip().upper()
            if primeira == "TOTAL" and len(linha) >= 2:
                total = dinheiro_br(linha[1].texto)
                continue
            links = [h for c in linha for h in c.links if "ceap_exibir_detalhado" in h]
            if not links or len(linha) < 2:
                raise PortalMudou(f"linha da tabela de elementos da ALAP sem o link do detalhe: {[c.texto for c in linha]}")
            m = RE_ELEMENTO.match(linha[0].texto)
            if not m:
                raise PortalMudou(f"elemento de despesa da ALAP fora do formato 'código - nome': {linha[0].texto!r}")
            elementos.append({"elemento": m.group(1), "nome": re.sub(r"\s+", " ", m.group(2)).strip(), "valor_texto": linha[1].texto,
                              "href": links[0]})
    texto = texto_html(html)
    historico: dict[tuple[int, int], dict[str, Decimal]] = defaultdict(dict)
    for nome_mes, ano, compl, valor, _saldo in RE_HISTORICO.findall(texto):
        historico[(int(ano), _mes_num(nome_mes))]["complementar" if compl else "regular"] = dinheiro_br(valor)
    m = re.search(r"Ref\.:\s*DEP\.\s*(.+?)\s*\((\w+)/(\d{4})\)", texto)
    return {"tem_tabela": achou, "elementos": elementos, "total": total, "historico": dict(historico),
            "ref": m.group(1).strip() if m else None, "mes_ref": (int(m.group(3)), _mes_num(m.group(2))) if m else None,
            "sem_registro": not achou and bool(re.search(r"nenhum|n[ãa]o h[áa]|sem (registro|despesa)", texto, re.I))}


def ler_detalhe(html: str) -> dict:
    """O iframe de um elemento: as notas (empresa com CNPJ, objeto, NF, valor) e o TOTAL."""
    notas: list[dict] = []
    total: Decimal | None = None
    achou = False
    for t in tabelas_html(html):
        cab = [c.texto.upper() for c in (t[0] if t else [])]
        if not (cab and cab[0].startswith("EMPRESA") and any("VALOR" in c for c in cab)):
            continue
        achou = True
        if len(cab) < 4:
            raise PortalMudou(f"tabela de notas da ALAP com {len(cab)} colunas: {cab}")
        for linha in t[1:]:
            if not linha:
                continue
            if linha[0].texto.strip().upper() == "TOTAL":
                total = dinheiro_br(linha[-1].texto)
                continue
            if len(linha) < 4:
                raise PortalMudou(f"nota da ALAP com {len(linha)} colunas: {[c.texto for c in linha]}")
            empresa = re.sub(r"\s+", " ", linha[0].texto).strip()
            m = RE_EMPRESA.match(empresa)
            doc, nome = (m.group(1), m.group(2).strip()) if m else (None, empresa)
            nf = linha[2].texto.strip()
            digitalizado = next((h for h in linha[2].links if "documento_digitalizado" in h), None)
            id_item = parse_qs(urlsplit(digitalizado).query).get("iditem_verba", [None])[0] if digitalizado else None
            notas.append({"empresa": empresa, "documento": doc, "fornecedor": nome, "objeto": re.sub(r"\s+", " ", linha[1].texto).strip(),
                          "nf": nf, "digitalizado": digitalizado, "id_item": id_item, "valor_texto": linha[3].texto})
    if not achou:
        raise PortalMudou("o detalhe do elemento da ALAP veio sem a tabela de notas")
    return {"notas": notas, "total": total}


class Alap(FonteAssembleiaTela):
    inicio = "https://www.al.ap.leg.br/transparencia/pagina.php?pg=ceap"
    o_que_tem = ("Cota para o exercício da atividade parlamentar (CEAP) de cada deputado estadual, nota a nota, com a empresa e o CNPJ, "
                 "lida na tela: elemento de despesa do mês e o detalhe de cada um.")

    # ---- os três selects -------------------------------------------------
    async def _ano(self, ano: int) -> list[tuple[str, str]]:
        assert self.pagina is not None
        _, corpo, _ = await self.gesto(lambda: self.pagina.select_option("#ano_verbaB", str(ano)),  # type: ignore[union-attr]
                                       lambda r: "mes_ceap_json.php" in r.url)
        meses = opcoes(decodificar(corpo))
        await self.pagina.wait_for_function(f"document.querySelectorAll('#mes_verbaB option[value]:not([value=\"\"])').length === {len(meses)}")
        return meses

    async def _mes(self, mes: str) -> list[tuple[str, str]]:
        assert self.pagina is not None
        _, corpo, _ = await self.gesto(lambda: self.pagina.select_option("#mes_verbaB", mes),  # type: ignore[union-attr]
                                       lambda r: "gabinete_ceap_json.php" in r.url)
        gabs = opcoes(decodificar(corpo))
        await self.pagina.wait_for_function(f"document.querySelectorAll('#idgabineteB option[value]:not([value=\"\"])').length === {len(gabs)}")
        return gabs

    async def _abrir(self) -> None:
        assert self.pagina is not None
        await self.ir(self.inicio, wait_until="domcontentloaded")
        if await self.pagina.locator("#ano_verbaB").count() == 0:
            raise PortalMudou("a página da CEAP da ALAP não tem mais o select de ano (#ano_verbaB)")

    async def descobrir(self) -> Descoberta:
        assert self.pagina is not None
        await self._abrir()
        anos = {v for v, _ in await self.pagina.eval_on_selector_all("#ano_verbaB option", "os => os.map(o => [o.value, o.textContent])") if v}
        gabinetes: dict[str, dict] = {}
        totais: list[TotalOficial] = []
        for ano in range(self.de, self.ate + 1):
            if str(ano) not in anos:
                continue
            for mes, _ in await self._ano(ano):
                gabs = await self._mes(mes)
                totais.append(TotalOficial(fonte=self.id, escopo=f"{ano}-{mes}", metrica="gabinetes_no_select", valor=str(len(gabs)),
                                           procedencia=self.procedencia(self.inicio, "", f"select de gabinete de {mes}/{ano}")))
                for gid, rotulo in gabs:
                    g = gabinetes.setdefault(gid, {"rotulos": set(), "meses": defaultdict(list)})
                    g["rotulos"].add(rotulo)
                    g["meses"][ano].append(mes)
        itens = []
        for gid, g in sorted(gabinetes.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
            for ano, meses in sorted(g["meses"].items()):
                rotulo = sorted(g["rotulos"])[-1]
                itens.append(ItemInventario(chave=f"ceap-{gid}-{ano}", descricao=f"CEAP de {rotulo} em {ano}", periodo=str(ano),
                                            parametros={"gabinete": gid, "rotulos": sorted(g["rotulos"]), "ano": ano, "meses": sorted(meses)}))
        return Descoberta(itens=itens, totais=totais)

    # ---- um gabinete num ano ----------------------------------------------
    async def coletar_item(self, item: ItemInventario) -> Resultado:
        assert self.pagina is not None
        p = item.parametros
        gid, ano = str(p["gabinete"]), int(p["ano"])
        ref = f"id:{gid}"
        res = Resultado()
        conf = Conferencias(self.id, item.chave)
        n_notas = 0
        rotulos: set[str] = set()
        primeira = None
        await self._abrir()
        await self._ano(ano)
        for mes in p["meses"]:
            gabs = dict(await self._mes(mes))
            if gid not in gabs:
                res.totais.append(TotalOficial(fonte=self.id, escopo=f"{gid}-{ano}-{mes}", metrica="mes_fora_da_lista", valor="1",
                                               texto_original="o gabinete não está mais no select deste mês",
                                               procedencia=self.procedencia(self.inicio, "")))
                continue
            rotulos.add(gabs[gid])
            await self.gesto(lambda: self.pagina.select_option("#idgabineteB", gid))  # type: ignore[union-attr]
            r, corpo, h = await self.gesto(lambda: self.pagina.click("#Consultar"),  # type: ignore[union-attr]
                                           lambda r: "acao=buscar" in r.url and r.request.method == "POST")
            assert r is not None and h is not None
            await self.pagina.wait_for_load_state("domcontentloaded")
            url_post = r.url
            pag = ler_resultado(decodificar(corpo))
            proc_mes = self.procedencia(url_post, h, f"{mes}/{ano}, gabinete {gid}")
            primeira = primeira or proc_mes
            if pag["mes_ref"] and pag["mes_ref"] != (ano, int(mes)):
                raise PortalMudou(f"a ALAP devolveu {pag['mes_ref']} para a consulta de {mes}/{ano}")
            if not pag["tem_tabela"]:
                # sem tabela: o histórico do ano tem de dizer zero (ou não ter o mês)
                hist = pag["historico"].get((ano, int(mes)), {})
                no_hist = sum(hist.values(), Decimal(0))
                conf.conferir(f"{gid}-{ano}-{mes}", Decimal(0), no_hist, proc_mes, f"{mes}/{ano} sem tabela, histórico {no_hist}")
                continue
            escopo_mes = f"{gid}-{ano}-{mes}"
            soma_mes = Decimal(0)
            n_elementos = len(pag["elementos"])
            botoes = self.pagina.locator("a.ls-btn.abrir-galeria-modal")
            if await botoes.count() != n_elementos:
                raise PortalMudou(f"a tela tem {await botoes.count()} botões 'ver detalhes' e {n_elementos} elementos na tabela")
            chaves_mes: list[int] = []
            for k, el in enumerate(pag["elementos"]):
                q = parse_qs(urlsplit(el["href"]).query)
                sub = (q.get("idsubelemento") or [""])[0]
                escopo_el = f"{gid}-{ano}-{mes}-{el['elemento']}-{sub}"
                try:
                    valor_el: Decimal | None = dinheiro_br(el["valor_texto"])
                except ValorIlegivel:
                    valor_el = None
                if valor_el is not None:
                    soma_mes += valor_el
                rd, corpo_d, hd = await self.gesto(botoes.nth(k).click, lambda r: "ceap_exibir_detalhado" in r.url)
                assert rd is not None and hd is not None
                det = ler_detalhe(decodificar(corpo_d))
                await self.pagina.frame_locator(".modal iframe").locator("table").first.wait_for(timeout=30000)
                await self.pagina.locator(".close").first.click()
                soma_el = Decimal(0)
                lidas = 0
                for j, n in enumerate(det["notas"]):
                    n_notas += 1
                    proc = self.procedencia(rd.url, hd, f"{el['elemento']}, nota {j + 1}")
                    chave = chave_hash(self.id, gid, ano, mes, el["elemento"], sub, n["id_item"], n["nf"], n["valor_texto"], j)
                    texto = f"{gabs[gid]}, {mes}/{ano}, {el['elemento']} {el['nome']}, nota {j + 1}: {n['empresa']} {n['valor_texto']}"
                    try:
                        valor = dinheiro_br(n["valor_texto"])
                    except ValorIlegivel as e:
                        res.pendencias.append(Pendencia(fonte=self.id, chave=chave, motivo="valor ilegível", texto_original=f"{texto} ({e})",
                                                        procedencia=proc))
                        continue
                    soma_el += valor
                    lidas += 1
                    chaves_mes.append(len(res.despesas))
                    res.despesas.append(self.nota(
                        chave=chave, item=item.chave, ref=ref, nome=titulo_nome(separar_partido(gabs[gid])[0]), data=None,
                        competencia=f"{ano}-{mes}", categoria=el["nome"], documento=n["documento"], fornecedor=n["fornecedor"],
                        valor=valor, proc=proc, descricao=n["objeto"] or None,
                        documento_url=self.absoluto(n["digitalizado"], rd.url) if n["digitalizado"] else None,
                        extra={"elemento": el["elemento"], "subelemento": sub, "nf": n["nf"] or None, "id_item": n["id_item"],
                               "valor_do_elemento": el["valor_texto"], "escopos_conferencia": [escopo_el, escopo_mes]}))
                conf.conferir(escopo_el, valor_el, soma_el, proc_mes, f"{mes}/{ano} {el['elemento']} {el['nome']}, valor do elemento × notas",
                              lidas_todas=lidas == len(det["notas"]),
                              outra=(det["total"] == soma_el, f"o TOTAL do detalhe dá {det['total']}"))
            # o mês: elementos somam o TOTAL; o TOTAL é o do histórico (regular + complementar)
            hist = pag["historico"].get((ano, int(mes)))
            no_hist = sum(hist.values(), Decimal(0)) if hist else None
            conf.conferir(escopo_mes, pag["total"], soma_mes, proc_mes, f"{mes}/{ano}, soma dos elementos × TOTAL do mês",
                          outra=(no_hist == pag["total"], f"o histórico do ano dá {no_hist} para o mês"))
            if hist and "complementar" in hist:
                for i in chaves_mes:
                    res.despesas[i].extra["mes_com_complementar"] = True
        proc_item = primeira or self.procedencia(self.inicio, "")
        conf.fechar(res, n_notas, proc_item, f"{len(p['meses'])} meses")
        if rotulos or p.get("rotulos"):
            todos = sorted(rotulos or set(p["rotulos"]))
            nome, partido = separar_partido(sorted(rotulos)[-1] if rotulos else todos[-1])
            res.pessoas.append(PessoaFonte(fonte=self.id, ref=ref, periodo=str(ano), nome=titulo_nome(nome), partido=partido, uf="AP",
                                           casa=self.ent.casa, matricula=gid,
                                           extra={"grafias_na_fonte": todos, "partido_de": "rótulo do gabinete no select da consulta da CEAP"},
                                           procedencia=proc_item))
        if n_notas == 0 and not res.pessoas:
            raise FalhaTransitoria("nenhum mês do gabinete respondeu")
        return res
