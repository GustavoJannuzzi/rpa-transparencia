"""Executa descobrir e coletar de uma fonte: inventário, retomada, repetição com
espera, evidência no erro e alarme de portal mudou. Não sabe de fonte nenhuma."""

from __future__ import annotations

import asyncio
import random
import shutil
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime

from .. import config
from ..fontes.base import Fonte
from ..modelo import Resultado, TotalOficial
from .banco import agora, js, transacao
from .erros import AcessoRecusado, BloqueadoPorRobots, FalhaTransitoria, PortalMudou
from .evidencia import caminho_relativo, pasta_evidencia


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


def gravar_totais(con, totais: list[TotalOficial]) -> None:
    for t in totais:
        con.execute(
            """INSERT INTO totais_oficiais(fonte, escopo, metrica, valor, texto_original, url, hash_original, coletado_em)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(fonte, escopo, metrica) DO UPDATE SET valor=excluded.valor,
                 texto_original=excluded.texto_original, url=excluded.url,
                 hash_original=excluded.hash_original, coletado_em=excluded.coletado_em""",
            (t.fonte, t.escopo, t.metrica, t.valor, t.texto_original, t.procedencia.url,
             t.procedencia.hash_original, t.procedencia.coletado_em),
        )


async def descobrir(fonte: Fonte) -> int:
    con = fonte.con
    inicio = agora()
    d = await fonte.descobrir()
    with transacao(con):
        for it in d.itens:
            atual = con.execute("SELECT parametros FROM inventario WHERE fonte=? AND chave=?", (fonte.id, it.chave)).fetchone()
            if atual is None:
                con.execute(
                    "INSERT INTO inventario(fonte, chave, descricao, periodo, parametros, situacao, atualizado_em) VALUES(?,?,?,?,?,'pendente',?)",
                    (fonte.id, it.chave, it.descricao, it.periodo, js(it.parametros), agora()),
                )
            elif atual["parametros"] != js(it.parametros):
                # o item mudou na origem (ex.: mais páginas): volta a pendente
                con.execute(
                    "UPDATE inventario SET descricao=?, periodo=?, parametros=?, situacao='pendente', atualizado_em=? WHERE fonte=? AND chave=?",
                    (it.descricao, it.periodo, js(it.parametros), agora(), fonte.id, it.chave),
                )
        gravar_totais(con, d.totais)
        con.execute(
            "INSERT INTO coletas(fonte, etapa, inicio, fim, situacao, totais, versao) VALUES(?,?,?,?,?,?,?)",
            (fonte.id, "descobrir", inicio, agora(), "ok", js({"itens": len(d.itens), "totais": len(d.totais)}), config.VERSAO_ROBO),
        )
    return len(d.itens)


