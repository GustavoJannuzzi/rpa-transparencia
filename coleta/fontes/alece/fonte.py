"""Assembleia do Ceará: a verba de desempenho parlamentar pela tela, no navegador.

O caminho, visto em 26/11/2026 em `despesas/verba-desempenho-parlamentar`:
- o formulário (mês e ano) volta uma lista paginada de nomes ("DEP AGENOR NETO"), 30
  por página, com o contador "Mostrando 1 a 30 de 53 resultados";
- cada nome tem um botão que abre um modal; o script da página põe num iframe o
  endereço `.../detalhes?codigo=<base64>`, e o código é o base64 de
  "ANO_MÊS_NOME" (`2026_09_DEP AGENOR NETO`): a chave do detalhe é o nome exato
  como a casa o escreve, com erro de digitação e espaço duplo;
- o detalhe é uma tabela por nota de empenho: empenho, descrição, CNPJ (14 dígitos,
  sem máscara), credor e valor, com o TOTAL GERAL.

A casa também publica, na mesma tela, um CSV do mês ("Baixar em formato CSV"), com os
mesmos empenhos sem acento. O robô lê a tela e baixa o CSV pelo botão, para conferir
nota a nota: cada empenho da tela tem de estar no CSV, com o mesmo CNPJ e o mesmo
valor, e o contrário. A conferência de cada deputado no mês é a soma das notas ×
TOTAL GERAL e a tela × CSV.

A casa não classifica a despesa por tipo: tudo é "Verba de Desempenho
Parlamentar". Uma parte dos credores são contratos da própria casa (benefício
alimentação, cartão combustível, telefonia). No reembolso de despesa do próprio
deputado, a coluna "CNPJ" traz 11 dígitos (o CPF dele): o documento é mascarado na
leitura, como o de todo fornecedor pessoa física.
"""

from __future__ import annotations

import base64
import csv
import io
import re
from collections import Counter
from decimal import Decimal

from ...de_para import grafia
from ...modelo import Descoberta, ItemInventario, Pendencia, PessoaFonte, Resultado, TotalOficial
from ...nucleo.erros import FalhaTransitoria, PortalMudou
from ...nucleo.evidencia import guardar_original
from ...nucleo.texto import ValorIlegivel, chave_hash, dinheiro_br, normalizar_nome, so_digitos
from ..assembleia_tela import Conferencias, FonteAssembleiaTela, decodificar, tabelas_html, texto_html, titulo_nome

CATEGORIA = "Verba de Desempenho Parlamentar"
RE_CONTADOR = re.compile(r"Mostrando\s+(\d+)\s+a\s+(\d+)\s+de\s+(\d+)\s+resultados", re.I)
RE_PREFIXO = re.compile(r"^\s*DEP(?:UTAD[OA]|A)?\.?\s+", re.I)


def nome_sem_prefixo(rotulo: str) -> str:
    """'DEP AGENOR NETO' -> 'AGENOR NETO' (espaços simples)."""
    return re.sub(r"\s+", " ", RE_PREFIXO.sub("", rotulo)).strip()


def codigo_do_detalhe(ano: int, mes: str, rotulo: str) -> str:
    """A chave que a casa põe no iframe: base64 de 'ANO_MÊS_NOME', o nome como está."""
    return base64.b64encode(f"{ano}_{mes}_{rotulo}".encode()).decode()


def ler_lista(html: str) -> dict:
    """Uma página da lista: os nomes com o código do detalhe e o contador."""
    linhas = [(r, c) for c, r in re.findall(r'data-bs-codigo="([^"]+)"\s+data-bs-nome="([^"]*)"', html)]
    if not linhas:
        # ordem dos atributos diferente: lê um por um
        for botao in re.findall(r"<button[^>]*data-bs-codigo[^>]*>", html):
            c = re.search(r'data-bs-codigo="([^"]+)"', botao)
            n = re.search(r'data-bs-nome="([^"]*)"', botao)
            if c and n:
                linhas.append((n.group(1), c.group(1)))
    from html import unescape

    linhas = [(unescape(n), c) for n, c in linhas]
    m = RE_CONTADOR.search(texto_html(html))
    proxima = re.search(r'<a[^>]+href="([^"]+)"[^>]*rel="next"', html)
    return {"linhas": linhas, "contador": tuple(int(x) for x in m.groups()) if m else None,
            "proxima": unescape(proxima.group(1)) if proxima else None}


