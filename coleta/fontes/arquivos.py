"""Download de arquivo grande com cache, hash em streaming e coleta educada."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from .. import config
from ..nucleo.erros import FalhaTransitoria
from ..nucleo.evidencia import registrar_original_arquivo
from .base import Fonte


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


async def baixar_arquivo(fonte: Fonte, url: str, destino: Path, *, validade_h: float | None = None) -> tuple[Path, str, bool]:
    """Baixa `url` para `destino` se não houver cópia mais nova que `validade_h`.
    Devolve (caminho, sha256, veio_do_cache)."""
    validade_h = config.VALIDADE_CACHE_H if validade_h is None else validade_h
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists() and (time.time() - destino.stat().st_mtime) < validade_h * 3600:
        h = sha256_arquivo(destino)
        registrar_original_arquivo(fonte.con, fonte.id, destino, url, destino.suffix.lstrip("."), h)
        return destino, h, True
    assert fonte.http is not None
    await fonte.educacao.verificar_robots(url, fonte.http)
    parcial = destino.with_suffix(destino.suffix + ".parcial")
    async with fonte.educacao.vez(url):
        try:
            async with fonte.http.stream("GET", url) as r:
                if r.status_code >= 500:
                    raise FalhaTransitoria(f"HTTP {r.status_code} em {url}")
                r.raise_for_status()
                with parcial.open("wb") as f:
                    async for bloco in r.aiter_bytes(1 << 20):
                        f.write(bloco)
        except Exception as e:
            if isinstance(e, FalhaTransitoria):
                raise
            raise FalhaTransitoria(f"{type(e).__name__} ao baixar {url}") from e
    parcial.replace(destino)
    h = sha256_arquivo(destino)
    registrar_original_arquivo(fonte.con, fonte.id, destino, url, destino.suffix.lstrip("."), h)
    return destino, h, False
