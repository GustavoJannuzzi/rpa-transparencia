"""Gravação no SQLite do que a coleta produz: o inventário de cada fonte, os totais
que a fonte diz de si e o resultado de cada item.

O executor (`execucao.py`) decide o que fazer com cada item (repetir, parar, guardar
evidência); este módulo só sabe ler e gravar o estado. Cada escrita que precisa ser
atômica abre a sua transação aqui: o item gravado e o inventário marcado "ok" entram
juntos, ou nenhum dos dois, e é isso que deixa a retomada parar e voltar em qualquer
ponto sem duplicar linha.
"""

from __future__ import annotations

import json
import sqlite3

from .. import config
from ..modelo import Descoberta, ItemInventario, Resultado, TotalOficial
from .banco import agora, js, transacao


def gravar_totais(con: sqlite3.Connection, totais: list[TotalOficial]) -> None:
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


# ---------------------------------------------------------------- inventário
def registrar_descoberta(con: sqlite3.Connection, fonte_id: str, d: Descoberta, inicio: str) -> None:
    """O inventário que a fonte descobriu, numa transação: item novo entra pendente,
    item que mudou na origem (mais páginas, outro período) volta a pendente, e o que
    não mudou fica como estava (a retomada não refaz o que já está ok)."""
    with transacao(con):
        for it in d.itens:
            atual = con.execute("SELECT parametros FROM inventario WHERE fonte=? AND chave=?", (fonte_id, it.chave)).fetchone()
            if atual is None:
                con.execute(
                    "INSERT INTO inventario(fonte, chave, descricao, periodo, parametros, situacao, atualizado_em) VALUES(?,?,?,?,?,'pendente',?)",
                    (fonte_id, it.chave, it.descricao, it.periodo, js(it.parametros), agora()),
                )
            elif atual["parametros"] != js(it.parametros):
                con.execute(
                    "UPDATE inventario SET descricao=?, periodo=?, parametros=?, situacao='pendente', atualizado_em=? WHERE fonte=? AND chave=?",
                    (it.descricao, it.periodo, js(it.parametros), agora(), fonte_id, it.chave),
                )
        gravar_totais(con, d.totais)
        con.execute(
            "INSERT INTO coletas(fonte, etapa, inicio, fim, situacao, totais, versao) VALUES(?,?,?,?,?,?,?)",
            (fonte_id, "descobrir", inicio, agora(), "ok", js({"itens": len(d.itens), "totais": len(d.totais)}), config.VERSAO_ROBO),
        )


def itens_a_coletar(con: sqlite3.Connection, fonte_id: str, *, refazer: bool) -> tuple[list[ItemInventario], int]:
    """Os itens que esta rodada coleta (os pendentes e os com erro, ou todos com
    `refazer`), em ordem de chave, e quantos do inventário ficam de fora por já estarem ok."""
    filtro = "" if refazer else "AND situacao IN ('pendente','erro')"
    linhas = con.execute(
        f"SELECT chave, descricao, periodo, parametros FROM inventario WHERE fonte=? {filtro} ORDER BY chave",
        (fonte_id,),
    ).fetchall()
    total = con.execute("SELECT COUNT(*) FROM inventario WHERE fonte=?", (fonte_id,)).fetchone()[0]
    itens = [ItemInventario(chave=l["chave"], descricao=l["descricao"], periodo=l["periodo"], parametros=json.loads(l["parametros"] or "{}"))
             for l in linhas]
    return itens, total - len(itens)


def gravar_item_coletado(con: sqlite3.Connection, fonte_id: str, chave_item: str, r: Resultado, casa: str | None, tentativas: int) -> None:
    """O resultado do item e o inventário marcado "ok", na mesma transação."""
    with transacao(con):
        gravar_resultado(con, fonte_id, chave_item, r, casa)
        con.execute(
            "UPDATE inventario SET situacao='ok', tentativas=tentativas+?, ultimo_erro=NULL, evidencia=NULL, atualizado_em=? WHERE fonte=? AND chave=?",
            (tentativas, agora(), fonte_id, chave_item),
        )


def marcar_erro(con: sqlite3.Connection, fonte_id: str, chave: str, erro: Exception, evidencia: str) -> None:
    """O item fica com erro, a mensagem e onde está a evidência: a próxima rodada tenta de novo."""
    con.execute(
        "UPDATE inventario SET situacao='erro', tentativas=tentativas+1, ultimo_erro=?, evidencia=?, atualizado_em=? WHERE fonte=? AND chave=?",
        (f"{type(erro).__name__}: {str(erro)[:500]}", evidencia, agora(), fonte_id, chave),
    )


def registrar_coleta(con: sqlite3.Connection, fonte_id: str, inicio: str, situacao: str, totais: dict, mensagem: str | None) -> None:
    """Uma linha em `coletas` por rodada de `coletar` de cada fonte: o histórico das rodadas."""
    con.execute(
        "INSERT INTO coletas(fonte, etapa, inicio, fim, situacao, totais, versao, mensagem) VALUES(?,?,?,?,?,?,?,?)",
        (fonte_id, "coletar", inicio, agora(), situacao, js(totais), config.VERSAO_ROBO, mensagem),
    )


# ---------------------------------------------------------------- resultado de um item
def gravar_resultado(con: sqlite3.Connection, fonte_id: str, chave_item: str, r: Resultado, casa: str | None = None) -> None:
    """Grava tudo que um item produziu no modelo único. Chamar dentro de uma transação.

    Refazer um item apaga o que ele tinha gravado antes (despesas, pendências e
    atividades daquele item): rodar duas vezes não duplica."""
    con.execute("DELETE FROM despesas WHERE fonte=? AND item=?", (fonte_id, chave_item))
    con.execute("DELETE FROM pendencias WHERE fonte=? AND item=?", (fonte_id, chave_item))
    con.execute("DELETE FROM atividades WHERE fonte=? AND item=?", (fonte_id, chave_item))
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
    con.executemany(
        """INSERT INTO atividades(chave, fonte, item, casa, tipo, ref_parlamentar, ref_sessao, data, competencia, rotulo,
             quantidade, url, hash_original, localizador, coletado_em, extra) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(chave) DO UPDATE SET item=excluded.item, rotulo=excluded.rotulo, quantidade=excluded.quantidade,
             url=excluded.url, hash_original=excluded.hash_original, localizador=excluded.localizador,
             coletado_em=excluded.coletado_em, extra=excluded.extra""",
        [(a.chave, a.fonte, chave_item, a.casa, a.tipo, a.ref_parlamentar, a.ref_sessao, a.data.isoformat() if a.data else None,
          a.competencia, a.rotulo, a.quantidade, a.procedencia.url, a.procedencia.hash_original, a.procedencia.localizador,
          a.procedencia.coletado_em, js(a.extra)) for a in r.atividades],
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
