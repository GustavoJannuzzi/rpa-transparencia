"""Atividade legislativa na plataforma: o que cada vereador registrou (presença,
ausência com o motivo que a fonte der, voto nominal por tipo) e o que cada casa
registrou na janela de coleta.

Só contagem bruta, com a procedência anotada. Nada de taxa, ranking nem ordem por
quem falta mais: a casa lista os vereadores em ordem alfabética, e a página diz
quem entrou ou saiu no meio da janela tem menos sessões, porque é assim.

Só vai para o ar o que se ligou a um vereador identificado pelas fontes de
despesa. O resto fica contado em "em revisão", com o motivo.

Coleta parcial (páginas ainda por pedir): publica só o trecho contínuo que fechou,
e diz até que data. Presença: as sessões até a última data em que todas as
sessões anteriores já têm a presença coletada. Voto: as páginas vêm em ordem de
registro; vale o prefixo contínuo de páginas coletadas, até a véspera da sessão do
último voto dele (a sessão do último voto pode ter votos na página seguinte).
"""

from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from .. import entidades
from ..fontes import FONTES
from ..nucleo.texto import normalizar_nome

PASTA = Path(__file__).resolve().parents[1] / "cobertura"
FREQ = "cmc_frequencia"
ROTULO_FREQ = {
    "presenca_ou_falta_justificada": "presença ou falta justificada",
    "falta_descontada": "falta descontada",
    "licenca": "licença",
}


def _fontes() -> dict[str, object]:
    return {f.id: f for f in FONTES if f.dado == "atividade"}


def _valor(con, fonte: str, escopo: str, metrica: str) -> str | None:
    r = con.execute("SELECT valor FROM totais_oficiais WHERE fonte=? AND escopo=? AND metrica=?", (fonte, escopo, metrica)).fetchone()
    return r[0] if r else None


def _faltam(con, fonte: str, prefixo: str = "") -> int:
    return con.execute("SELECT COUNT(*) FROM inventario WHERE fonte=? AND chave LIKE ? AND situacao!='ok'",
                       (fonte, f"{prefixo}%")).fetchone()[0]


def _cortes_sapl(con, fonte: str) -> dict:
    """Até onde a coleta de uma câmara fechou: as datas de corte efetivas de presença e voto."""
    corte = _valor(con, fonte, "janela", "corte")
    datas = {r[0]: r[1] for r in con.execute("SELECT ref_sessao, data FROM atividades WHERE fonte=? AND tipo='sessao'", (fonte,))}
    out: dict = {"de": _valor(con, fonte, "janela", "de"), "corte": corte, "presenca": corte, "votos": corte}
    # presença: sessões cobertas pelos lotes que fecharam
    cobertas: set[str] = set()
    faltando: list[str] = []
    for r in con.execute("SELECT situacao, parametros FROM inventario WHERE fonte=? AND chave LIKE '2-presenca-%'", (fonte,)):
        ids = list(json.loads(r[1])["sessoes"])
        (cobertas.update(ids) if r[0] == "ok" else faltando.extend(ids))
    if faltando:
        primeira_falta = min(datas.get(s, corte or "9999") for s in faltando)
        anteriores = [d for s, d in datas.items() if d < primeira_falta]
        out["presenca"] = max(anteriores) if anteriores else None
    # voto: prefixo contínuo de páginas coletadas
    paginas = [(r[0], r[1]) for r in con.execute(
        "SELECT chave, situacao FROM inventario WHERE fonte=? AND chave LIKE '4-votos-%' ORDER BY chave", (fonte,))]
    if any(s != "ok" for _, s in paginas):
        prefixo = []
        for chave, s in paginas:
            if s != "ok":
                break
            prefixo.append(chave)
        out["votos_paginas"] = prefixo
        if prefixo:
            ult = con.execute("SELECT MAX(data) FROM atividades WHERE fonte=? AND tipo='voto' AND item=?", (fonte, prefixo[-1])).fetchone()[0]
            if ult:
                antes = [d for d in datas.values() if d < ult]
                out["votos"] = max(antes) if antes else None
            else:
                out["votos"] = None
        else:
            out["votos"] = None
    out["parcial"] = bool(_faltam(con, fonte))
    return out


