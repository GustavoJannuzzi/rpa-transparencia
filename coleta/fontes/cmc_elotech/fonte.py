"""Câmara de Curitiba no Elotech (2017–2023 nas diárias; pessoal até hoje).

É o adaptador genérico do Elotech (`fontes/elotech`) com a entidade de Curitiba,
que está em `entidades.toml`. Fica aqui com o nome antigo porque os testes, as
amostras e o banco chamam a fonte assim.
"""

from __future__ import annotations

from ...entidades import elotech
from ..elotech.fonte import CAMPOS_DIARIA, CAMPOS_SERVIDOR, ElotechAPI

ENTIDADE_CURITIBA = next(e for e in elotech() if e.fonte == "cmc_elotech")
API = ENTIDADE_CURITIBA.api
TELA = ENTIDADE_CURITIBA.tela
ENTIDADE = str(ENTIDADE_CURITIBA.entidade)

__all__ = ["API", "CAMPOS_DIARIA", "CAMPOS_SERVIDOR", "ENTIDADE", "TELA", "CmcElotechAPI"]


class CmcElotechAPI(ElotechAPI):
    def __init__(self) -> None:
        super().__init__(ENTIDADE_CURITIBA)
