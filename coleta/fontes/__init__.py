"""Registro das fontes. Fonte nova: uma pasta aqui e uma linha nesta lista."""

from __future__ import annotations

from .base import Fonte
from .camara_deputados.fonte import CamaraDeputados
from .tse.fonte import Tse
from .cmc_betha.fonte import CmcBetha
from .cmc_elotech.fonte import CmcElotechAPI
from .cmc_legado.fonte import CmcLegado
from .cmc_prefeitura.fonte import CmcPrefeitura

FONTES: list[type[Fonte]] = [
    CamaraDeputados,
    CmcLegado,
    CmcElotechAPI,
    CmcPrefeitura,
    CmcBetha,
    Tse,
]


def criar(fonte_id: str) -> Fonte:
    for f in FONTES:
        if f.id == fonte_id:
            return f()
    raise KeyError(fonte_id)