def _filtro_sapl(cortes: dict):
    """Diz se um registro do SAPL entra na publicação, pelos cortes efetivos."""
    paginas = set(cortes["votos_paginas"]) if "votos_paginas" in cortes else None

    def entra(tipo: str, data_reg: str | None, item: str) -> bool:
        if tipo == "presenca":
            return cortes["presenca"] is not None and (data_reg or "") <= cortes["presenca"]
        if tipo == "voto":
            if cortes["votos"] is None:
                return False
            return (paginas is None or item in paginas) and (data_reg or "") <= cortes["votos"]
        return True

    return entra


def resumos(con: sqlite3.Connection) -> tuple[dict[str, list[dict]], dict[str, list[dict]], dict]:
    """(atividade por parlamentar, atividade por casa, atividade na Cobertura)."""
    fontes = _fontes()
    ids = {(r[0], r[1]): r[2] for r in con.execute("SELECT fonte, ref, parlamentar_id FROM parlamentar_ids")}
    nomes = {r[0]: r[1] for r in con.execute("SELECT id, nome FROM parlamentares")}
    por_parl: dict[str, list[dict]] = defaultdict(list)
    por_casa: dict[str, list[dict]] = defaultdict(list)
    cobertura: list[dict] = []
    for fid, f in fontes.items():
        if not con.execute("SELECT 1 FROM inventario WHERE fonte=? LIMIT 1", (fid,)).fetchone():
            continue
        casa = f.sistema.casa  # type: ignore[attr-defined]
        conf = con.execute("""SELECT esperado, obtido, resultado, detalhe FROM conferencias
                              WHERE fonte=? AND verificacao='origem_igual_coletado_mais_revisao'""", (fid,)).fetchone()
        rev = [{"motivo": r[0], "n": r[1], "registros": r[2]} for r in con.execute(
            """SELECT motivo, COUNT(*), SUM(COALESCE(json_extract(detalhe, '$.registros'), 1)) FROM revisao
               WHERE fonte=? GROUP BY 1 ORDER BY 3 DESC""", (fid,))]
        coleta = (con.execute("SELECT MAX(coletado_em) FROM atividades WHERE fonte=?", (fid,)).fetchone()[0] or "")[:10]
        base = {"fonte": fid, "sistema": f.sistema.sistema, "fornecedor": f.sistema.fornecedor, "modo": f.sistema.modo,  # type: ignore[attr-defined]
                "endereco": f.sistema.endereco, "coleta": coleta,  # type: ignore[attr-defined]
                "conferencia": dict(conf) if conf else None, "em_revisao": rev}
        if fid == FREQ:
            casa_r, parl_r = _frequencia(con, fid, ids, nomes, base)
        else:
            casa_r, parl_r = _sapl(con, fid, f, ids, nomes, base)
        por_casa[casa].append(casa_r)
        for pid, r in parl_r.items():
            por_parl[pid].append(r)
        cobertura.append({"casa": casa, "fonte": fid, "sistema": f.sistema.sistema, "de": casa_r["de"],  # type: ignore[attr-defined]
                          "ate": casa_r["ate"], "situacao": casa_r["situacao"],
                          **({k: casa_r[k] for k in ("presenca_ate", "votos_ate")} if "presenca_ate" in casa_r else {})})
    return dict(por_parl), dict(por_casa), {"coletadas": cobertura, **_fora()}


