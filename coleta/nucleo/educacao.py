"""Coleta educada: uma requisição por vez em cada portal, pausa entre elas e
respeito ao robots.txt. Vale para httpx e para o navegador."""

from __future__ import annotations

import asyncio
import time
import urllib.robotparser
from urllib.parse import urlsplit

import httpx

from .. import config
from .erros import BloqueadoPorRobots


class Educacao:
    def __init__(self, pausa: float | None = None, ua: str = config.UA_ROBO):
        self.pausa = config.PAUSA_PADRAO if pausa is None else pausa
        self.ua = ua
        self._travas: dict[str, asyncio.Lock] = {}
        self._ultima: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.politicas: dict[str, str] = {}

    def _host(self, url: str) -> str:
        p = urlsplit(url)
        return f"{p.scheme}://{p.netloc}"

    def vez(self, url: str) -> "_Vez":
        """Espera a vez de falar com o host de `url`. Uso: `async with educacao.vez(url):`."""
        host = self._host(url)
        trava = self._travas.setdefault(host, asyncio.Lock())
        return _Vez(self, host, trava)

    async def verificar_robots(self, url: str, cliente: httpx.AsyncClient | None = None) -> None:
        host = self._host(url)
        if host not in self._robots:
            self._robots[host] = await self._carregar_robots(host, cliente)
        rp = self._robots[host]
        if rp is not None and not rp.can_fetch(self.ua, url):
            raise BloqueadoPorRobots(f"robots.txt de {host} não permite {urlsplit(url).path}")

    async def _carregar_robots(self, host: str, cliente: httpx.AsyncClient | None):
        url = host + "/robots.txt"
        fechar = cliente is None
        cliente = cliente or httpx.AsyncClient(timeout=20, headers={"User-Agent": self.ua}, follow_redirects=True)
        try:
            r = await cliente.get(url)
        except httpx.HTTPError:
            self.politicas[host] = "robots.txt não respondeu"
            return None
        finally:
            if fechar:
                await cliente.aclose()
        tipo = r.headers.get("content-type", "")
        # Vários portais devolvem a própria página (ou uma página de erro com 200)
        # no lugar do robots.txt. Isso não é política nenhuma.
        if r.status_code != 200 or "text/plain" not in tipo:
            self.politicas[host] = f"sem robots.txt (HTTP {r.status_code}, {tipo.split(';')[0] or 'sem tipo'})"
            return None
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(r.text.splitlines())
        self.politicas[host] = "robots.txt lido e respeitado"
        return rp


class _Vez:
    def __init__(self, ed: Educacao, host: str, trava: asyncio.Lock):
        self.ed, self.host, self.trava = ed, host, trava

    async def __aenter__(self):
        await self.trava.acquire()
        espera = self.ed._ultima.get(self.host, 0) + self.ed.pausa - time.monotonic()
        if espera > 0:
            await asyncio.sleep(espera)

    async def __aexit__(self, *exc):
        self.ed._ultima[self.host] = time.monotonic()
        self.trava.release()