def ler_detalhe(html: str) -> dict:
    """O iframe de um deputado no mês: as notas de empenho e o TOTAL GERAL."""
    for t in tabelas_html(html):
        cab = [c.texto.upper() for c in (t[0] if t else [])]
        if not (cab and cab[0] == "EMPENHO"):
            continue
        esperado = ["EMPENHO", "DESCRIÇÃO", "CNPJ", "CREDOR", "VALOR"]
        if cab[:5] != esperado:
            raise PortalMudou(f"o detalhe da ALECE mudou as colunas: {cab}")
        notas, total = [], None
        for linha in t[1:]:
            if not linha:
                continue
            if linha[0].texto.upper().startswith("TOTAL"):
                total = dinheiro_br(linha[-1].texto)
                continue
            if len(linha) < 5:
                raise PortalMudou(f"nota da ALECE com {len(linha)} colunas")
            notas.append({"empenho": linha[0].texto.strip(), "descricao": re.sub(r"\s+", " ", linha[1].texto).strip(),
                          "documento": linha[2].texto.strip(), "credor": re.sub(r"\s+", " ", linha[3].texto).strip(),
                          "valor_texto": linha[4].texto.strip()})
        return {"notas": notas, "total": total}
    if "EMPENHO" not in html.upper() and len(texto_html(html)) < 400:
        return {"notas": [], "total": None}
    raise PortalMudou("o detalhe da ALECE veio sem a tabela de empenhos")


def ler_csv(texto: str) -> list[dict]:
    """O CSV do mês: 'DEPUTADO;PERIODO;EMPENHO;DESCRICAO;CNPJ;CREDOR;VALOR', depois de
    uma linha de ';;;'."""
    linhas = [l for l in texto.lstrip("﻿").splitlines() if l.strip(" ;")]
    if not linhas or not linhas[0].upper().startswith("DEPUTADO;"):
        raise PortalMudou(f"o CSV da ALECE mudou o cabeçalho: {linhas[:1]}")
    cab = [c.strip().upper() for c in linhas[0].split(";")]
    faltam = {"DEPUTADO", "PERIODO", "EMPENHO", "CNPJ", "VALOR"} - set(cab)
    if faltam:
        raise PortalMudou(f"o CSV da ALECE sem as colunas {sorted(faltam)}")
    return [dict(zip(cab, l, strict=False)) for l in csv.reader(io.StringIO("\n".join(linhas[1:])), delimiter=";")]


def assinatura(nome: str, empenho: str, documento: str, valor: str) -> tuple[str, str, str, str]:
    """A nota como a tela e o CSV a mostram. O nome fica exato (só sem as bordas): a
    casa tem "DEP CLAUDIO PINHO" e "DEP CLAUDIO  PINHO" como duas entradas."""
    return (nome.strip().upper(), empenho.strip().upper(), so_digitos(documento), valor.strip())


def resumo_do_empenho(descricao: str) -> str | None:
    """A descrição do empenho até o primeiro "CONFORME"/"TERMO"/"EDITAL" (o resto é a
    referência ao contrato, repetida em todas as notas). A inteira fica no original."""
    d = re.sub(r"\s+", " ", descricao or "").strip()
    corte = re.split(r"[,.;]?\s+(?:CONFORME|TERMO DE|EDITAL DE|ATO NORMATIVO)\b", d, maxsplit=1, flags=re.I)[0].strip(" ,.;-")
    return corte[:160] or None


# a casa escreve "ANULACAO", "ANULAÇÃO", "ANULACAL", "ANULCAO", "AANULACAO", "ANULACA", "ANULACOA"
RE_ANULACAO = re.compile(r"\bA?ANUL", re.I)


