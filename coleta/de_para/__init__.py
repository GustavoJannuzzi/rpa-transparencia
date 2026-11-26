"""Tabelas de-para: como cada sistema chama a mesma coisa -> o valor único.

O que não tem de-para vai para revisão. Os CSV desta pasta são a parte que uma
pessoa edita; o código só lê.
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

from ..nucleo.texto import normalizar_nome

PASTA = Path(__file__).parent

# Guarda de privacidade usada na LEITURA (antes de qualquer gravação): só cargo de
# parlamentar mantém nome. É de propósito mais estreita que a tabela de cargos;
# cargo que não casa aqui perde o nome na hora e, se for parlamentar com um nome
# de cargo novo, cai na revisão por "cargo sem de-para".
RE_CARGO_PARLAMENTAR = re.compile(r"(VEREADORA?|PRESIDENTE|PRESIDENTE DA CAMARA( MUNICIPAL)?( DE CURITIBA)?)")


def eh_cargo_parlamentar(cargo: str | None) -> bool:
    return bool(RE_CARGO_PARLAMENTAR.fullmatch(normalizar_nome(cargo)))


@lru_cache(maxsize=None)
def _tabela(nome: str) -> dict[str, dict[str, str]]:
    caminho = PASTA / nome
    with caminho.open(encoding="utf-8", newline="") as f:
        linhas = [l for l in csv.DictReader(f) if not (l.get("origem") or "").startswith("#")]
    return {(l["fonte"], normalizar_nome(l["origem"])): l for l in linhas}  # type: ignore[misc]


def cargo(fonte: str, original: str | None) -> str | None:
    """'VEREADORA', 'Vereador', 'PRESIDENTE DA CÂMARA MUNICIPAL' -> 'vereador' | 'servidor' | None (sem de-para)."""
    t = _tabela("cargos.csv")
    n = normalizar_nome(original)
    linha = t.get((fonte, n)) or t.get(("*", n))
    return linha["papel"] if linha else None


def categoria(fonte: str, original: str | None) -> tuple[str, str] | None:
    """Categoria da fonte -> (id único, rótulo). None = sem de-para."""
    t = _tabela("categorias.csv")
    n = normalizar_nome(original)
    linha = t.get((fonte, n)) or t.get(("*", n))
    return (linha["categoria"], linha["rotulo"]) if linha else None


def regra_negativo(fonte: str, categoria_unica: str) -> str | None:
    """Quando um valor negativo é esperado (compensação) e não um erro."""
    t = _tabela("negativos.csv")
    linha = t.get((fonte, normalizar_nome(categoria_unica)))
    return linha["explicacao"] if linha else None
