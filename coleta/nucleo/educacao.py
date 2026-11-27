"""Coleta educada: uma requisição por vez em cada portal, pausa entre elas e
respeito ao robots.txt. Vale para httpx e para o navegador.

A pausa de cada domínio é a maior entre o piso do projeto (ou o da fonte) e o
Crawl-delay que o robots.txt daquele domínio pede. O robots.txt é lido antes da
primeira requisição ao domínio, então a primeira já espera o que ele pede."""

from __future__ import annotations

import asyncio
import time
import urllib.robotparser
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

import httpx

from .. import config
from .erros import BloqueadoPorRobots

# (url) -> (status HTTP, content-type, texto)
Buscar = Callable[[str], Awaitable[tuple[int, str, str]]]


class Educacao:
    def __init__(self, pausa: float | None = None, ua: str = config.UA_ROBO):
        self.pausa = config.PAUSA_PADRAO if pausa is None else pausa
        self.ua = ua
        self._travas: dict[str, asyncio.Lock] = {}
        self._ultima: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._pausa_host: dict[str, float] = {}
        self.politicas: dict[str, str] = {}

    def pausa_de(self, url: str) -> float:
        """A pausa que vale para o domínio de `url`: o piso ou o Crawl-delay, o maior."""
        return self._pausa_host.get(self._host(url), self.pausa)

    def _host(self, url: str) -> str:
        p = urlsplit(url)
        return f"{p.scheme}://{p.netloc}"

    def vez(self, url: str) -> _Vez:
        """Espera a vez de falar com o host de `url`. Uso: `async with educacao.vez(url):`."""
        host = self._host(url)
        trava = self._travas.setdefault(host, asyncio.Lock())
        return _Vez(self, host, trava)

    async def verificar_robots(self, url: str, cliente: httpx.AsyncClient | None = None, buscar: Buscar | None = None) -> None:
        """`buscar`: outro jeito de pedir o robots.txt (o do navegador), usado só quando o
        servidor não manda a cadeia de certificados inteira e o httpx não consegue conferir."""
        host = self._host(url)
        if host not in self._robots:
            self._robots[host] = await self._carregar_robots(host, cliente, buscar)
        rp = self._robots[host]
        if rp is not None and not rp.can_fetch(self.ua, url):
            raise BloqueadoPorRobots(f"robots.txt de {host} não permite {urlsplit(url).path}")

    async def _carregar_robots(self, host: str, cliente: httpx.AsyncClient | None, buscar: Buscar | None = None):
        url = host + "/robots.txt"
        fechar = cliente is None
        cliente = cliente or httpx.AsyncClient(timeout=20, headers={"User-Agent": self.ua}, follow_redirects=True)
        try:
            r = await cliente.get(url)
            status, tipo, texto = r.status_code, r.headers.get("content-type", ""), r.text
        except httpx.HTTPError as e:
            if buscar is None or "CERTIFICATE_VERIFY_FAILED" not in str(e):
                self.politicas[host] = "robots.txt não respondeu"
                return None
            # O servidor não manda o certificado intermediário: o navegador completa a cadeia
            # sozinho (como faz para qualquer pessoa), o httpx não. O robots.txt vem por ele.
            try:
                status, tipo, texto = await buscar(url)
            except Exception:
                self.politicas[host] = "robots.txt não respondeu"
                return None
        finally:
            if fechar:
                await cliente.aclose()
        return self._interpretar(host, status, tipo, texto)

    def _interpretar(self, host: str, status: int, tipo: str, texto: str):
        # Vários portais devolvem a própria página (ou uma página de erro com 200)
        # no lugar do robots.txt. Isso não é política nenhuma.
        if status != 200 or "text/plain" not in tipo:
            self.politicas[host] = f"sem robots.txt (HTTP {status}, {tipo.split(';')[0] or 'sem tipo'})"
            return None
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(texto.splitlines())
        atraso = rp.crawl_delay(self.ua)
        if atraso is not None and float(atraso) > self.pausa:
            self._pausa_host[host] = float(atraso)
            self.politicas[host] = f"robots.txt lido e respeitado; Crawl-delay de {float(atraso):g} s"
        else:
            self.politicas[host] = "robots.txt lido e respeitado"
        return rp


class _Vez:
    def __init__(self, ed: Educacao, host: str, trava: asyncio.Lock):
        self.ed, self.host, self.trava = ed, host, trava

    async def __aenter__(self):
        await self.trava.acquire()
        pausa = self.ed._pausa_host.get(self.host, self.ed.pausa)
        espera = self.ed._ultima.get(self.host, 0) + pausa - time.monotonic()
        if espera > 0:
            await asyncio.sleep(espera)

    async def __aexit__(self, *exc):
        self.ed._ultima[self.host] = time.monotonic()
        self.trava.release()