class Alece(FonteAssembleiaTela):
    inicio = "https://transparencia.al.ce.gov.br/despesas/verba-desempenho-parlamentar"
    o_que_tem = ("Verba de desempenho parlamentar de cada deputado estadual, empenho a empenho, com o credor e o CNPJ, lida na tela "
                 "(lista paginada e detalhe no modal), conferida contra o CSV do mês que a própria casa publica.")

    def recorte(self, html: str, url: str) -> str:
        """Da lista, guarda o bloco dos resultados até a paginação (o resto é o menu)."""
        i = html.find('id="resultados"')
        j = html.find("</nav>", i)
        return html[html.rfind("<div", 0, i):j + 6] if i >= 0 and j > i else html

    async def _listar(self, ano: int, mes: str):
        """Abre o mês pelo formulário e devolve a primeira página lida (e o original)."""
        assert self.pagina is not None
        await self.ir(self.inicio, wait_until="domcontentloaded")
        if await self.pagina.locator("#mes").count() == 0 or await self.pagina.locator("#ano").count() == 0:
            raise PortalMudou("o formulário da verba da ALECE não tem mais os selects de mês e ano")
        anos = {v for v in await self.pagina.eval_on_selector_all("#ano option", "os => os.map(o => o.value)")}
        if str(ano) not in anos:
            return None
        await self.pagina.select_option("#mes", mes)
        await self.pagina.select_option("#ano", str(ano))
        r, corpo, h = await self.gesto(lambda: self.pagina.click("#busca input[type=submit]"),  # type: ignore[union-attr]
                                       lambda r: r.request.resource_type == "document" and "verba-desempenho-parlamentar?" in r.url)
        await self.pagina.wait_for_load_state("domcontentloaded")
        assert r is not None and h is not None
        return r.url, decodificar(corpo), h

    async def descobrir(self) -> Descoberta:
        itens, totais = [], []
        from ...nucleo.banco import agora

        hoje = agora()[:7]
        for ano in range(self.de, self.ate + 1):
            for m in range(1, 13):
                mes = f"{m:02d}"
                if f"{ano}-{mes}" > hoje:
                    break
                aberto = await self._listar(ano, mes)
                if aberto is None:
                    break
                url, html, h = aberto
                pag = ler_lista(html)
                if not pag["linhas"]:
                    continue
                n = pag["contador"][2] if pag["contador"] else len(pag["linhas"])
                totais.append(TotalOficial(fonte=self.id, escopo=f"verbas-{ano}-{mes}", metrica="nomes_na_lista", valor=str(n),
                                           texto_original=f"Mostrando ... de {n} resultados", procedencia=self.procedencia(url, h)))
                itens.append(ItemInventario(chave=f"verbas-{ano}-{mes}", descricao=f"Verba de desempenho de {mes}/{ano}", periodo=str(ano),
                                            parametros={"ano": ano, "mes": mes, "nomes": n}))
        return Descoberta(itens=itens, totais=totais)

    async def _csv_do_mes(self, ano: int, mes: str) -> tuple[list[dict], str, str]:
        """Baixa o CSV pelo botão da própria tela."""
        assert self.pagina is not None
        botao = self.pagina.locator("a.baixar-csv").first
        if await botao.count() == 0:
            raise PortalMudou("a tela da ALECE não tem mais o botão 'Baixar em formato CSV'")
        href = await botao.get_attribute("href") or ""
        async with self.educacao.vez(self.inicio):
            try:
                async with self.pagina.expect_download(timeout=self.timeout_resposta) as info:
                    await botao.click()
                d = await info.value
                caminho = await d.path()
            except Exception as e:
                raise FalhaTransitoria(f"o CSV do mês não baixou ({type(e).__name__})") from e
        corpo = open(caminho, "rb").read()
        h = guardar_original(self.con, self.id, corpo, href, "csv")
        return ler_csv(decodificar(corpo)), href, h

    async def coletar_item(self, item: ItemInventario) -> Resultado:
        assert self.pagina is not None
        p = item.parametros
        ano, mes = int(p["ano"]), str(p["mes"])
        res = Resultado()
        conf = Conferencias(self.id, item.chave)
        aberto = await self._listar(ano, mes)
        if aberto is None:
            raise PortalMudou(f"o ano {ano} sumiu do formulário da ALECE")
        url, html, h = aberto
        proc_lista = self.procedencia(url, h, f"lista de {mes}/{ano}")
        pag = ler_lista(html)
        contador = pag["contador"]
        csv_linhas, url_csv, h_csv = await self._csv_do_mes(ano, mes)
        # tela × CSV pelo nome normalizado: o CSV tira o acento solto que a tela mantém
        # ("DEP ´SARGENTO REGINAURO"), e a tela tem variantes do mesmo nome que são entradas
        # vazias ("DEP CLAUDIO  PINHO"); as variantes de um nome são juntadas dos dois lados
        no_csv: dict[str, Counter] = {}
        for l in csv_linhas:
            s = assinatura(l.get("DEPUTADO", ""), l.get("EMPENHO", ""), l.get("CNPJ", ""), l.get("VALOR", ""))
            no_csv.setdefault(normalizar_nome(s[0]), Counter())[s[1:]] += 1
        na_tela_mes: dict[str, Counter] = {}
        vistos: list[str] = []
        n_notas = 0
        pagina_n = 1
        while True:
            for k, (rotulo, codigo) in enumerate(pag["linhas"]):
                vistos.append(rotulo)
                if codigo != codigo_do_detalhe(ano, mes, rotulo):
                    raise PortalMudou(f"a chave do detalhe de {rotulo!r} não é mais base64 de 'ano_mês_nome'")
                botao = self.pagina.locator("[data-bs-codigo]").nth(k)
                alvo = f"detalhes?codigo={codigo}"
                rd, corpo_d, hd = await self.gesto(botao.click, lambda r: alvo in r.url)  # noqa: B023 (usado na hora)
                assert rd is not None and hd is not None
                det = ler_detalhe(decodificar(corpo_d))
                await self.pagina.keyboard.press("Escape")
                await self.pagina.locator("#detalhesParlamentar").wait_for(state="hidden", timeout=10000)
                nome_fonte = nome_sem_prefixo(rotulo)
                nome = grafia(self.id, nome_fonte)
                ref = f"nome:{normalizar_nome(nome)}"
                rotulo_limpo = re.sub(r"\s+", " ", rotulo).strip()
                escopo = f"{ano}-{mes}-{rotulo_limpo}"
                escopo_csv = f"{ano}-{mes}-csv-{normalizar_nome(rotulo)}"
                soma = Decimal(0)
                lidas = 0
                na_tela = na_tela_mes.setdefault(normalizar_nome(rotulo), Counter())
                for j, n in enumerate(det["notas"]):
                    n_notas += 1
                    proc = self.procedencia(rd.url, hd, f"empenho {n['empenho']}")
                    chave = chave_hash(self.id, ano, mes, rotulo, n["empenho"], n["documento"], n["valor_texto"], j)
                    na_tela[assinatura(rotulo, n["empenho"], n["documento"], n["valor_texto"])[1:]] += 1
                    try:
                        valor = dinheiro_br(n["valor_texto"])
                    except ValorIlegivel as e:
                        res.pendencias.append(Pendencia(fonte=self.id, chave=chave, motivo="valor ilegível",
                                                        texto_original=f"{rotulo} {mes}/{ano} {n['empenho']}: {e}", procedencia=proc))
                        continue
                    soma += valor
                    lidas += 1
                    res.despesas.append(self.nota(
                        chave=chave, item=item.chave, ref=ref, nome=titulo_nome(nome), data=None, competencia=f"{ano}-{mes}",
                        categoria=CATEGORIA, documento=n["documento"], fornecedor=n["credor"], valor=valor, proc=proc,
                        descricao=resumo_do_empenho(n["descricao"]),
                        extra={"empenho": n["empenho"], "nome_na_fonte": rotulo, "descricao_inteira": n["descricao"],
                               "escopos_conferencia": [escopo, escopo_csv],
                               **({"anulacao_explicada": True} if valor < 0 and RE_ANULACAO.search(n["descricao"]) else {})}))
                conf.conferir(escopo, det["total"], soma, proc_lista, f"{rotulo} {mes}/{ano}, TOTAL GERAL × soma dos empenhos",
                              lidas_todas=lidas == len(det["notas"]))
                res.pessoas.append(PessoaFonte(fonte=self.id, ref=ref, periodo=str(ano), nome=titulo_nome(nome), uf="CE", casa=self.ent.casa,
                                               extra={"grafias_na_fonte": [rotulo], "partido_de": None}, procedencia=proc_lista))
            if not pag["proxima"]:
                break
            proxima = self.pagina.locator("a.page-link[rel=next]:visible").first
            r2, corpo2, h2 = await self.gesto(proxima.click,
                                              lambda r: r.request.resource_type == "document" and "page=" in r.url)
            await self.pagina.wait_for_load_state("domcontentloaded")
            assert r2 is not None
            pag = ler_lista(decodificar(corpo2))
            pagina_n += 1
            if pagina_n > 20:
                raise PortalMudou("a paginação da ALECE não termina")
        # cada nome (com as suas variantes): os empenhos da tela são os do CSV, e o contrário
        for nome_norm in sorted(set(na_tela_mes) | set(no_csv)):
            tela, do_csv = na_tela_mes.get(nome_norm, Counter()), no_csv.get(nome_norm, Counter())
            faltam, sobram = sum((tela - do_csv).values()), sum((do_csv - tela).values())
            conf.conferir(f"{ano}-{mes}-csv-{nome_norm}", Decimal(sum(do_csv.values())), Decimal(sum((tela & do_csv).values())), proc_lista,
                          f"{nome_norm or '(nome vazio)'} {mes}/{ano}, empenhos do CSV × da tela",
                          outra=(tela == do_csv, f"{faltam} empenho(s) só na tela, {sobram} só no CSV"))
        # a lista inteira: todo deputado do CSV apareceu na tela
        nomes_csv = set(no_csv)
        nomes_tela = {normalizar_nome(v) for v in vistos}
        conf.conferir(f"{ano}-{mes}-lista", Decimal(len(nomes_csv)), Decimal(len(nomes_csv & nomes_tela)), proc_lista,
                      f"{mes}/{ano}, nomes do CSV × nomes da lista da tela",
                      outra=(nomes_csv <= nomes_tela, f"{len(nomes_csv - nomes_tela)} nome(s) do CSV fora da lista da tela"))
        # o contador "Mostrando ... de N resultados" conta um a mais do que a lista mostra
        # (visto em 26/11/2026 em todos os meses testados): fica registrado, sem mexer nas notas
        res.totais.append(TotalOficial(fonte=self.id, escopo=item.chave, metrica="contador_x_lidos",
                                       valor=f"{len(vistos)}/{contador[2] if contador else '?'}",
                                       texto_original=f"o contador da tela diz {contador[2] if contador else '?'}; a lista mostrou {len(vistos)} nomes",
                                       procedencia=proc_lista))
        res.totais.append(TotalOficial(fonte=self.id, escopo=item.chave, metrica="linhas_no_csv", valor=str(len(csv_linhas)),
                                       procedencia=self.procedencia(url_csv, h_csv)))
        conf.fechar(res, n_notas, proc_lista, f"{len(vistos)} nomes")
        if not vistos:
            raise FalhaTransitoria("a lista do mês veio vazia")
        # o mesmo deputado em duas grafias no mês: junta as grafias na pessoa
        por_ref: dict[str, PessoaFonte] = {}
        for pf in res.pessoas:
            if pf.ref in por_ref:
                por_ref[pf.ref].extra["grafias_na_fonte"] = sorted(set(por_ref[pf.ref].extra["grafias_na_fonte"]) | set(pf.extra["grafias_na_fonte"]))
            else:
                por_ref[pf.ref] = pf
        res.pessoas = list(por_ref.values())
        return res
