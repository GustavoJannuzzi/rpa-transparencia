"""Caminhos e parâmetros da coleta. Tudo que muda entre máquinas sai daqui."""

from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
VERSAO_ROBO = "0.1.0"


def _dados() -> Path:
    return Path(os.environ.get("RPA_DADOS", RAIZ / "dados"))


def dados() -> Path:
    return _dados()


def banco() -> Path:
    return _dados() / "estado.db"


def cache() -> Path:
    return _dados() / "cache"


def originais() -> Path:
    return _dados() / "originais"


def evidencias() -> Path:
    return _dados() / "evidencias"


def destino_plataforma() -> Path:
    return Path(os.environ.get("RPA_PUBLICAR", RAIZ / "plataforma" / "public" / "dados"))


def destino_relatorio() -> Path:
    return Path(os.environ.get("RPA_RELATORIO", RAIZ / "relatorio"))


# User-Agent: diz o que é e não leva dado pessoal. Cada fonte escolhe o seu,
# porque um portal recusa "HeadlessChrome" e outro só funciona com um
# User-Agent de navegador (ver docs/etapa-0.md).
UA_ROBO = "rpa-transparencia/0.1 (robo de coleta de dados publicos; codigo aberto)"
UA_NAVEGADOR_ROBO = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "HeadlessChrome/146.0.0.0 Safari/537.36 rpa-transparencia/0.1 (robo de coleta de dados publicos)"
)

# Pausa mínima entre duas requisições ao mesmo portal, em segundos.
PAUSA_PADRAO = float(os.environ.get("RPA_PAUSA", "1.0"))

# Repetição com espera.
TENTATIVAS = int(os.environ.get("RPA_TENTATIVAS", "4"))
ESPERA_BASE = float(os.environ.get("RPA_ESPERA_BASE", "2.0"))

# Arquivo baixado mais novo que isto é reaproveitado (horas).
VALIDADE_CACHE_H = float(os.environ.get("RPA_VALIDADE_CACHE_H", "20"))
