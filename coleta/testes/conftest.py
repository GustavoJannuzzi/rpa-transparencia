from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from coleta import config
from coleta.nucleo.banco import conectar

AMOSTRAS = Path(__file__).parent / "amostras"


@pytest.fixture
def dados_tmp(tmp_path, monkeypatch):
    """Cada teste com o seu próprio dados/ (banco, originais, evidências)."""
    monkeypatch.setenv("RPA_DADOS", str(tmp_path / "dados"))
    monkeypatch.setenv("RPA_PUBLICAR", str(tmp_path / "publicar"))
    monkeypatch.setenv("RPA_RELATORIO", str(tmp_path / "relatorio"))
    monkeypatch.setattr(config, "TENTATIVAS", 4)
    monkeypatch.setattr(config, "ESPERA_BASE", 0.01)
    monkeypatch.setattr(config, "PAUSA_PADRAO", 0.0)
    return tmp_path / "dados"


@pytest.fixture
def con(dados_tmp) -> Iterator[sqlite3.Connection]:
    c = conectar()
    yield c
    c.close()
