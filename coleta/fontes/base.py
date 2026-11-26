"""O contrato de uma fonte. Fonte nova = pasta nova em fontes/ + tabela em de_para/."""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from .. import config
from ..modelo import Descoberta, ItemInventario, Procedencia, Resultado, SistemaOrigem
from ..nucleo.banco import agora
from ..nucleo.educacao import Educacao
from ..nucleo.erros import FalhaTransitoria
from ..nucleo.evidencia import guardar_original

if TYPE_CHECKING:  # pragma: no cover
    from playwright.async_api import Browser, BrowserContext, Page


@dataclass
class Contexto:
    con: sqlite3.Connection
    navegador: Browser | None = None
    gravar_video: bool = False
    # Para os testes: trocar o transporte HTTP (respostas gravadas, falhas injetadas).
    transporte_http: httpx.AsyncBaseTransport | None = None
    # Para os testes: rotas do Playwright (servir amostras, injetar falhas).
    rotas_navegador: list[tuple[str, Any]] = field(default_factory=list)


class Fonte(ABC):
    id: str
    sistema: SistemaOrigem
    ua: str = config.UA_ROBO
    pausa: float | None = None
    usa_navegador: bool = False

    def __init__(self) -> None:
        self.educacao = Educacao(self.pausa, self.ua)
        self.http: httpx.AsyncClient | None = None
        self.ctx: Contexto | None = None

    # ---- ciclo de vida -------------------------------------------------
    async def abrir(self, ctx: Contexto) -> None:
        self.ctx = ctx
        self.http = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=20.0),
            headers={"User-Agent": self.ua},
            follow_redirects=True,
            transport=ctx.transporte_http,
        )

    async def fechar(self) -> None:
        if self.http:
            await self.http.aclose()

    # ---- o que cada fonte implementa ------------------------------------
    @abstractmethod
    async def descobrir(self) -> Descoberta: ...

    @abstractmethod
    async def coletar_item(self, item: ItemInventario) -> Resultado: ...

    async def antes_do_item(self, item: ItemInventario) -> None:  # noqa: B027 (gancho opcional, vazio de propósito)
        """Gancho: fontes com navegador começam a gravar o rastro aqui."""

    async def evidencia(self, pasta: Path, sucesso: bool) -> list[str]:
        """Gancho: grava print/rastro no ponto do erro. Devolve os arquivos gravados."""
        return []

    # ---- ajudas comuns --------------------------------------------------
    @property
    def con(self) -> sqlite3.Connection:
        assert self.ctx is not None
        return self.ctx.con

    async def baixar(self, url: str, *, metodo: str = "GET", tipo: str = "json", **kw) -> tuple[httpx.Response, str]:
        """Requisição educada com robots, pausa e original guardado com hash."""
        assert self.http is not None
        await self.educacao.verificar_robots(url, self.http)
        async with self.educacao.vez(url):
            try:
                r = await self.http.request(metodo, url, **kw)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                raise FalhaTransitoria(f"{type(e).__name__} em {url}") from e
        if r.status_code >= 500 or r.status_code == 429:
            raise FalhaTransitoria(f"HTTP {r.status_code} em {url}")
        r.raise_for_status()
        h = guardar_original(self.con, self.id, r.content, str(r.request.url), tipo)
        return r, h

    def procedencia(self, url: str, h: str, localizador: str | None = None) -> Procedencia:
        return Procedencia(fonte=self.id, url=url, hash_original=h, coletado_em=agora(), localizador=localizador)


class FonteNavegador(Fonte):
    """Fonte que precisa de navegador. Um contexto por fonte, rastro por item."""

    usa_navegador = True
    viewport = {"width": 1400, "height": 1000}

    def __init__(self) -> None:
        super().__init__()
        self.contexto: BrowserContext | None = None
        self.pagina: Page | None = None
        self._rastreando = False

    async def abrir(self, ctx: Contexto) -> None:
        await super().abrir(ctx)
        assert ctx.navegador is not None, "fonte com navegador precisa do Playwright aberto"
        opcoes: dict[str, Any] = dict(user_agent=self.ua, viewport=self.viewport, locale="pt-BR", accept_downloads=True)
        if ctx.gravar_video:
            pasta = config.evidencias() / "videos" / self.id
            pasta.mkdir(parents=True, exist_ok=True)
            opcoes["record_video_dir"] = str(pasta)
            opcoes["record_video_size"] = self.viewport
        self.contexto = await ctx.navegador.new_context(**opcoes)
        for padrao, tratador in ctx.rotas_navegador:
            await self.contexto.route(padrao, tratador)
        self.pagina = await self.contexto.new_page()
        self.pagina.set_default_timeout(45000)

    async def fechar(self) -> None:
        if self.contexto:
            await self.contexto.close()
        await super().fechar()

    async def antes_do_item(self, item: ItemInventario) -> None:
        if self.contexto and not self._rastreando:
            await self.contexto.tracing.start(screenshots=True, snapshots=True, sources=False)
            self._rastreando = True

    async def evidencia(self, pasta: Path, sucesso: bool) -> list[str]:
        arquivos: list[str] = []
        if not sucesso and self.pagina is not None:
            try:
                p = pasta / "tela.png"
                await self.pagina.screenshot(path=str(p), full_page=True)
                arquivos.append(p.name)
                (pasta / "pagina.html").write_text(await self.pagina.content(), encoding="utf-8")
                arquivos.append("pagina.html")
            except Exception:  # a página pode ter caído junto
                pass
        if self.contexto and self._rastreando:
            try:
                if sucesso:
                    await self.contexto.tracing.stop()
                else:
                    p = pasta / "rastro.zip"
                    await self.contexto.tracing.stop(path=str(p))
                    arquivos.append(p.name)
            finally:
                self._rastreando = False
        return arquivos

    async def ir(self, url: str, **kw) -> None:
        assert self.pagina is not None
        await self.educacao.verificar_robots(url, self.http)
        async with self.educacao.vez(url):
            try:
                resp = await self.pagina.goto(url, **kw)
            except Exception as e:
                raise FalhaTransitoria(f"{type(e).__name__} ao abrir {url}: {str(e)[:200]}") from e
        if resp is not None and (resp.status >= 500 or resp.status == 429):
            raise FalhaTransitoria(f"HTTP {resp.status} ao abrir {url}")
