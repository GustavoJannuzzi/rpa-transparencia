"""O portal legado servido das amostras, sem rede: a aplicação React gravada e os
PDFs (tarjados). Falhas são injetadas por arquivo: erro 500, lentidão e queda de
sessão (a resposta de "Token inválido." que a própria aplicação trata)."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict

import httpx

from .conftest import AMOSTRAS

SPA = AMOSTRAS / "cmc_legado" / "spa"
PDFS = AMOSTRAS / "cmc_legado"


class Replay:
    def __init__(self, falhas: dict[str, list[str]] | None = None):
        # falhas["Diarias_2015.pdf"] = ["500", "lento", "sessao"]: uma por pedido, na ordem
        self.falhas = {k: list(v) for k, v in (falhas or {}).items()}
        self.pedidos: dict[str, int] = defaultdict(int)

    async def rota(self, route):
        url = route.request.url
        if ":3000/api/download/" in url:
            nome = url.rsplit("/", 1)[1]
            self.pedidos[nome] += 1
            fila = self.falhas.get(nome, [])
            falha = fila.pop(0) if fila else None
            if falha == "500":
                return await route.fulfill(status=500, body="erro interno")
            if falha == "sessao":
                return await route.fulfill(status=401, content_type="application/json", body=json.dumps({"error": "Token inválido."}))
            if falha == "lento":
                await asyncio.sleep(2.5)
            arq = PDFS / nome
            if not arq.exists():
                return await route.fulfill(status=404, body="")
            return await route.fulfill(status=200, content_type="application/pdf", body=arq.read_bytes(),
                                       headers={"Access-Control-Allow-Origin": "*"})
        if url.startswith("https://transparencia-legada.cmc.pr.gov.br/static/"):
            caminho = SPA / url.split("transparencia-legada.cmc.pr.gov.br/", 1)[1].split("?")[0]
            if not caminho.exists():  # imagens da aplicação não foram gravadas: não fazem falta ao robô
                return await route.fulfill(status=404, body="")
            tipo = "text/css" if caminho.suffix == ".css" else "application/javascript"
            return await route.fulfill(status=200, content_type=tipo, body=caminho.read_bytes())
        if url.startswith("https://transparencia-legada.cmc.pr.gov.br"):
            return await route.fulfill(status=200, content_type="text/html", body=(SPA / "index.html").read_bytes())
        return await route.abort()  # fontes externas, analytics: nada sai da máquina


def transporte_sem_rede() -> httpx.MockTransport:
    """robots.txt (e qualquer outra chamada httpx) respondidos localmente: 404 = sem política."""
    return httpx.MockTransport(lambda req: httpx.Response(404, text="não encontrado"))