def _gravar_resultado(con, fonte_id: str, chave_item: str, r: Resultado, casa: str | None = None) -> None:
    # Refazer um item apaga o que ele tinha gravado antes: rodar duas vezes não duplica.
    con.execute("DELETE FROM despesas WHERE fonte=? AND item=?", (fonte_id, chave_item))
    con.execute("DELETE FROM pendencias WHERE fonte=? AND item=?", (fonte_id, chave_item))
    for pe in r.pendencias:
        p = pe.procedencia
        con.execute(
            "INSERT OR REPLACE INTO pendencias(chave, fonte, item, motivo, texto_original, url, hash_original, localizador, coletado_em) VALUES(?,?,?,?,?,?,?,?,?)",
            (pe.chave, pe.fonte, chave_item, pe.motivo, pe.texto_original, p.url, p.hash_original, p.localizador, p.coletado_em),
        )
    linhas = []
    for d in r.despesas:
        p = d.procedencia
        linhas.append((d.chave, d.fonte, chave_item, d.tipo, d.ref_parlamentar, d.beneficiario_tipo, d.nome_beneficiario,
                       d.cargo_original, d.data.isoformat() if d.data else None, d.competencia, d.ano, d.categoria_original,
                       d.fornecedor_doc, d.fornecedor_tipo, d.fornecedor_nome, str(d.valor), d.documento_url, d.descricao,
                       p.url, p.hash_original, p.localizador, p.coletado_em, js(d.extra), d.casa or casa, d.granularidade))
    con.executemany(
        """INSERT INTO despesas(chave, fonte, item, tipo, ref_parlamentar, beneficiario_tipo, nome_beneficiario,
             cargo_original, data, competencia, ano, categoria, categoria_original, fornecedor_doc, fornecedor_tipo,
             fornecedor_nome, valor, documento_url, descricao, url, hash_original, localizador, coletado_em, extra,
             casa, granularidade)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(chave) DO UPDATE SET item=excluded.item, valor=excluded.valor,
             url=excluded.url, hash_original=excluded.hash_original, coletado_em=excluded.coletado_em,
             localizador=excluded.localizador, extra=excluded.extra, casa=excluded.casa,
             granularidade=excluded.granularidade""",
        linhas,
    )
    for m in r.remuneracoes:
        p = m.procedencia
        con.execute(
            """INSERT OR REPLACE INTO remuneracoes(fonte, casa, ref_parlamentar, competencia, data_referencia, valor, rotulo,
                 cargo_original, url, hash_original, localizador, coletado_em) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (m.fonte, m.casa, m.ref_parlamentar, m.competencia, m.data_referencia, str(m.valor), m.rotulo, m.cargo_original,
             p.url, p.hash_original, p.localizador, p.coletado_em),
        )
    for pf in r.pessoas:
        p = pf.procedencia
        con.execute(
            """INSERT OR REPLACE INTO pessoas_fonte(fonte, ref, periodo, nome, nome_parlamentar, matricula, partido, uf, casa,
                 extra, url, hash_original, coletado_em) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pf.fonte, pf.ref, pf.periodo, pf.nome, pf.nome_parlamentar, pf.matricula, pf.partido, pf.uf, pf.casa,
             js(pf.extra), p.url, p.hash_original, p.coletado_em),
        )
    for c in r.candidaturas:
        p = c.procedencia
        con.execute(
            """INSERT OR REPLACE INTO candidaturas(ano_eleicao, municipio, cargo, sq_candidato, nome, nome_norm, nome_urna,
                 partido, situacao, url, hash_original, coletado_em) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (c.ano_eleicao, c.municipio, c.cargo, c.sq_candidato, c.nome, c.nome_norm, c.nome_urna, c.partido,
             c.situacao, p.url, p.hash_original, p.coletado_em),
        )
    for g in r.gabinetes:
        p = g.procedencia
        con.execute(
            """INSERT OR REPLACE INTO gabinetes(fonte, lotacao_original, competencia, ref_parlamentar, data_referencia,
                 pessoas, custo, url, hash_original, coletado_em) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (g.fonte, g.lotacao_original, g.competencia, g.ref_parlamentar, g.data_referencia, g.pessoas, str(g.custo),
             p.url, p.hash_original, p.coletado_em),
        )
    gravar_totais(con, r.totais)


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
    filtro = "" if refazer else "AND situacao IN ('pendente','erro')"
    itens = con.execute(
        f"SELECT chave, descricao, periodo, parametros, tentativas FROM inventario WHERE fonte=? {filtro} ORDER BY chave",
        (fonte.id,),
    ).fetchall()
    total_inv = con.execute("SELECT COUNT(*) FROM inventario WHERE fonte=?", (fonte.id,)).fetchone()[0]
    placar.pulados = total_inv - len(itens)
    if placar.pulados:
        eco(f"  {fonte.id}: {placar.pulados} itens já coletados, retomando os {len(itens)} que faltam")

    import json

    from ..modelo import ItemInventario

    feitos = 0
    for linha in itens:
        item = ItemInventario(chave=linha["chave"], descricao=linha["descricao"], periodo=linha["periodo"],
                              parametros=json.loads(linha["parametros"] or "{}"))
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
            except (PortalMudou, AcessoRecusado, BloqueadoPorRobots) as e:
                ultimo_erro = e
                pasta = pasta_evidencia(fonte.id, item.chave)
                arquivos = await fonte.evidencia(pasta, sucesso=False)
                _marcar_erro(con, fonte.id, item.chave, e, pasta, arquivos)
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
                with transacao(con):
                    _gravar_resultado(con, fonte.id, item.chave, r, fonte.sistema.casa)
                    con.execute(
                        "UPDATE inventario SET situacao='ok', tentativas=tentativas+?, ultimo_erro=NULL, evidencia=NULL, atualizado_em=? WHERE fonte=? AND chave=?",
                        (tentativa, agora(), fonte.id, item.chave),
                    )
                placar.ok += 1
                ultimo_erro = None
                n = (len(r.despesas) + len(r.pendencias)) or len(r.pessoas) or len(r.candidaturas) or len(r.gabinetes) or len(r.remuneracoes)
                eco(f"  {fonte.id} {item.chave}: ok ({n} registros{', ' + str(tentativa) + ' tentativas' if tentativa > 1 else ''})")
                break
        if ultimo_erro is not None:
            pasta = pasta_evidencia(fonte.id, item.chave)
            arquivos = await fonte.evidencia(pasta, sucesso=False)
            _marcar_erro(con, fonte.id, item.chave, ultimo_erro, pasta, arquivos)
            placar.erro += 1
            eco(f"  {fonte.id} {item.chave}: ERRO — {type(ultimo_erro).__name__}: {str(ultimo_erro)[:200]}")
        feitos += 1
    _fechar_coleta(con, fonte.id, inicio, placar)
    return placar


def _marcar_erro(con, fonte_id: str, chave: str, e: Exception, pasta, arquivos: list[str]) -> None:
    (pasta / "erro.txt").write_text("".join(traceback.format_exception(e)), encoding="utf-8")
    con.execute(
        "UPDATE inventario SET situacao='erro', tentativas=tentativas+1, ultimo_erro=?, evidencia=?, atualizado_em=? WHERE fonte=? AND chave=?",
        (f"{type(e).__name__}: {str(e)[:500]}", caminho_relativo(pasta), agora(), fonte_id, chave),
    )


def _fechar_coleta(con, fonte_id: str, inicio: str, placar: Placar) -> None:
    situacao = "parou" if placar.parou else ("erro" if placar.erro else "ok")
    con.execute(
        "INSERT INTO coletas(fonte, etapa, inicio, fim, situacao, totais, versao, mensagem) VALUES(?,?,?,?,?,?,?,?)",
        (fonte_id, "coletar", inicio, agora(), situacao,
         js({"ok": placar.ok, "erro": placar.erro, "ja_coletados": placar.pulados, "tentativas_extras": placar.tentativas_extras}),
         config.VERSAO_ROBO, placar.parou),
    )
