"""Assembleia do Tocantins: a verba indenizatória (CODAP) pela tela, com um PDF por mês.

O caminho, visto em 26/11/2026 em `transparencia/verbaIndenizatoria`:
- escolher o ano já envia o formulário (POST) e a página volta com os deputados
  daquele ano no select (o valor é o NOME, não um id: 24 nomes em 2026, 34 em 2023,
  com grafias que mudam de um ano para outro, "Deputado Gipão" e "Aldair da Costa
  Sousa (Gipão)");
- mês + deputado + "Pesquisar" (POST) devolve a tabela "Mês de referência |
  Descrição" com o link do PDF do mês (`transparencia/baixar?arquivo=
  transparencia_ano_2025_14_77019.PDF`; o "14" do meio é o mesmo para deputados
  diferentes, então não identifica ninguém: a identidade é o nome, normalizado, com
  a tabela de grafias para quem a casa escreve de dois jeitos);
- o PDF (texto, "Microsoft: Print To PDF" de uma planilha) traz uma linha por nota:
  item, tipo, número, data, emitente, CNPJ/CPF e valor, e uma coluna de SALDO
  corrido ao lado. O `pdftotext -layout` desalinha o saldo das notas; pelas
  coordenadas, cada nota tem o seu saldo na mesma altura. No fim, o quadro do mês:
  valor mensal, saldo do mês anterior, telefone, saldo atual, total das despesas e
  valor ressarcido.

A conferência é nota a nota: o saldo de cada linha é o saldo anterior menos o valor
da nota (começando do "Saldo Atual"); as notas somam o "Total das despesas"; o
saldo atual é o valor mensal mais o saldo anterior menos o telefone; e o ressarcido
é o total (se for menor, a casa glosou alguma nota e o PDF não diz qual).

O `robots.txt` pede `Crawl-delay: 10`, e o robô espera 10 s entre dois pedidos,
cliques e downloads incluídos. O PDF é lido e não fica guardado (são ~200 KB cada,
sem compressão possível): o original guardado é o texto com as coordenadas, com o
hash e o tamanho do PDF como veio.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from ...de_para import grafia
from ...modelo import Descoberta, ItemInventario, Pendencia, PessoaFonte, Resultado, TotalOficial
from ...nucleo.banco import agora
from ...nucleo.erros import FalhaTransitoria, PortalMudou
from ...nucleo.evidencia import guardar_original
from ...nucleo.texto import ValorIlegivel, chave_hash, data_br, dinheiro_br, normalizar_nome, sem_acento
from ..assembleia_tela import Conferencias, FonteAssembleiaTela, decodificar, tabelas_html, titulo_nome

CATEGORIA = "Cota Despesa de Atividade Parlamentar"
MESES = ["JANEIRO", "FEVEREIRO", "MARCO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
RE_ARQUIVO = re.compile(r"transparencia_ano_(\d{4})_(\d+)_(\d+)\.PDF", re.I)
RE_DINHEIRO = re.compile(r"^-?[\d.]+,\d{2}$")
RE_DOC = re.compile(r"^(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11}|\d{14})$")
RE_DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")
# o que parece data, mesmo escrita errado ("0107/2025"): marca onde a data estaria
RE_DATA_SOLTA = re.compile(r"^\d{1,2}/?\d{1,2}/\d{2,4}$")
QUADRO = {"VALOR MENSAL": "valor_mensal", "SALDO DO MES ANTER": "saldo_anterior", "DESP. COM TELEFONE": "telefone",
          "SALDO ATUAL": "saldo_atual", "TOTAL DAS DESPESAS": "total_despesas", "VALOR RESSARCIDO": "ressarcido"}


def palavras_do_pdf(caminho: Path) -> list[dict]:
    """As palavras de todas as páginas, com página e coordenadas (o que fica guardado)."""
    import pdfplumber

    out = []
    with pdfplumber.open(str(caminho)) as pdf:
        for n, pg in enumerate(pdf.pages, start=1):
            for w in pg.extract_words(keep_blank_chars=False, use_text_flow=False):
                out.append({"p": n, "t": w["text"], "x0": round(w["x0"], 1), "x1": round(w["x1"], 1), "y": round(w["top"], 1)})
    return out


def _linhas(palavras: list[dict]) -> list[list[dict]]:
    """Agrupa as palavras em linhas (mesma página, mesma altura com folga de 2 pt)."""
    linhas: list[list[dict]] = []
    for w in sorted(palavras, key=lambda w: (w["p"], w["y"], w["x0"])):
        if linhas and linhas[-1][0]["p"] == w["p"] and abs(linhas[-1][0]["y"] - w["y"]) <= 2:
            linhas[-1].append(w)
        else:
            linhas.append([w])
    return [sorted(l, key=lambda w: w["x0"]) for l in linhas]


def ler_pdf(palavras: list[dict]) -> dict:
    """Notas (com o saldo de cada linha) e o quadro do mês."""
    linhas = _linhas(palavras)
    cab = next((l for l in linhas if {"Item", "Valor", "Saldo"} <= {w["t"] for w in l}), None)
    if cab is not None:
        x_saldo = next(w for w in cab if w["t"] == "Saldo")["x0"] - 8
        x_valor = next(w for w in cab if w["t"] == "Valor")["x0"] - 30
    else:
        # alguns meses (fev/2023) vêm sem a linha de cabeçalho: as colunas saem das linhas
        # de nota, onde o valor e o saldo são os dois últimos números da linha
        finais = [[w for w in l if RE_DINHEIRO.match(w["t"])][-2:] for l in linhas if l[0]["t"].isdigit() and len(l) >= 4]
        pares = [f for f in finais if len(f) == 2]
        if not pares:
            raise PortalMudou("o PDF da ALETO não tem o cabeçalho 'Item ... Valor Saldo' nem linhas de nota com valor e saldo")
        x_saldo = min(f[1]["x0"] for f in pares) - 8
        x_valor = min(f[0]["x0"] for f in pares) - 30
    deputado = processo = mes = None
    notas: list[dict] = []
    quadro: dict[str, Decimal] = {}
    saldos_soltos: list[Decimal] = []  # saldo numa linha sem nota (a primeira, o saldo de abertura)
    for l in linhas:
        textos = [w["t"] for w in l]
        junto = " ".join(textos)
        sa = sem_acento(junto).upper()
        m = re.search(r"DEPUTAD[OA]\s*:\s*(.+?)(?:\s+Processo|$)", junto, re.I)
        if m:
            deputado = m.group(1).strip()
            p = re.search(r"Processo\s+n\.?\S*\s+(\S+)", junto, re.I)
            processo = p.group(1) if p else None
            continue
        if not mes:
            mm = next((x for x in MESES if re.search(rf"\b{x}\b", sa)), None)
            if mm and "DESPESAS" in sa:
                mes = MESES.index(mm) + 1
                continue
        rotulo = next((v for k, v in QUADRO.items() if sa.startswith(k)), None)
        if rotulo:
            vals = [w for w in l if w["x0"] >= x_saldo and (RE_DINHEIRO.match(w["t"]) or w["t"] == "-")] or \
                [w for w in l if RE_DINHEIRO.match(w["t"]) or w["t"] == "-"][-1:]
            quadro[rotulo] = Decimal(0) if not vals or vals[-1]["t"] == "-" else dinheiro_br(vals[-1]["t"])
            continue
        saldo_w = [w for w in l if w["x0"] >= x_saldo and RE_DINHEIRO.match(w["t"])]
        valor_w = [w for w in l if x_valor <= w["x0"] < x_saldo and RE_DINHEIRO.match(w["t"])]
        # a linha de nota começa pelo número do item e tem valor na coluna Valor; a data
        # pode vir escrita errado na própria planilha ("0107/2025")
        if not (textos[0].isdigit() and valor_w and len(textos) >= 4):
            if saldo_w and l is not cab:
                saldos_soltos.extend(dinheiro_br(w["t"]) for w in saldo_w)
            continue
        i_data = next((i for i, t in enumerate(textos) if i >= 2 and RE_DATA_SOLTA.match(t)), None)
        corte = i_data if i_data is not None else 3
        resto = [w for w in l[corte + (1 if i_data is not None else 0):] if w not in valor_w and w not in saldo_w]
        doc = next((w["t"] for w in resto if RE_DOC.match(w["t"])), None)
        emitente = " ".join(w["t"] for w in resto if w["t"] != doc)
        notas.append({"item": int(textos[0]), "tipo": textos[1], "numero": " ".join(textos[2:corte]) or None,
                      "data": textos[i_data] if i_data is not None else None, "emitente": emitente,
                      "documento": doc, "valor_texto": valor_w[-1]["t"], "saldo_texto": saldo_w[-1]["t"] if saldo_w else None,
                      "pagina": l[0]["p"]})
    return {"deputado": deputado, "processo": processo, "mes": mes, "notas": notas, "quadro": quadro, "saldos_soltos": saldos_soltos}


def conferir_pdf(pdf: dict) -> tuple[bool, list[str]]:
    """As contas do próprio PDF. Devolve (fecha, o que não fecha)."""
    q = pdf["quadro"]
    problemas = []
    faltam = {"saldo_atual", "total_despesas", "ressarcido"} - set(q)
    if faltam:
        return False, [f"o quadro do mês não tem {sorted(faltam)}"]
    soma = Decimal(0)
    corrente = q["saldo_atual"]
    # a numeração dos itens às vezes pula (de 12 para 14 em 07/2025, Claudia Lelis): quem
    # prova que nenhuma linha se perdeu é a corrente do saldo, linha a linha, e o total
    for n in pdf["notas"]:
        try:
            v = dinheiro_br(n["valor_texto"])
        except ValorIlegivel:
            problemas.append(f"nota {n['item']} sem valor legível")
            continue
        soma += v
        corrente -= v
        if n["saldo_texto"] is None or dinheiro_br(n["saldo_texto"]) != corrente:
            problemas.append(f"nota {n['item']}: saldo na linha {n['saldo_texto']} × saldo calculado {corrente}")
    if soma != q["total_despesas"]:
        problemas.append(f"notas somam {soma} × total das despesas {q['total_despesas']}")
    if {"valor_mensal", "saldo_anterior"} <= set(q):
        esperado = q["valor_mensal"] + q["saldo_anterior"] - q.get("telefone", Decimal(0))
        if esperado != q["saldo_atual"]:
            problemas.append(f"valor mensal + saldo anterior − telefone = {esperado} × saldo atual {q['saldo_atual']}")
    if q["ressarcido"] != q["total_despesas"]:
        problemas.append(f"valor ressarcido {q['ressarcido']} × total das despesas {q['total_despesas']} (glosa sem nota indicada)")
    return not problemas, problemas


class Aleto(FonteAssembleiaTela):
    inicio = "https://www.al.to.leg.br/transparencia/verbaIndenizatoria"
    pausa = None  # o Crawl-delay de 10 s vem do robots.txt
    o_que_tem = ("Verba indenizatória (CODAP) de cada deputado estadual, nota a nota, com o emitente e o CNPJ, lida no PDF mensal que a "
                 "tela entrega, com o saldo de cada linha conferido.")

    def __init__(self, ent) -> None:
        super().__init__(ent)
        self.de = int(ent.extra.get("de", self.de))
        self.ate = int(ent.extra.get("ate", self.ate))
        self.sistema.cobre_de, self.sistema.cobre_ate = self.de, self.ate
        self._ano_na_tela: int | None = None

    def ao_renovar(self) -> None:
        self._ano_na_tela = None

    def recorte(self, html: str, url: str) -> str:
        """Da página do POST, guarda do título ao rodapé: o formulário e a tabela do mês."""
        i, j = html.find('<h1 class="page-title">'), html.find("<footer")
        return html[i:j] if 0 <= i < j else html

    async def _escolher_ano(self, ano: int) -> list[str]:
        """Escolher o ano envia o formulário; a página volta com os deputados do ano."""
        assert self.pagina is not None
        if self._ano_na_tela != ano:
            await self.ir(self.inicio, wait_until="domcontentloaded")
            if await self.pagina.locator("#verbaindenizatoria_ano").count() == 0:
                raise PortalMudou("a página da verba da ALETO não tem mais o select de ano")
            anos = await self.pagina.eval_on_selector_all("#verbaindenizatoria_ano option", "os => os.map(o => o.value)")
            if str(ano) not in anos:
                return []
            await self.gesto(lambda: self.pagina.select_option("#verbaindenizatoria_ano", str(ano), force=True),  # type: ignore[union-attr]
                             lambda r: r.request.resource_type == "document" and r.request.method == "POST")
            await self.pagina.wait_for_load_state("domcontentloaded")
            self._ano_na_tela = ano
        nomes = await self.pagina.eval_on_selector_all("#transparencia_parlamentar option", "os => os.map(o => o.value)")
        return [n for n in nomes if n]

    async def descobrir(self) -> Descoberta:
        itens, totais = [], []
        hoje = agora()[:7]
        for ano in range(self.de, self.ate + 1):
            nomes = await self._escolher_ano(ano)
            totais.append(TotalOficial(fonte=self.id, escopo=str(ano), metrica="deputados_no_select", valor=str(len(nomes)),
                                       procedencia=self.procedencia(self.inicio, "", f"select de deputado de {ano}")))
            meses = [m for m in range(1, 13) if f"{ano}-{m:02d}" <= hoje]
            for nome in nomes:
                itens.append(ItemInventario(chave=f"codap-{ano}-{nome}", descricao=f"CODAP de {nome} em {ano}", periodo=str(ano),
                                            parametros={"ano": ano, "nome": nome, "meses": meses}))
        return Descoberta(itens=itens, totais=totais)

    async def _baixar_pdf(self, link) -> tuple[list[dict], str, str, dict]:
        """Clica no link do PDF, lê as palavras e guarda o texto com o hash do PDF."""
        assert self.pagina is not None
        href = await link.get_attribute("href") or ""
        async with self.educacao.vez(self.inicio):
            try:
                async with self.pagina.expect_download(timeout=self.timeout_resposta) as info:
                    await link.click()
                d = await info.value
                caminho = Path(await d.path())
            except Exception as e:
                raise FalhaTransitoria(f"o PDF não baixou ({type(e).__name__})") from e
        bruto = caminho.read_bytes()
        if not bruto.startswith(b"%PDF"):
            raise FalhaTransitoria("o download não é um PDF")
        palavras = palavras_do_pdf(caminho)
        meta = {"pdf_sha256": hashlib.sha256(bruto).hexdigest(), "pdf_bytes": len(bruto), "arquivo": d.suggested_filename}
        url = self.absoluto(href)
        h = guardar_original(self.con, self.id, json.dumps({**meta, "url": url, "palavras": palavras}, ensure_ascii=False).encode(),
                             url, "json")
        try:
            await d.delete()
        except Exception:
            pass
        return palavras, url, h, meta

    async def coletar_item(self, item: ItemInventario) -> Resultado:
        self.disco()
        assert self.pagina is not None
        p = item.parametros
        ano, nome_select = int(p["ano"]), str(p["nome"])
        res = Resultado()
        conf = Conferencias(self.id, item.chave)
        try:
            return await self._coletar(item, ano, nome_select, res, conf)
        except Exception:
            self._ano_na_tela = None  # a página pode ter ficado em outro lugar: o próximo item reabre o formulário
            raise

    async def _coletar(self, item: ItemInventario, ano: int, nome_select: str, res: Resultado, conf: Conferencias) -> Resultado:
        assert self.pagina is not None
        p = item.parametros
        n_notas = 0
        nomes_pdf: set[str] = set()
        primeira = None
        nome = grafia(self.id, nome_select)
        ref = f"nome:{normalizar_nome(nome)}"
        nomes = await self._escolher_ano(ano)
        if nome_select not in nomes:
            raise PortalMudou(f"{nome_select!r} não está mais no select de {ano}")
        for mes in p["meses"]:
            await self.pagina.select_option("#verbaindenizatoria_mes", str(mes), force=True)
            await self.pagina.select_option("#transparencia_parlamentar", nome_select, force=True)
            r, corpo, h = await self.gesto(lambda: self.pagina.click("form[action$='verbaIndenizatoria'] button[type=submit]"),  # type: ignore[union-attr]
                                           lambda r: r.request.resource_type == "document" and r.request.method == "POST")
            await self.pagina.wait_for_load_state("domcontentloaded")
            assert r is not None and h is not None
            proc_mes = self.procedencia(r.url, h, f"{nome_select}, {mes:02d}/{ano}")
            primeira = primeira or proc_mes
            arquivos = []
            for t in tabelas_html(decodificar(corpo)):
                if t and [c.texto for c in t[0]][:2] == ["Mês de referência", "Descrição"]:
                    arquivos = [(l[0].texto, h2) for l in t[1:] if l for c in l for h2 in c.links if "baixar?arquivo=" in h2]
            for ref_mes, href in arquivos:
                m = RE_ARQUIVO.search(href)
                if not m:
                    raise PortalMudou(f"o link do PDF da ALETO mudou de forma: {href}")
                if int(m.group(1)) != ano:
                    raise PortalMudou(f"o PDF {href} é de outro ano")
                arq_id = m.group(3)
                link = self.pagina.locator(f"a[href*='{m.group(0)}']").first
                palavras, url_pdf, h_pdf, meta = await self._baixar_pdf(link)
                pdf = ler_pdf(palavras)
                if pdf["deputado"]:
                    nomes_pdf.add(pdf["deputado"])
                if pdf["mes"] and pdf["mes"] != mes:
                    raise PortalMudou(f"o PDF de {mes:02d}/{ano} diz ser do mês {pdf['mes']}")
                fecha, problemas = conferir_pdf(pdf)
                escopo = f"{ref}-{ano}-{mes:02d}-{arq_id}"
                q = pdf["quadro"]
                soma = Decimal(0)
                lidas = 0
                for n in pdf["notas"]:
                    n_notas += 1
                    proc = self.procedencia(url_pdf, h_pdf, f"página {n['pagina']}, item {n['item']}")
                    chave = chave_hash(self.id, ano, mes, arq_id, n["item"], n["numero"], n["documento"], n["valor_texto"])
                    try:
                        valor = dinheiro_br(n["valor_texto"])
                    except ValorIlegivel as e:
                        res.pendencias.append(Pendencia(fonte=self.id, chave=chave, motivo="valor ilegível",
                                                        texto_original=f"{nome_select} {mes:02d}/{ano} item {n['item']}: {e}", procedencia=proc))
                        continue
                    quando: date | None = None
                    if n["data"] and RE_DATA.match(n["data"]):
                        try:
                            quando = data_br(n["data"])
                        except ValueError:
                            quando = None
                    soma += valor
                    lidas += 1
                    res.despesas.append(self.nota(
                        chave=chave, item=item.chave, ref=ref, nome=titulo_nome(nome), data=quando,
                        competencia=f"{ano}-{mes:02d}", categoria=CATEGORIA, documento=n["documento"], fornecedor=n["emitente"],
                        valor=valor, proc=proc, documento_url=url_pdf,
                        extra={"tipo_documento": n["tipo"], "numero": n["numero"], "data_na_fonte": n["data"] if quando is None else None, "item_no_pdf": n["item"], "saldo_na_linha": n["saldo_texto"], "processo": pdf["processo"],
                               "pdf_sha256": meta["pdf_sha256"], "escopos_conferencia": [escopo]}))
                conf.conferir(escopo, q.get("total_despesas"), soma, proc_mes, f"{nome_select} {mes:02d}/{ano} ({ref_mes})",
                              lidas_todas=lidas == len(pdf["notas"]), outra=(fecha, "; ".join(problemas)[:400]))
                res.totais.append(TotalOficial(fonte=self.id, escopo=escopo, metrica="quadro_do_mes",
                                               valor=str(q.get("ressarcido")), texto_original=json.dumps({k: str(v) for k, v in q.items()}),
                                               procedencia=self.procedencia(url_pdf, h_pdf, "quadro do mês")))
        proc_item = primeira or self.procedencia(self.inicio, "")
        conf.fechar(res, n_notas, proc_item, f"{len(p['meses'])} meses")
        if n_notas or nomes_pdf:
            res.pessoas.append(PessoaFonte(fonte=self.id, ref=ref, periodo=str(ano), nome=titulo_nome(nome), uf="TO", casa=self.ent.casa,
                                           extra={"grafias_na_fonte": sorted({nome_select} | nomes_pdf), "partido_de": None},
                                           procedencia=proc_item))
        return res
