"""Lê `entidades.toml`: as casas que a coleta cobre e, para cada fornecedor, as
entidades que o adaptador dele atende. O código dos adaptadores não sabe de
município nenhum; tudo que muda de uma casa para outra vem daqui."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from .modelo import CASAS_FIXAS, Casa
from .nucleo.texto import normalizar_nome

ARQUIVO = Path(__file__).with_name("entidades.toml")


@dataclass(frozen=True)
class EntidadeElotech:
    fonte: str
    casa: str
    municipio: str
    ibge: int
    regiao: str
    host: str
    entidade: int
    cnpj: str
    de: int
    ate: int
    tela: str

    @property
    def api(self) -> str:
        return f"{self.host}/portaltransparencia-api"


@dataclass(frozen=True)
class EntidadeAssembleia:
    fonte: str
    casa: str
    uf: str
    nome: str
    cargo: str
    sistema: str
    modo: str
    extra: dict


@cache
def _bruto() -> dict:
    with ARQUIVO.open("rb") as f:
        return tomllib.load(f)


def periodo() -> tuple[int, int]:
    p = _bruto()["periodo"]
    return int(p["de"]), int(p["ate"])


@cache
def elotech() -> tuple[EntidadeElotech, ...]:
    de, ate = periodo()
    out = []
    for e in _bruto().get("elotech", []):
        out.append(EntidadeElotech(
            fonte=e["fonte"], casa=e["casa"], municipio=e["municipio"], ibge=int(e["ibge"]), regiao=e["regiao"],
            host=e["host"].rstrip("/"), entidade=int(e["entidade"]), cnpj=e["cnpj"], de=int(e.get("de", de)),
            ate=int(e.get("ate", ate)), tela=e.get("tela") or f"{e['host'].rstrip('/')}/portaltransparencia/{e['entidade']}",
        ))
    return tuple(out)


@cache
def assembleias() -> dict[str, EntidadeAssembleia]:
    out = {}
    chaves = {"fonte", "casa", "uf", "nome", "cargo", "sistema", "modo"}
    for a in _bruto().get("assembleia", []):
        out[a["fonte"]] = EntidadeAssembleia(
            fonte=a["fonte"], casa=a["casa"], uf=a["uf"], nome=a["nome"], cargo=a["cargo"], sistema=a["sistema"],
            modo=a["modo"], extra={k: v for k, v in a.items() if k not in chaves})
    return out


@cache
def casas() -> dict[str, Casa]:
    """Todas as casas que a coleta cobre, pelo id usado no banco e na plataforma."""
    out = dict(CASAS_FIXAS)
    for e in elotech():
        if e.casa not in out:
            out[e.casa] = Casa(id=e.casa, tipo="camara_municipal", esfera="municipal", nome=f"Câmara Municipal de {e.municipio}",
                               uf="PR", municipio=e.municipio, ibge=e.ibge, cargo="vereador")
    for a in assembleias().values():
        out[a.casa] = Casa(id=a.casa, tipo="assembleia", esfera="estadual", nome=a.nome, uf=a.uf, cargo=a.cargo)
    return out


def casa_do_municipio(nome: str) -> Casa | None:
    alvo = normalizar_nome(nome)
    return next((c for c in casas().values() if c.municipio and normalizar_nome(c.municipio) == alvo), None)
