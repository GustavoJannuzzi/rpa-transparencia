"""Assembleia que só se lê pela tela: o robô abre o portal no navegador, preenche os
filtros como uma pessoa e lê o que a tela mostra (ou a resposta que a própria tela
pede ao servidor). O original de cada passo vai para `originais/` com hash.

O que é comum às sete casas desta família (AP, CE, TO, BA, GO, PE, RN):
- a vez de falar com o portal vale também para o clique: todo gesto que dispara um
  pedido ao servidor espera a pausa do domínio (`gesto`);
- a conferência da casa é a soma das notas contra o total que a própria tela
  mostra, por escopo (categoria no mês, mês, pedido). Cada item grava quantos
  escopos fecham (`escopos_que_fecham`) e, para cada um que não fecha, um
  `total_diverge`; as notas daquele escopo levam `escopo_conferencia` e vão para a
  revisão com o motivo;
- `linhas_na_origem` conta as notas que a tela mostrou; é o lado "origem" da
  equação origem = coletado + revisão;
- o original de uma tela HTML é guardado enxuto (sem scripts, estilos e SVG, que eram
  a maior parte do peso); JSON, CSV e o texto do PDF ficam como vieram.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from .. import config
from ..entidades import EntidadeAssembleia
from ..modelo import Procedencia, Resultado, TotalOficial
from ..nucleo.erros import FalhaTransitoria, PortalMudou
from ..nucleo.evidencia import guardar_original
from .assembleia import FonteAssembleia
from .base import FonteNavegador

if TYPE_CHECKING:  # pragma: no cover
    from playwright.async_api import Response


# ---------------------------------------------------------------------------
# HTML -> tabelas (texto e links de cada célula), sem biblioteca
# ---------------------------------------------------------------------------

@dataclass
class Celula:
    texto: str
    links: list[str] = field(default_factory=list)
    cabecalho: bool = False


class _Tabelas(HTMLParser):
    """Junta cada <table> em linhas de células. Tabela dentro de tabela vira outra
    tabela (a de fora não leva o texto da de dentro)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tabelas: list[list[list[Celula]]] = []
        self._pilha: list[list[list[Celula]]] = []
        self._cel: list[Celula | None] = []
        self._ignorar = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style"):
            self._ignorar += 1
        elif tag == "table":
            self._pilha.append([])
            self._cel.append(None)
        elif tag == "tr" and self._pilha:
            self._pilha[-1].append([])
        elif tag in ("td", "th") and self._pilha:
            if not self._pilha[-1]:
                self._pilha[-1].append([])
            c = Celula("", cabecalho=tag == "th")
            self._pilha[-1][-1].append(c)
            self._cel[-1] = c
        elif tag == "a" and self._cel and self._cel[-1] is not None and a.get("href"):
            self._cel[-1].links.append(a["href"] or "")
        elif tag == "br" and self._cel and self._cel[-1] is not None:
            self._cel[-1].texto += "\n"

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._ignorar = max(0, self._ignorar - 1)
        elif tag == "table" and self._pilha:
            self.tabelas.append(self._pilha.pop())
            self._cel.pop()
        elif tag in ("td", "th") and self._cel:
            self._cel[-1] = None

    def handle_data(self, data):
        if not self._ignorar and self._cel and self._cel[-1] is not None:
            self._cel[-1].texto += data


def tabelas_html(html: str) -> list[list[list[Celula]]]:
    p = _Tabelas()
    p.feed(html)
    p.close()
    for t in p.tabelas:
        for linha in t:
            for c in linha:
                c.texto = re.sub(r"[ \t\r\f\v\xa0]+", " ", c.texto).strip()
                c.texto = re.sub(r"\s*\n\s*", "\n", c.texto).strip()
    return p.tabelas