def _sapl(con, fid: str, f, ids: dict, nomes: dict, base: dict) -> tuple[dict, dict[str, dict]]:
    cortes = _cortes_sapl(con, fid)
    entra = _filtro_sapl(cortes)
    host = f.ent.host
    tipos_sessao: Counter[str] = Counter()
    n_sessoes = 0
    pres: Counter[str] = Counter()
    aus: dict[str, Counter] = defaultdict(Counter)
    votos: dict[str, Counter] = defaultdict(Counter)
    casa_aus: Counter[str] = Counter()
    casa_votos: Counter[str] = Counter()
    sessoes_presenca = 0
    com_presenca: set[str] = set()  # sessões em que o sistema tem alguém presente (ligado ou não)
    id_sapl: dict[str, str] = {}
    coleta_pid: dict[str, str] = {}
    for r in con.execute("SELECT tipo, ref_parlamentar, ref_sessao, data, rotulo, item, coletado_em, extra FROM atividades WHERE fonte=?", (fid,)):
        tipo = r["tipo"]
        if tipo == "sessao":
            n_sessoes += 1
            tipos_sessao[r["rotulo"] or "sem tipo"] += 1
            if cortes["presenca"] is not None and r["data"] <= cortes["presenca"]:
                sessoes_presenca += 1
            continue
        if not entra(tipo, r["data"], r["item"]):
            continue
        if tipo == "presenca":
            com_presenca.add(r["ref_sessao"])
        pid = ids.get((fid, r["ref_parlamentar"]))
        if pid is None:
            continue  # em revisão (identidade), contado na equação
        id_sapl[pid] = r["ref_parlamentar"].removeprefix("sapl:")
        coleta_pid[pid] = max(coleta_pid.get(pid, ""), (r["coletado_em"] or "")[:10])
        if tipo == "presenca":
            pres[pid] += 1
        elif tipo == "ausencia":
            extra = json.loads(r["extra"] or "{}")
            rot = r["rotulo"] + (" (em matéria)" if extra.get("ausencia") == "Matéria" else "")
            aus[pid][rot] += 1
            casa_aus[rot] += 1
        elif tipo == "voto":
            votos[pid][r["rotulo"]] += 1
            casa_votos[r["rotulo"]] += 1
    situacao = "parcial" if cortes["parcial"] else "completa"
    # o que ainda não foi lido não vira zero: a tela diz "ainda não lido"
    janela = {"de": cortes["de"], "ate": cortes["corte"], "situacao": situacao,
              "presenca_ate": cortes["presenca"], "votos_ate": cortes["votos"],
              "ausencias_lidas": not _faltam(con, fid, "3-ausencias")}
    pids = sorted(set(pres) | set(aus) | set(votos), key=lambda p: (normalizar_nome(nomes.get(p, p)), p))
    por_parl: dict[str, dict] = {}
    for pid in pids:
        por_parl[pid] = {
            **{k: base[k] for k in ("fonte", "sistema", "fornecedor", "modo")}, **janela,
            "sessoes_da_casa": sessoes_presenca, "sessoes_com_presenca_registrada": len(com_presenca), "presencas": pres.get(pid, 0),
            "ausencias": [{"rotulo": k, "n": v} for k, v in sorted(aus.get(pid, Counter()).items(), key=lambda x: (-x[1], x[0]))],
            "votos": [{"rotulo": k, "n": v} for k, v in sorted(votos.get(pid, Counter()).items(), key=lambda x: (-x[1], x[0]))],
            "coleta": coleta_pid.get(pid, base["coleta"]),
            "documento": f"{host}/parlamentar/{id_sapl[pid]}",
            "id_na_fonte": id_sapl[pid],
        }
    casa_r = {
        **base, **janela,
        "sessoes": n_sessoes, "sessoes_por_tipo": [{"rotulo": k, "n": v} for k, v in tipos_sessao.most_common()],
        "sessoes_com_presenca_coletada": sessoes_presenca,
        "sessoes_com_presenca_registrada": len(com_presenca),
        "presencas": sum(pres.values()),
        "ausencias": [{"rotulo": k, "n": v} for k, v in casa_aus.most_common()],
        "votos": [{"rotulo": k, "n": v} for k, v in casa_votos.most_common()],
        "vereadores": [{"id": p, "nome": nomes.get(p, p), "presencas": pres.get(p, 0), "ausencias": sum(aus.get(p, Counter()).values()),
                        "votos": sum(votos.get(p, Counter()).values())} for p in pids],
        "pedidos": con.execute("SELECT COUNT(*) FROM inventario WHERE fonte=? AND chave NOT LIKE '1-%'", (fid,)).fetchone()[0],
        "pedidos_feitos": con.execute("SELECT COUNT(*) FROM inventario WHERE fonte=? AND chave NOT LIKE '1-%' AND situacao='ok'",
                                      (fid,)).fetchone()[0],
        "crawl_delay": 60,
    }
    return casa_r, por_parl


