"""Registro das fontes.

Fonte com sistema próprio (Câmara dos Deputados, cada assembleia) é uma pasta aqui
e uma linha nesta lista. Casa nova num fornecedor que já tem adaptador (outra
câmara no Elotech, no Betha ou no Equiplano) não muda código: é um bloco novo em `entidades.toml`.
"""

from __future__ import annotations

from .. import entidades
from .alesp.fonte import Alesp
from .almg.fonte import Almg
from .base import Fonte
from .betha.fonte import BethaCloud
from .camara_deputados.fonte import CamaraDeputados
from .cldf.fonte import Cldf
from .cmc_betha.fonte import CmcBetha
from .cmc_elotech.fonte import CmcElotechAPI
from .cmc_legado.fonte import CmcLegado
from .cmc_prefeitura.fonte import CmcPrefeitura
from .elotech.fonte import ElotechAPI
from .equiplano.fonte import Equiplano
from .tse.fonte import Tse

ASSEMBLEIAS: dict[str, type[Fonte]] = {"cldf": Cldf, "almg": Almg, "alesp": Alesp}


def _construir() -> list[Fonte]:
    out: list[Fonte] = [CamaraDeputados(), CmcLegado()]
    for e in entidades.elotech():
        out.append(CmcElotechAPI() if e.fonte == "cmc_elotech" else ElotechAPI(e))
    out.append(CmcPrefeitura())
    for b in entidades.betha():
        out.append(CmcBetha() if b.fonte == "cmc_betha" else BethaCloud(b))
    out += [Equiplano(e) for e in entidades.equiplano()]
    for fid, a in entidades.assembleias().items():
        out.append(ASSEMBLEIAS[fid](a))  # type: ignore[call-arg]
    # o TSE vem por último: o recorte dele depende das câmaras acima
    out.append(Tse())
    return out


FONTES: list[Fonte] = _construir()


def grupo(f: Fonte) -> str:
    return getattr(f, "grupo", f.id)


def criar(fonte_id: str) -> Fonte:
    """Uma instância nova (cada rodada abre e fecha a sua)."""
    for f in _construir():
        if f.id == fonte_id:
            return f
    raise KeyError(fonte_id)
