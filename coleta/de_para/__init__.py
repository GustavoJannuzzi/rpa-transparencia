"""Tabelas de-para: como cada sistema chama a mesma coisa -> o valor único.

O que não tem de-para vai para revisão. Os CSV desta pasta são a parte que uma
pessoa edita; o código só lê.
"""

from __future__ import annotations

import csv
import re
from functools import cache
from pathlib import Path

from ..nucleo.texto import normalizar_nome

PASTA = Path(__file__).parent

# Guarda de privacidade usada na LEITURA (antes de qualquer gravação): só cargo de
# parlamentar mantém nome. É de propósito mais estreita que a tabela de cargos;
# cargo que não casa aqui perde o nome na hora e, se for parlamentar com um nome
# de cargo novo, cai na revisão por "cargo sem de-para".
# "PRESIDENTE" sozinho, numa diária da Câmara, é o presidente da Câmara; qualquer
# outro complemento que não seja "da Câmara" (comissão, conselho) não passa.
RE_CARGO_PARLAMENTAR = re.compile(
    r"(VEREADORA?|VEREADORA? PRESIDENTE|PRESIDENTE|PRESIDENTE (D[AE] )?CAMARA( MUNICIPAL)?( DE [A-Z]+( [A-Z]+){0,3})?)")
# O que parece cargo de vereador escrito de outro jeito (erro de digitação, abreviação):
# não guarda nome e vai para revisão, em vez de virar servidor.
# "Primeiro Secretário" e "Segundo Secretário" são cargos da Mesa, de vereador.
RE_PARECE_PARLAMENTAR = re.compile(r"\bV[EA]?R[EIA]{0,2}A?DOR|\bVEREA|\bVER\b|\bPRESID|\bEDIL|\b(PRIMEIR|SEGUND|TERCEIR)[OA] SECRETARI")
# Cargo do Executivo municipal (Prefeitura) numa consulta de diárias da Câmara: a
# fonte está misturando entidades (visto no Betha de Cornélio Procópio, 26/11/2026).
RE_CARGO_EXECUTIVO = re.compile(r"\bPREFEIT|\bSUBPREFEIT|\bSECRETARI[OA] MUN|\bSECRETARIA MUNICIPAL|\bDO MUNICIPIO\b")
# Fontes com a tabela de cargos revisada à mão (cargos.csv). Nas outras, cargo que
# não é de parlamentar e não se parece com um é de servidor: entra só no agregado.
FONTES_COM_TABELA = frozenset({"cmc_legado", "cmc_elotech", "cmc_prefeitura", "cmc_betha"})


def eh_cargo_parlamentar(cargo: str | None) -> bool:
    return bool(RE_CARGO_PARLAMENTAR.fullmatch(normalizar_nome(cargo)))


def grupo_da_fonte(fonte: str) -> str:
    """'equiplano_pien' -> 'equiplano': a linha da tabela vale para todas as câmaras do fornecedor."""
    return fonte.split("_", 1)[0] if fonte.startswith(("elotech_", "betha_", "equiplano_", "pronim_")) else fonte


def eh_cargo_do_executivo(cargo: str | None) -> bool:
    return bool(RE_CARGO_EXECUTIVO.search(normalizar_nome(cargo)))


def papel_por_regra(original: str | None) -> str | None:
    """Papel pelo texto do cargo, para fontes sem tabela revisada. None = não dá para
    saber (cargo vazio, ou parecido com o de vereador sem ser): vai para revisão."""
    n = normalizar_nome(original)
    if not n:
        return None
    if eh_cargo_parlamentar(original):
        return "vereador"
    if RE_PARECE_PARLAMENTAR.search(n):
        return None
    return "servidor"


@cache
def _tabela(nome: str) -> dict[tuple[str, str], dict[str, str]]:
    caminho = PASTA / nome
    with caminho.open(encoding="utf-8", newline="") as f:
        linhas = [l for l in csv.DictReader(f) if not (l.get("origem") or "").startswith("#")]
    return {(l["fonte"], normalizar_nome(l["origem"])): l for l in linhas}


def cargo(fonte: str, original: str | None) -> str | None:
    """'VEREADORA', 'Vereador', 'PRESIDENTE DA CÂMARA MUNICIPAL' -> 'vereador' | 'servidor' | None (sem de-para)."""
    t = _tabela("cargos.csv")
    n = normalizar_nome(original)
    linha = t.get((fonte, n)) or t.get((grupo_da_fonte(fonte), n)) or t.get(("*", n))
    if linha:
        return linha["papel"]
    return None if fonte in FONTES_COM_TABELA else papel_por_regra(original)


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


def grafia(fonte: str, nome: str) -> str:
    """O nome como a fonte escreve -> o nome da pessoa, pela tabela de grafias revisada
    à mão (erro de digitação da própria fonte). Sem linha na tabela, o nome fica como
    veio, com espaços simples; o nome parecido com outro da mesma casa vai para a
    revisão na conferência."""
    import re as _re

    limpo = _re.sub(r"\s+", " ", nome or "").strip()
    linha = _tabela("grafias.csv").get((fonte, normalizar_nome(limpo)))
    return linha["nome"] if linha else limpo