def texto_html(html: str) -> str:
    """O texto visível, em uma linha (para achar rótulos como 'TOTAL' e 'Saldo')."""
    class _T(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.partes: list[str] = []
            self._ign = 0

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style"):
                self._ign += 1

        def handle_endtag(self, tag):
            if tag in ("script", "style"):
                self._ign = max(0, self._ign - 1)

        def handle_data(self, data):
            if not self._ign:
                self.partes.append(data)

    t = _T()
    t.feed(html)
    return re.sub(r"\s+", " ", " ".join(t.partes).replace("\xa0", " ")).strip()


_RE_PESO = re.compile(r"<(script|style|svg|noscript)\b.*?</\1>|<link\b[^>]*>|<!--.*?-->", re.S | re.I)


def enxuto(html: str) -> str:
    """A página sem scripts, estilos, SVG e comentários: o que o robô guarda como
    original de uma tela HTML (o texto e as tabelas ficam; o peso era o resto)."""
    return re.sub(r"\n\s*\n+", "\n", _RE_PESO.sub("", html))


_RE_DUPLA = re.compile(r"[ÂÃ][\x80-\xbf]")


def desfazer_dupla_codificacao(texto: str) -> str:
    """'SERRÃ\\x83O' -> 'SERRÃO': UTF-8 codificado duas vezes (o servidor leu os bytes
    UTF-8 como Latin-1 e codificou de novo). Só desfaz quando o resultado é UTF-8
    válido; senão devolve o texto como veio."""
    if not _RE_DUPLA.search(texto):
        return texto
    try:
        return texto.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto


def decodificar(corpo: bytes) -> str:
    """O portal declara UTF-8; se os bytes não forem, é Latin-1 (Windows-1252). Se
    forem UTF-8 duas vezes, desfaz."""
    try:
        return desfazer_dupla_codificacao(corpo.decode("utf-8"))
    except UnicodeDecodeError:
        return corpo.decode("cp1252", errors="replace")


# ---------------------------------------------------------------------------
# Nome e partido como a casa escreve
# ---------------------------------------------------------------------------

_MINUSCULAS = {"da", "de", "do", "das", "dos", "e"}


def titulo_nome(nome: str) -> str:
    """'ALDILENE SOUZA' -> 'Aldilene Souza'; 'DR. VICTOR' -> 'Dr. Victor'. Só mexe
    no que está todo em maiúsculas (ou todo em minúsculas)."""
    n = re.sub(r"\s+", " ", nome).strip()
    if not (n.isupper() or n.islower()):
        return n
    return " ".join(p.lower() if i and p.lower() in _MINUSCULAS else p[:1].upper() + p[1:].lower() for i, p in enumerate(n.split(" ")))


def separar_partido(rotulo: str) -> tuple[str, str | None]:
    """'ALDILENE SOUZA - PDT' -> ('ALDILENE SOUZA', 'PDT'); 'ROBERTO GOES -UNIÃO'
    também. O partido é o que vem depois do último hífen."""
    m = re.match(r"^(.*\S)\s*-\s*([^-]+?)\s*$", rotulo.strip())
    if not m:
        return re.sub(r"\s+", " ", rotulo).strip(), None
    partido = re.sub(r"\s+", "", m.group(2)) if re.fullmatch(r"PC\s*do\s*B", m.group(2).strip(), re.I) else m.group(2).strip()
    if partido.upper() == "PCDOB":
        partido = "PCdoB"
    return re.sub(r"\s+", " ", m.group(1)).strip(), partido


# ---------------------------------------------------------------------------
# Conferência por escopo
# ---------------------------------------------------------------------------

@dataclass
class Conferencias:
    """Os escopos que o item confere (soma das notas × total da tela).

    As divergências vão numa linha só do item (`escopos_que_fecham`, com a lista em
    JSON no texto): refazer o item regrava a linha, e nada velho fica para trás."""

    fonte: str
    item: str
    fecham: int = 0
    escopos: int = 0
    divergencias: list[dict] = field(default_factory=list)

    def conferir(self, escopo: str, total_tela: Decimal | None, soma: Decimal, proc: Procedencia, rotulo: str,
                 lidas_todas: bool = True, outra: tuple[bool, str] = (True, "")) -> bool:
        """`outra`: uma segunda verificação do mesmo escopo (ok, o que ela diz)."""
        self.escopos += 1
        if total_tela is not None and total_tela == soma and lidas_todas and outra[0]:
            self.fecham += 1
            return True
        texto = f"{rotulo}: total na tela {total_tela if total_tela is not None else 'ausente'} × soma {soma}"
        if not lidas_todas:
            texto += " (há nota ilegível)"
        if not outra[0]:
            texto += f"; {outra[1]}"
        self.divergencias.append({"escopo": escopo, "texto": texto, "url": proc.url})
        return False

    def fechar(self, res: Resultado, linhas: int, proc: Procedencia, texto: str | None = None) -> None:
        res.totais.append(TotalOficial(fonte=self.fonte, escopo=self.item, metrica="linhas_na_origem", valor=str(linhas),
                                       texto_original=texto, procedencia=proc))
        res.totais.append(TotalOficial(fonte=self.fonte, escopo=self.item, metrica="escopos_que_fecham", valor=f"{self.fecham}/{self.escopos}",
                                       texto_original=json.dumps(self.divergencias, ensure_ascii=False) if self.divergencias else None,
                                       procedencia=proc))


# ---------------------------------------------------------------------------
# A fonte
# ---------------------------------------------------------------------------

# Abaixo disto, a coleta para (o rastro do navegador de um item longo passa de 100 MB).
DISCO_MINIMO = 400 * 2**20
# A cada tantos itens o contexto do navegador é trocado (o que ele acumula no Temp vai embora).
ITENS_POR_CONTEXTO = 20


class FonteAssembleiaTela(FonteAssembleia, FonteNavegador):
    """Assembleia lida no navegador. `inicio` é a página onde a consulta começa."""

    inicio = ""
    timeout_resposta = 60000

    def __init__(self, ent: EntidadeAssembleia) -> None:
        # o endereço da consulta vem de entidades.toml (`inicio`)
        self.inicio = ent.extra.get("inicio") or self.inicio
        self.endereco = self.endereco or self.inicio
        super().__init__(ent)

    async def antes_do_item(self, item) -> None:
        # Disco quase cheio: a fonte para limpa (o item fica para a retomada) em vez de
        # cair no meio, quando o rastro do navegador não conseguir ser gravado.
        livre = shutil.disk_usage(config.dados().anchor or config.dados()).free
        self._disco_cheio: str | None = None
        if livre < DISCO_MINIMO:
            self._disco_cheio = f"o disco tem {livre // 2**20} MB livres (mínimo {DISCO_MINIMO // 2**20} MB): a coleta para e retoma depois"
            return
        if self.contexto is None or self._rastreando:
            return
        # O rastro com snapshots guarda o corpo de cada resposta no Temp enquanto o contexto
        # viver: numa coleta de horas, passou de 800 MB por fonte. Aqui o rastro leva só os
        # prints (a página do erro já vai inteira na evidência), e o contexto é trocado a
        # cada ITENS_POR_CONTEXTO itens, o que libera o que o navegador acumulou.
        self._itens_no_contexto = getattr(self, "_itens_no_contexto", 0) + 1
        if self._itens_no_contexto > ITENS_POR_CONTEXTO:
            await self._novo_contexto()
            self._itens_no_contexto = 1
        await self.contexto.tracing.start(screenshots=True, snapshots=False, sources=False)
        self._rastreando = True

    async def _novo_contexto(self) -> None:
        """Fecha o contexto do navegador e abre outro igual (o mesmo navegador)."""
        assert self.ctx is not None and self.ctx.navegador is not None and self.contexto is not None
        await self.contexto.close()
        self.contexto = await self.ctx.navegador.new_context(user_agent=self.ua, viewport=self.viewport, locale="pt-BR",  # type: ignore[arg-type]
                                                             accept_downloads=True)
        for padrao, tratador in self.ctx.rotas_navegador:
            await self.contexto.route(padrao, tratador)
        self.pagina = await self.contexto.new_page()
        self.pagina.set_default_timeout(45000)
        self.ao_renovar()

    def ao_renovar(self) -> None:
        """Gancho: o que a fonte guarda sobre a página aberta deixa de valer."""

    def disco(self) -> None:
        """Chamado no começo de cada item: para a fonte se o disco estiver quase cheio."""
        if getattr(self, "_disco_cheio", None):
            raise PortalMudou(self._disco_cheio)

    def recorte(self, html: str, url: str) -> str:
        """O pedaço da tela HTML que vale guardar como original (cada casa diz o seu)."""
        return html

    def absoluto(self, href: str, base: str | None = None) -> str:
        return urljoin(base or self.inicio, href)

    async def gesto(self, acao: Callable[[], Awaitable[Any]], quer: Callable[[Response], bool] | None = None, *,
                    tipo: str = "html", timeout: int | None = None, guardar: bool = True) -> tuple[Response | None, bytes, str | None]:
        """Um gesto na tela (escolher, clicar) que faz a página pedir algo ao servidor.
        Espera a vez do domínio, faz o gesto, espera a resposta que casa com `quer` e
        guarda o corpo dela como original. Sem `quer`, só espera a vez e faz o gesto."""
        assert self.pagina is not None
        async with self.educacao.vez(self.inicio):
            if quer is None:
                await acao()
                return None, b"", None
            try:
                async with self.pagina.expect_response(quer, timeout=timeout or self.timeout_resposta) as info:
                    await acao()
                r = await info.value
            except Exception as e:
                if type(e).__name__ == "TimeoutError":
                    raise FalhaTransitoria(f"a tela não recebeu a resposta esperada em {timeout or self.timeout_resposta} ms") from e
                raise
        if r.status >= 500 or r.status == 429:
            raise FalhaTransitoria(f"HTTP {r.status} em {r.url}")
        try:
            corpo = await r.body()
        except Exception as e:  # a página navegou antes de o corpo ser lido
            raise FalhaTransitoria(f"corpo da resposta indisponível ({type(e).__name__}) em {r.url}") from e
        # guardar=False: a fonte guarda ela mesma um trecho (a página inteira é menu repetido).
        # Uma tela HTML é guardada enxuta (sem scripts, estilos e SVG); JSON e CSV, como vieram.
        h = None
        if guardar:
            guardado = self.recorte(enxuto(decodificar(corpo)), r.url).encode("utf-8") if tipo == "html" else corpo
            h = guardar_original(self.con, self.id, guardado, r.url, tipo)
        return r, corpo, h
