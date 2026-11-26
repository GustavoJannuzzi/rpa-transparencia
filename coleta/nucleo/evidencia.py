"""Originais com hash (procedência) e evidência no ponto de cada erro."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .. import config
from .banco import agora
from .texto import sha256_bytes, slug


def guardar_original(con: sqlite3.Connection, fonte: str, conteudo: bytes, url: str, tipo: str) -> str:
    """Grava o original como veio e devolve o hash. O mesmo conteúdo não se repete."""
    h = sha256_bytes(conteudo)
    ext = {"pdf": "pdf", "html": "html", "json": "json", "csv": "csv", "zip": "zip"}.get(tipo, "bin")
    pasta = config.originais() / fonte / h[:2]
    caminho = pasta / f"{h}.{ext}"
    if not caminho.exists():
        pasta.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(conteudo)
    con.execute(
        "INSERT OR IGNORE INTO originais(hash, fonte, url, caminho, tipo, tamanho, coletado_em) VALUES(?,?,?,?,?,?,?)",
        (h, fonte, url, str(caminho.relative_to(config.dados())), tipo, len(conteudo), agora()),
    )
    return h


def registrar_original_arquivo(con: sqlite3.Connection, fonte: str, caminho: Path, url: str, tipo: str, h: str) -> None:
    """Para arquivos grandes (zip anual): registra o hash sem copiar de novo."""
    try:
        rel = str(caminho.relative_to(config.dados()))
    except ValueError:
        rel = str(caminho)
    con.execute(
        "INSERT OR IGNORE INTO originais(hash, fonte, url, caminho, tipo, tamanho, coletado_em) VALUES(?,?,?,?,?,?,?)",
        (h, fonte, url, rel, tipo, caminho.stat().st_size, agora()),
    )


def pasta_evidencia(fonte: str, item: str) -> Path:
    carimbo = agora().replace(":", "").replace("-", "")[:15]
    p = config.evidencias() / fonte / f"{carimbo}-{slug(item)[:60]}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def caminho_relativo(p: Path) -> str:
    try:
        return str(p.relative_to(config.dados()))
    except ValueError:
        return str(p)
