"""Câmara de Curitiba, frequência dos vereadores nas sessões (Betha): robô de
navegador + PDF.

A consulta "Frequência dos Vereadores" do portal Betha da Câmara lista um cartão
por relatório (anual em 2019 e 2020, mensal de 2021 em diante, e um consolidado
anual de 2021 a 2023). O PDF não tem link fixo: a tela só o mostra depois de
"Ver arquivos", e o link que ela recebe é uma URL S3 pré-assinada que vence em
24 horas. O robô abre a consulta como uma pessoa, clica em "Ver arquivos" de cada
relatório, lê a lista de arquivos que a própria tela recebe e baixa o PDF na hora.
O link de 24 h nunca é guardado como endereço do documento: a procedência aponta
para a consulta, com o relatório e o hash do PDF.

O que o relatório publica, por vereador e por mês (ou ano), são contagens que a
própria Câmara já somou: "presença + faltas justificadas" (as duas juntas, numa
coluna só), "faltas (descontadas)" e "licença"; quem preside aparece como
"PRESIDENTE", sem número. As notas com letra ("Alexandre Leprevost(B)",
"13 [F]") explicam posse, renúncia, suplência e faltas, e vão junto da linha.
O número de sessões do mês sai da nota "foram realizadas N sessões".

Layouts vistos (26/11/2026): anual 2019 e 2020 num PDF só ("FREQUÊNCIA*",
"FALTAS", "LICENÇA"); mensal 2021–2022 sem número de linha; mensal 2023–2024 com
número de linha e nota entre colchetes; mensal 2025–2026 com nota entre
parênteses colada ao nome. O consolidado anual de 2021–2023 repete os meses e não
é somado: entra só como total oficial, para conferir.
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass

import httpx
import pdfplumber

from ... import config
from ...modelo import Atividade, Descoberta, ItemInventario, Pendencia, PessoaFonte, Procedencia, Resultado, SistemaOrigem, TotalOficial
from ...nucleo.banco import agora
from ...nucleo.erros import FalhaTransitoria, PortalMudou
from ...nucleo.evidencia import guardar_original
from ...nucleo.texto import normalizar_nome
from ..base import FonteNavegador

PORTAL = "https://transparencia.betha.cloud/#/pYH4AbLiIyAHwETflX8gpQ=="
CONSULTA = 338120
URL_CONSULTA = f"{PORTAL}/consulta/{CONSULTA}"
MESES = {m: i for i, m in enumerate(["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro",
                                     "outubro", "novembro", "dezembro"], start=1)}
# As três colunas, na ordem do relatório
COLUNAS = ("presenca_ou_falta_justificada", "falta_descontada", "licenca")
NOTA = r"(?:\s*[\(\[](?:[A-Z]|\d{1,2})[\)\]])?"
CELULA = rf"(\d{{1,3}}|PRESIDENTE){NOTA}"
RE_LINHA = re.compile(rf"^(?:\d{{1,2}}\s+)?(?P<nome>[^\d].*?){NOTA}\s+{CELULA}\s+{CELULA}\s+{CELULA}\s*$", re.I)
RE_NOTAS_DA_LINHA = re.compile(r"[\(\[]([A-Z]|\d{1,2})[\)\]]")
RE_SESSOES = re.compile(r"foram realizadas\s+(\d{1,3})\s+sess", re.I)
RE_NOTA_TEXTO = re.compile(r"^\s*[\(\[]?([A-Z]|\d{1,2})[\)\]]\s*(.+)$")
RE_FIM_DAS_NOTAS = re.compile(r"^(Relat[óo]rio de requerimentos|Em cumprimento|REQUERIMENTOS|>>|VEREADORES)", re.I)
RE_ANO_PAGINA = re.compile(r"RELAT[OÓ]RIO ANO (\d{4})", re.I)


def _sem_acento_min(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower().strip()


def competencia_do_cartao(ano: int, periodo: str) -> str | None:
    """'2026' + 'Outubro' -> '2026-10'; '2019' + '2019' -> '2019' (relatório anual)."""
    p = _sem_acento_min(periodo)
    if p in MESES:
        return f"{ano}-{MESES[p]:02d}"
    if p == str(ano):
        return str(ano)
    return None


@dataclass
class LinhaFrequencia:
    nome: str
    valores: tuple[int | None, int | None, int | None]  # None = PRESIDENTE
    notas: list[str]
    texto: str
    pagina: int


def ler_relatorio(conteudo: bytes) -> tuple[dict[str, list[LinhaFrequencia]], dict[str, int], dict[str, str], list[tuple[int, str]]]:
    """Lê um PDF de frequência.

    Devolve, por período ('AAAA' no anual, 'mes' no mensal): as linhas da tabela; o
    número de sessões que a nota diz; o texto de cada nota com letra; e as linhas
    da tabela que o robô não conseguiu ler (página, texto), que vão para revisão.
    """
    linhas: dict[str, list[LinhaFrequencia]] = {}
    sessoes: dict[str, int] = {}
    notas: dict[str, str] = {}
    ilegiveis: list[tuple[int, str]] = []
    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        for n_pag, pagina in enumerate(pdf.pages, start=1):
            texto = pagina.extract_text() or ""
            if re.search(r"Requerimentos de Justificativa", texto, re.I) and not any(_casa(l.strip()) for l in texto.splitlines()):
                continue  # páginas com os números dos requerimentos: fora da tabela de frequência
            m_ano = RE_ANO_PAGINA.search(texto)
            periodo = m_ano.group(1) if m_ano else "mes"
            tabela = linhas.setdefault(periodo, [])
            crus = texto.splitlines()
            idx_linhas = [i for i, l in enumerate(crus) if _casa(l.strip())]
            primeira = min(idx_linhas, default=None)
            ultima = max(idx_linhas, default=None)
            i = 0
            fim_da_linha = -2  # índice da última linha do PDF que entrou numa linha da tabela
            nota_aberta: str | None = None  # a nota não continua de uma página para a outra
            while i < len(crus):
                bruto = crus[i].strip()
                m = _casa(bruto)
                if m:
                    tabela.append(_linha(m, bruto, n_pag))
                    fim_da_linha = i
                elif primeira is not None and ultima is not None and primeira < i <= ultima + 1 and re.fullmatch(r"[\(\[](?:[A-Z]|\d{1,2})[\)\]]", bruto):
                    pass  # marcador de nota sozinho na linha (o leitor do PDF separou do número)
                elif (primeira is not None and ultima is not None and primeira < i <= ultima + 1 and tabela and tabela[-1].pagina == n_pag
                      and re.fullmatch(r"[^\d\[\]\(\)]{2,40}", bruto) and len(bruto.split()) <= 3 and fim_da_linha == i - 1):
                    # fim de nome quebrado ("Giorgia Prates - Mandata" / "Preta"): volta para a linha de cima
                    ant = tabela[-1]
                    ant.nome = f"{ant.nome} {bruto}".strip()
                    ant.texto = f"{ant.texto} / {bruto}"
                elif primeira is not None and ultima is not None and primeira < i < ultima and bruto:
                    # nome quebrado em duas linhas: tenta juntar com a seguinte
                    junto = f"{bruto} {crus[i + 1].strip()}" if i + 1 < len(crus) else bruto
                    mj = _casa(junto)
                    if mj and not _casa(crus[i + 1].strip()):
                        tabela.append(_linha(mj, junto, n_pag))
                        i += 1
                        fim_da_linha = i
                    else:
                        ilegiveis.append((n_pag, bruto))
                for ms in RE_SESSOES.finditer(bruto):
                    sessoes.setdefault(periodo, int(ms.group(1)))
                mn = RE_NOTA_TEXTO.match(bruto)
                depois_da_tabela = primeira is None or i > (ultima or 0)
                if mn and not m and depois_da_tabela:
                    nota_aberta = mn.group(1)
                    notas.setdefault(nota_aberta, mn.group(2).strip())
                elif nota_aberta and RE_FIM_DAS_NOTAS.match(bruto):
                    nota_aberta = None  # começa outra parte do relatório (os requerimentos de justificativa)
                elif nota_aberta and depois_da_tabela and bruto and not m and len(notas[nota_aberta]) < 400:
                    notas[nota_aberta] = f"{notas[nota_aberta]} {bruto}"  # a nota continua na linha de baixo
                i += 1
    return {k: v for k, v in linhas.items() if v}, sessoes, notas, ilegiveis


def nome_valido(nome: str) -> bool:
    """Nome de vereador não tem célula da tabela dentro: no máximo um número solto
    ("João da 5 Irmãos"), nenhum número com nota ("1[4]") nem dois números seguidos."""
    return (len(re.findall(r"(?<!\S)\d+(?!\S)", nome)) <= 1 and not re.search(r"\d\s*[\[\(]|\d\s+\d", nome))


def _casa(bruto: str) -> re.Match | None:
    m = RE_LINHA.match(bruto)
    if m and nome_valido(m.group("nome")) and not re.search(r"\d+\s+\d+\s+\d+\s+\d+", bruto):
        return m
    return None


def _linha(m: re.Match, bruto: str, pagina: int) -> LinhaFrequencia:
    vals = tuple(None if g.upper() == "PRESIDENTE" else int(g) for g in m.groups()[1:4])
    nome = RE_NOTAS_DA_LINHA.sub("", m.group("nome")).strip(" -")
    return LinhaFrequencia(nome=nome, valores=vals, notas=RE_NOTAS_DA_LINHA.findall(bruto), texto=bruto, pagina=pagina)  # type: ignore[arg-type]


class CmcFrequencia(FonteNavegador):
    id = "cmc_frequencia"
    dado = "atividade"
    ua = config.UA_ROBO  # com "HeadlessChrome" o Betha devolve 403
    pausa = 1.5
    sistema = SistemaOrigem(
        fonte="cmc_frequencia", casa="cmc", sistema="Portal da Transparência Betha (Frequência dos Vereadores)", fornecedor="Betha Sistemas",
        modo="robo_pdf", cobre_de=2019, cobre_ate=2026, endereco=URL_CONSULTA,
        o_que_tem="Relatórios de frequência dos vereadores nas sessões: anual em 2019 e 2020, mensal de 2021 em diante.",
    )

    async def _abrir_consulta(self) -> list[dict]:
        """Abre a consulta, põe 100 por página e devolve os cartões que a tela recebeu."""
        assert self.pagina is not None
        hits: list[dict] = []

        async def ao_responder(r):
            if f"/busca-textual/{CONSULTA}?" in r.url and r.request.method == "POST":
                try:
                    hits.extend((await r.json()).get("hits", []))
                except Exception:
                    pass

        self.pagina.on("response", ao_responder)
        try:
            await self.ir(URL_CONSULTA, wait_until="networkidle")
            if await self.pagina.locator("text=403 Forbidden").count():
                raise PortalMudou("o Betha devolveu 403 (User-Agent recusado?)")
            try:
                await self.pagina.locator("table.table-card").first.wait_for(timeout=45000)
            except Exception as e:
                raise FalhaTransitoria("a tabela da consulta de frequência não apareceu") from e
            seletor = self.pagina.locator("select.responsive-result-pag").first
            if await seletor.count():
                hits.clear()
                async with self.educacao.vez(URL_CONSULTA):
                    async with self.pagina.expect_response(lambda r: f"/busca-textual/{CONSULTA}?" in r.url, timeout=45000):
                        await seletor.select_option("100")
                await self.pagina.wait_for_timeout(800)
            contador = (await self.pagina.locator(".bth-powernumber__value").first.inner_text()).strip()
            if not contador.isdigit() or int(contador) != len(hits):
                raise FalhaTransitoria(f"o contador diz {contador!r} e a tela recebeu {len(hits)} relatórios")
            return [{"id": h["id"], **h.get("sourceAsMap", {})} for h in hits]
        finally:
            self.pagina.remove_listener("response", ao_responder)

    async def descobrir(self) -> Descoberta:
        cartoes = await self._abrir_consulta()
        assert self.pagina is not None
        html = await self.pagina.content()
        h = guardar_original(self.con, self.id, html.encode("utf-8"), URL_CONSULTA, "html")
        proc = self.procedencia(URL_CONSULTA, h, "contador 'Registros encontrados'")
        itens = []
        for c in cartoes:
            comp = competencia_do_cartao(int(c["ano"]), str(c["periodo"]))
            if comp is None:
                raise PortalMudou(f"período do relatório de frequência ilegível: {c['ano']} / {c['periodo']!r}")
            itens.append(ItemInventario(chave=f"frequencia-{comp}", descricao=f"{c['titulo']} — {c['periodo']} de {c['ano']}", periodo=comp,
                                        parametros={"id": c["id"], "ano": c["ano"], "periodo": c["periodo"],
                                                    "publicado": c.get("dataHoraPublicacao")}))
        totais = [TotalOficial(fonte=self.id, escopo="relatorios", metrica="registros", valor=str(len(cartoes)),
                               texto_original=f"Registros encontrados: {len(cartoes)}", procedencia=proc)]
        return Descoberta(itens=itens, totais=totais)

    async def _arquivos(self, item: ItemInventario) -> list[dict]:
        """Clica em "Ver arquivos" no cartão do relatório e devolve a lista que a tela recebe."""
        assert self.pagina is not None
        cartoes = await self._abrir_consulta()
        ids = [c["id"] for c in cartoes]
        if item.parametros["id"] not in ids:
            raise PortalMudou(f"o relatório {item.chave} saiu da consulta")
        linha = self.pagina.locator("table.table-card tbody tr").nth(ids.index(item.parametros["id"]))
        celulas = " ".join(await linha.locator("td").all_inner_texts())
        if str(item.parametros["ano"]) not in celulas or str(item.parametros["periodo"]) not in celulas:
            raise PortalMudou(f"a linha {ids.index(item.parametros['id']) + 1} da tela não é a do relatório {item.chave}")
        uuid = item.parametros["id"].rsplit(":", 1)[-1]
        async with self.educacao.vez(URL_CONSULTA):
            async with self.pagina.expect_response(lambda r: f"/busca/{CONSULTA}/anexos/" in r.url and uuid in r.url, timeout=45000) as resp:
                await linha.locator("td.detalhamentoArquivos").click()
        lista = await (await resp.value).json()
        await self.pagina.keyboard.press("Escape")
        if not isinstance(lista, list) or not lista:
            raise PortalMudou(f"a lista de arquivos do relatório {item.chave} veio vazia ou em outro formato")
        return lista

    async def coletar_item(self, item: ItemInventario) -> Resultado:
        comp = item.periodo
        arquivos = [a for a in await self._arquivos(item) if (a.get("tipo") or "").endswith("pdf")]
        if not arquivos:
            raise PortalMudou(f"o relatório {item.chave} não tem PDF")
        res = Resultado()
        for arq in arquivos:
            assert self.http is not None
            async with self.educacao.vez(arq["url"]):
                try:
                    r = await self.http.get(arq["url"])  # URL pré-assinada de 24 h: usada na hora e nunca guardada
                except httpx.HTTPError as e:
                    raise FalhaTransitoria(f"{type(e).__name__} ao baixar o PDF de {item.chave}") from e
            if r.status_code != 200 or not r.content.startswith(b"%PDF"):
                raise FalhaTransitoria(f"o PDF de {item.chave} não veio (HTTP {r.status_code})")
            local = f"{item.descricao}, arquivo {arq.get('nome')}"
            h = guardar_original(self.con, self.id, r.content, f"{URL_CONSULTA} :: {item.chave} :: {arq.get('nome')}", "pdf")
            proc = Procedencia(fonte=self.id, url=URL_CONSULTA, hash_original=h, coletado_em=agora(), localizador=local)
            self._ler(item, comp, r.content, proc, res)
        return res

    def _ler(self, item: ItemInventario, comp: str, conteudo: bytes, proc: Procedencia, res: Resultado) -> None:
        por_periodo, sessoes, notas, ilegiveis = ler_relatorio(conteudo)
        anual = len(comp) == 4
        consolidado = anual and int(comp) >= 2021  # os meses vêm dos relatórios mensais
        if anual and not consolidado:
            # o PDF de 2019 e 2020 traz os dois anos, um por página: só o ano do cartão
            alvo = {comp: por_periodo.get(comp, [])}
        else:
            alvo = {comp: [l for v in por_periodo.values() for l in v]}
        n_lidas = sum(len(v) for v in alvo.values())
        if n_lidas == 0 and not consolidado:
            raise PortalMudou(f"nenhuma linha de frequência lida no relatório {item.chave}")
        # linhas da tabela: as lidas e as que o robô não conseguiu ler (estas vão para revisão)
        n_tabela = n_lidas + (0 if consolidado else len(ilegiveis))
        res.totais.append(TotalOficial(fonte=self.id, escopo=item.chave, metrica="linhas_lidas", valor=str(n_tabela),
                                       texto_original=f"{n_tabela} linhas de vereador na tabela", procedencia=proc))
        n_sessoes = sessoes.get(comp if anual else "mes")
        if n_sessoes is not None:
            res.totais.append(TotalOficial(fonte=self.id, escopo=item.chave, metrica="sessoes", valor=str(n_sessoes),
                                           texto_original=f"foram realizadas {n_sessoes} sessões", procedencia=proc))
        if consolidado:
            res.totais.append(TotalOficial(fonte=self.id, escopo=item.chave, metrica="consolidado_nao_somado", valor="1",
                                           texto_original="consolidado anual: os meses vêm dos relatórios mensais", procedencia=proc))
            return
        for pag, texto in ilegiveis:
            res.pendencias.append(Pendencia(fonte=self.id, chave=f"{self.id}:{comp}:ilegivel:{pag}:{normalizar_nome(texto)[:40]}",
                                            motivo="linha da tabela de frequência que o robô não conseguiu ler", texto_original=texto[:300],
                                            procedencia=proc.model_copy(update={"localizador": f"{proc.localizador}, página {pag}"})))
        vistos: set[str] = set()
        for linhas in alvo.values():
            for l in linhas:
                ref = f"nome:{normalizar_nome(l.nome)}"
                if ref in vistos:
                    res.pendencias.append(Pendencia(fonte=self.id, chave=f"{self.id}:{comp}:repetido:{ref}", motivo="vereador repetido no relatório",
                                                    texto_original=l.texto[:300], procedencia=proc))
                    continue
                vistos.add(ref)
                nota = " ".join(f"({x}) {notas[x]}" for x in l.notas if x in notas)[:400] or None
                loc = f"{proc.localizador}, página {l.pagina}: \"{l.texto[:120]}\""
                base = dict(fonte=self.id, casa="cmc", tipo="frequencia", ref_parlamentar=ref, competencia=comp,
                            procedencia=proc.model_copy(update={"localizador": loc}))
                if all(v is None for v in l.valores):
                    res.atividades.append(Atividade(chave=f"{self.id}:{comp}:{ref}:presidiu", rotulo="presidiu", quantidade=0,
                                                    extra={"nome_na_fonte": l.nome, **({"nota": nota} if nota else {}),
                                                           **({"sessoes": n_sessoes} if n_sessoes is not None else {})}, **base))
                    continue
                if any(v is None for v in l.valores):
                    # "PRESIDENTE" numa coluna e número em outra: a linha inteira vai para revisão
                    res.pendencias.append(Pendencia(fonte=self.id, chave=f"{self.id}:{comp}:{ref}:misto", motivo="linha de frequência com célula ilegível",
                                                    texto_original=l.texto[:300], procedencia=proc))
                    continue
                for coluna, v in zip(COLUNAS, l.valores, strict=True):
                    res.atividades.append(Atividade(chave=f"{self.id}:{comp}:{ref}:{coluna}", rotulo=coluna, quantidade=v,
                                                    extra={"nome_na_fonte": l.nome, **({"nota": nota} if nota else {}),
                                                           **({"sessoes": n_sessoes} if n_sessoes is not None else {})}, **base))
                res.pessoas.append(PessoaFonte(fonte=self.id, ref=ref, periodo=comp[:4], nome=l.nome, casa="cmc",
                                               procedencia=proc.model_copy(update={"localizador": loc})))