def _frequencia(con, fid: str, ids: dict, nomes: dict, base: dict) -> tuple[dict, dict[str, dict]]:
    sessoes = {r[0]: int(r[1]) for r in con.execute(
        "SELECT i.periodo, t.valor FROM totais_oficiais t JOIN inventario i ON i.fonte=t.fonte AND i.chave=t.escopo "
        "WHERE t.fonte=? AND t.metrica='sessoes'", (fid,))}
    meses: dict[str, dict[str, dict]] = defaultdict(dict)
    vereadores_periodo: Counter[str] = Counter()
    for r in con.execute("""SELECT competencia, ref_parlamentar, rotulo, quantidade, coletado_em, localizador, extra
                            FROM atividades WHERE fonte=? ORDER BY competencia""", (fid,)):
        pid = ids.get((fid, r["ref_parlamentar"]))
        if pid is None:
            continue
        extra = json.loads(r["extra"] or "{}")
        m = meses[pid].setdefault(r["competencia"], {"periodo": r["competencia"], "sessoes": sessoes.get(r["competencia"]),
                                                     "k": (r["coletado_em"] or "")[:10], "loc": r["localizador"],
                                                     "nome_na_fonte": extra.get("nome_na_fonte")})
        if extra.get("nota"):
            m["nota"] = extra["nota"]
        if r["rotulo"] == "presidiu":
            m["presidiu"] = True
        else:
            m[r["rotulo"]] = r["quantidade"]
    anos_da_casa = {int(p[:4]) for ms in meses.values() for p in ms}
    por_parl: dict[str, dict] = {}
    for pid, ms in meses.items():
        lista = sorted(ms.values(), key=lambda x: x["periodo"], reverse=True)
        anos_dele = {int(p[:4]) for p in ms}
        # ano dentro do período dele em que a Câmara publicou relatório e o nome não aparece (suplência, licença longa)
        sem_relatorio = [a for a in range(min(anos_dele), max(anos_dele) + 1) if a in anos_da_casa and a not in anos_dele]
        anos: dict[int, dict] = {}
        for m in lista:
            a = anos.setdefault(int(m["periodo"][:4]), {"ano": int(m["periodo"][:4]), "relatorios": 0, "presidiu": 0,
                                                       **{k: 0 for k in ROTULO_FREQ}, "anual": len(m["periodo"]) == 4})
            a["relatorios"] += 1
            a["presidiu"] += 1 if m.get("presidiu") else 0
            for k in ROTULO_FREQ:
                a[k] += m.get(k, 0)
        for m in lista:
            vereadores_periodo[m["periodo"]] += 1
        por_parl[pid] = {**{k: base[k] for k in ("fonte", "sistema", "fornecedor", "modo")},
                         "de": lista[-1]["periodo"], "ate": lista[0]["periodo"], "situacao": "completa" if not _faltam(con, fid) else "parcial",
                         "por_ano": sorted(anos.values(), key=lambda x: -x["ano"]), "periodos": lista, "anos_sem_o_nome": sem_relatorio,
                         "documento": base["endereco"], "coleta": max(m["k"] for m in lista)}
    periodos = sorted({p for ms in meses.values() for p in ms} | set(sessoes))
    por_ano: dict[int, dict] = {}
    for p in periodos:
        a = por_ano.setdefault(int(p[:4]), {"ano": int(p[:4]), "relatorios": 0, "sessoes": 0, "sessoes_sem_nota": 0, "anual": len(p) == 4})
        a["relatorios"] += 1
        if p in sessoes:
            a["sessoes"] += sessoes[p]
        else:
            a["sessoes_sem_nota"] += 1
    casa_r = {**base, "de": periodos[0] if periodos else None, "ate": periodos[-1] if periodos else None,
              "situacao": "completa" if not _faltam(con, fid) else "parcial",
              "relatorios": len(periodos), "consolidados_nao_somados": con.execute(
                  "SELECT COUNT(*) FROM totais_oficiais WHERE fonte=? AND metrica='consolidado_nao_somado'", (fid,)).fetchone()[0],
              "por_ano": sorted(por_ano.values(), key=lambda x: -x["ano"]),
              "vereadores": sorted(({"id": p, "nome": nomes.get(p, p), "relatorios": len(ms)} for p, ms in meses.items()),
                                   key=lambda x: (normalizar_nome(x["nome"]), x["id"]))}
    return casa_r, por_parl


def _fora() -> dict:
    """Câmaras de fora da atividade, com o motivo (do levantamento, com data)."""
    arq = PASTA / "atividade-pr.csv"
    if not arq.exists():
        return {"fora": []}
    with arq.open(encoding="utf-8", newline="") as f:
        linhas = list(csv.DictReader(l for l in f if not l.startswith("#")))
    casas = entidades.casas()
    fora = []
    for l in linhas:
        c = casas.get(l["casa"]) if l.get("casa") else None
        fora.append({"casa": l.get("casa") or None, "municipio": l["municipio"], "ibge": int(l["ibge"]) if l.get("ibge") else None,
                     "sistema": l.get("sistema") or None, "motivo": l["motivo"], "base": l.get("base") or None,
                     "no_site": c is not None})
    return {"fora": fora}


