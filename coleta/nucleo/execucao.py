"""Executa descobrir e coletar de uma fonte: inventário, retomada, repetição com
espera, evidência no erro e alarme de portal mudou. Não sabe de fonte nenhuma.

É o esqueleto fixo de toda coleta (o "template method" do projeto): para cada item
pendente, confere o disco, chama os ganchos da fonte (`antes_do_item`,
`coletar_item`, `evidencia`) e decide pelo tipo do erro. `FalhaTransitoria` tenta de
novo com espera exponencial; `PortalMudou`, `AcessoRecusado` e `BloqueadoPorRobots`
param a fonte com a evidência do ponto do erro; erro de programa marca o item e
segue para o próximo. O que gravar e como fica em `repositorio.py`.
"""

from __future__ import annotations

import asyncio
import random
import shutil
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .. import config
from ..fontes.base import Fonte
from . import repositorio
from .banco import agora
from .erros import AcessoRecusado, BloqueadoPorRobots, FalhaTransitoria, PortalMudou
from .evidencia import caminho_relativo, pasta_evidencia

# Erros que param a fonte inteira: repetir não adianta, e seguir para o próximo item
# gravaria lixo (portal mudou) ou contornaria uma recusa (captcha, robots.txt).
PARA_A_FONTE = (PortalMudou, AcessoRecusado, BloqueadoPorRobots)


def eco(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)
    sys.stdout.flush()


class Interrompido(Exception):
    """Usado pelo teste de retomada para cortar a coleta no meio."""


@dataclass
class Placar:
    fonte: str
    ok: int = 0
    erro: int = 0
    pulados: int = 0
    tentativas_extras: int = 0
    parou: str | None = None
    detalhes: list[str] = field(default_factory=list)


async def descobrir(fonte: Fonte) -> int:
    inicio = agora()
    d = await fonte.descobrir()
    repositorio.registrar_descoberta(fonte.con, fonte.id, d, inicio)
    return len(d.itens)


def espaco_livre_mb() -> float:
    """O espaço livre no disco da pasta de dados, em MB."""
    pasta = config.dados()
    while not pasta.exists() and pasta.parent != pasta:
        pasta = pasta.parent
    return shutil.disk_usage(pasta).free / 2**20


async def coletar(fonte: Fonte, *, refazer: bool = False, parar_apos: int | None = None) -> Placar:
    con = fonte.con
    placar = Placar(fonte.id)
    inicio = agora()
    itens, placar.pulados = repositorio.itens_a_coletar(con, fonte.id, refazer=refazer)
    if placar.pulados:
        eco(f"  {fonte.id}: {placar.pulados} itens já coletados, retomando os {len(itens)} que faltam")

    for feitos, item in enumerate(itens):
        if parar_apos is not None and feitos >= parar_apos:
            raise Interrompido(f"interrompido depois de {feitos} itens")
        livre = espaco_livre_mb()
        if livre < config.DISCO_MINIMO_MB:
            # o item (e os que faltam) ficam pendentes: a próxima rodada retoma daqui
            placar.parou = f"disco quase cheio: {livre:.0f} MB livres (mínimo {config.DISCO_MINIMO_MB:.0f} MB)"
            eco(f"  {fonte.id}: PAROU antes de {item.chave} — {placar.parou}; {len(itens) - feitos} item(ns) ficam pendentes")
            break
        ultimo_erro: Exception | None = None
        for tentativa in range(1, config.TENTATIVAS + 1):
            await fonte.antes_do_item(item)
            try:
                r = await fonte.coletar_item(item)
            except FalhaTransitoria as e:
                ultimo_erro = e
                if tentativa < config.TENTATIVAS:
                    # descarta o rastro desta tentativa; o da última fica como evidência
                    await fonte.evidencia(config.evidencias(), sucesso=True)
                    espera = config.ESPERA_BASE * (2 ** (tentativa - 1)) * (0.75 + random.random() / 2)
                    placar.tentativas_extras += 1
                    eco(f"  {fonte.id} {item.chave}: {e} — nova tentativa em {espera:.1f}s")
                    await asyncio.sleep(espera)
                    continue
                break
            except PARA_A_FONTE as e:
                pasta = await _registrar_erro(fonte, item.chave, e)
                placar.erro += 1
                placar.parou = f"{type(e).__name__}: {e}"
                eco(f"  {fonte.id}: PAROU em {item.chave} — {type(e).__name__}: {e} (evidência em {caminho_relativo(pasta)})")
                _fechar_coleta(con, fonte.id, inicio, placar)
                return placar
            except Interrompido:
                raise
            except Exception as e:  # erro de programa: evidência e segue para o próximo
                ultimo_erro = e
                break
            else:
                await fonte.evidencia(config.evidencias(), sucesso=True)
                repositorio.gravar_item_coletado(con, fonte.id, item.chave, r, fonte.sistema.casa, tentativa)
                placar.ok += 1
                ultimo_erro = None
                n = (len(r.despesas) + len(r.pendencias)) or len(r.atividades) or len(r.pessoas) or len(r.candidaturas) or len(r.gabinetes) or len(r.remuneracoes)
                eco(f"  {fonte.id} {item.chave}: ok ({n} registros{', ' + str(tentativa) + ' tentativas' if tentativa > 1 else ''})")
                break
        if ultimo_erro is not None:
            await _registrar_erro(fonte, item.chave, ultimo_erro)
            placar.erro += 1
            eco(f"  {fonte.id} {item.chave}: ERRO — {type(ultimo_erro).__name__}: {str(ultimo_erro)[:200]}")
    _fechar_coleta(con, fonte.id, inicio, placar)
    return placar


async def _registrar_erro(fonte: Fonte, chave: str, e: Exception) -> Path:
    """A evidência do ponto do erro (o que a fonte guardar, mais o traceback) e o item marcado com erro."""
    pasta = pasta_evidencia(fonte.id, chave)
    await fonte.evidencia(pasta, sucesso=False)
    (pasta / "erro.txt").write_text("".join(traceback.format_exception(e)), encoding="utf-8")
    repositorio.marcar_erro(fonte.con, fonte.id, chave, e, caminho_relativo(pasta))
    return pasta


def _fechar_coleta(con, fonte_id: str, inicio: str, placar: Placar) -> None:
    situacao = "parou" if placar.parou else ("erro" if placar.erro else "ok")
    totais = {"ok": placar.ok, "erro": placar.erro, "ja_coletados": placar.pulados, "tentativas_extras": placar.tentativas_extras}
    repositorio.registrar_coleta(con, fonte_id, inicio, situacao, totais, placar.parou)
