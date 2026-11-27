"""Casas e cobertura: o que a coleta cobre, casa a casa, e onde estão as casas que
ficaram de fora, com o motivo.

Os números de casa coletada vêm da coleta (medidos). Os números do levantamento das
fontes (quantas câmaras usam cada fornecedor, quantas o robots.txt barra) vêm dos
arquivos em `coleta/cobertura/`, com a data do levantamento, e a plataforma os
mostra como levantamento, nunca como coleta.
"""

from __future__ import annotations

import csv
import json
import math
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

from .. import entidades
from ..fontes import FONTES
from ..nucleo.texto import normalizar_nome

PASTA = Path(__file__).resolve().parents[1] / "cobertura"
DATA_LEVANTAMENTO = "2026-11-26"

# O que o levantamento contou (relatório de fontes dos municípios do PR, seções 1, 2 e 6).
# São contagens do levantamento, não da coleta, e vão para a tela com a data.
LEVANTAMENTO_CAMARAS = {
    "total": 399,
    "com_fornecedor_dos_quatro_adaptadores": 211,
    "por_fornecedor": {"elotech": 108, "betha": 59, "equiplano": 36, "pronim": 14, "ipm": 28, "inga": 32},
    "sem_fornecedor_identificado": 135,
    "robots_proibe_tudo": 39,
}
# Fornecedores com adaptador na coleta: a câmara que usa um deles e ainda não está em
# `entidades.toml` está "na fila", não "sem adaptador".
COM_ADAPTADOR = frozenset({"elotech", "betha", "equiplano"})
# Atividade legislativa (SAPL): o que o levantamento achou. Contagem do levantamento, com data.
LEVANTAMENTO_SAPL = {
    "camaras_que_linkam": 114,     # câmaras do PR com link para sapl.<cidade>.pr.leg.br na página inicial
    "enderecos_no_dns": 177,       # endereços sapl.<cidade>.pr.leg.br que existem no DNS (399 nomes testados)
    "crawl_delay": 60,
}
NOME_FORNECEDOR = {
    "elotech": "Elotech", "betha": "Betha Cloud", "equiplano": "Equiplano", "pronim": "Govbr Pronim", "ipm": "IPM Atende.net",
    "inga": "Inga Digital", "cr2": "CR2", "softcam": "SOFTCAM", "econtab": "eContab", "conexaogov": "Conexão Gov",
}


def _ler_csv(nome: str) -> list[dict[str, str]]:
    with (PASTA / nome).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(l for l in f if not l.startswith("#")))


def _p(fontes: list[str], coleta: dict[str, str]) -> dict:
    return {"fontes": sorted(fontes), "coleta": max(((coleta.get(f) or "")[:10] for f in fontes), default="")}


def casas(con: sqlite3.Connection, indice: list[dict], coleta: dict[str, str], municipal_ano: dict, casa_ano: dict, casa_cat: dict,
          casa_linhas: Counter, casa_forn: dict, nomes_forn: dict, cobertura_casa: dict, sem_publicacao: dict, subsidio: dict,
          _d: Callable[[object], str]) -> list[dict]:
    """Um resumo (para o índice) e um detalhe (para a página) de cada casa coletada."""
    por_casa: dict[str, list] = defaultdict(list)
    for f in FONTES:
        if f.id != "tse" and f.dado == "despesa":
            por_casa[f.sistema.casa].append(f)
    membros: dict[str, list] = defaultdict(list)
    for i in indice:
        membros[i["casa"]].append(i)
    rev_linhas = {r[0]: r[1] for r in con.execute(
        "SELECT d.fonte, COUNT(*) FROM despesas d JOIN despesa_situacao s USING(chave) WHERE s.situacao='revisao' GROUP BY 1")}
    pend = {r[0]: r[1] for r in con.execute("SELECT fonte, COUNT(*) FROM pendencias WHERE item NOT LIKE 'servidores-%' GROUP BY 1")}
    equacao = {r[0]: dict(r) for r in con.execute(
        "SELECT fonte, esperado, obtido, resultado, detalhe FROM conferencias WHERE verificacao='origem_igual_coletado_mais_revisao'")}
    erros = {r[0]: dict(r) for r in con.execute(
        "SELECT fonte, obtido, resultado, detalhe FROM conferencias WHERE verificacao='erros_em_aberto'")}
    outras: dict[str, list] = defaultdict(list)
    for r in con.execute("""SELECT fonte, verificacao, escopo, esperado, obtido, resultado, detalhe FROM conferencias
                            WHERE verificacao NOT IN ('origem_igual_coletado_mais_revisao', 'erros_em_aberto', 'api_x_arquivo')
                            ORDER BY fonte, verificacao, escopo"""):
        outras[r["fonte"]].append(dict(r))
    motivos: dict[str, Counter] = defaultdict(Counter)
    for r in con.execute("""SELECT d.fonte, s.motivo, COUNT(*) FROM despesas d JOIN despesa_situacao s USING(chave)
                            WHERE s.situacao='revisao' GROUP BY 1, 2"""):
        motivos[r[0]][r[1]] += r[2]
    for r in con.execute("SELECT fonte, motivo, COUNT(*) FROM pendencias WHERE item NOT LIKE 'servidores-%' GROUP BY 1, 2"):
        motivos[r[0]][r[1]] += r[2]

    out = []
    for cid, casa in entidades.casas().items():
        fontes = [f for f in por_casa.get(cid, []) if con.execute("SELECT 1 FROM inventario WHERE fonte=? LIMIT 1", (f.id,)).fetchone()]
        if not fontes:
            continue
        ids = [f.id for f in fontes]
        p = _p(ids, coleta)
        pessoas = sorted(membros.get(cid, []), key=lambda m: (normalizar_nome(m["nome"]), m["id"]))
        em_revisao = sum(rev_linhas.get(f, 0) + pend.get(f, 0) for f in ids)
        fechou = all(equacao.get(f, {}).get("resultado", "confere") == "confere" for f in ids)
        sem_erro = all(erros.get(f, {}).get("resultado", "confere") == "confere" for f in ids)
        linhas = casa_linhas.get(cid, 0)
        # coletada = a conta fechou e não sobrou erro; casa sem diária de vereador (a fonte só tem
        # diária de servidor) também é coletada: o que ela publica está aqui
        situacao = "coletada" if fechou and sem_erro else "em_revisao"
        de, ate = cobertura_casa.get(cid, (0, 0))
        resumo = {
            "id": cid, "nome": casa.nome, "tipo": casa.tipo, "esfera": casa.esfera, "uf": casa.uf, "municipio": casa.municipio,
            "ibge": casa.ibge, "cargo": casa.cargo, "de": de, "ate": ate,
            "sistemas": [{"fonte": f.id, "sistema": f.sistema.sistema, "fornecedor": f.sistema.fornecedor, "modo": f.sistema.modo,
                          "de": f.sistema.cobre_de, "ate": f.sistema.cobre_ate, "endereco": f.sistema.endereco} for f in fontes],
            "parlamentares": len(pessoas), "com_despesa": sum(1 for m in pessoas if m["linhas"]), "linhas": linhas,
            "total": _d(sum(casa_ano.get(cid, Counter()).values(), Decimal(0))), "em_revisao": em_revisao, "situacao": situacao,
            "p": p,
        }
        anos = sorted(set(casa_ano.get(cid, {})) | set(municipal_ano.get(cid, {})) | sem_publicacao.get(cid, set()))
        por_ano = []
        for a in anos:
            linha: dict = {"ano": a, "total": _d(casa_ano[cid][a]) if a in casa_ano.get(cid, {}) else None}
            if casa.tipo == "camara_municipal":
                m = municipal_ano.get(cid, {}).get(a)
                linha |= {"vereadores": _d(m["vereadores"]) if m else None, "servidores": _d(m["servidores"]) if m else None,
                          "linhas": m["linhas"] if m else 0, "linhas_vereadores": m["linhas_vereadores"] if m else 0,
                          "fonte_nao_publica": a in sem_publicacao.get(cid, set())}
            por_ano.append(linha)
        sub = sorted((s["valor"] for pid in (m["id"] for m in pessoas) for s in subsidio.get(pid, [])), key=Decimal)
        sub_datas = sorted({s["data_referencia"] for pid in (m["id"] for m in pessoas) for s in subsidio.get(pid, [])})
        detalhe = {
            **resumo,
            "por_ano": por_ano,
            "por_categoria": {c: _d(v) for c, v in casa_cat.get(cid, Counter()).most_common() if c},
            "membros": [{"id": m["id"], "nome": m["nome"], "partido": m["partido"], "total": m["total"], "linhas": m["linhas"]} for m in pessoas],
            # fornecedor (CNPJ) pago pelo maior número de parlamentares da casa: é o que liga uns aos outros no grafo
            "fornecedores_comuns": [{"doc": doc, "nome": nomes_forn.get(doc), "parlamentares": n}
                                    for doc, n in casa_forn.get(cid, Counter()).most_common(10) if n >= 2],
            "subsidio": ({"min": sub[0], "max": sub[-1], "pessoas": len(sub), "datas": sub_datas,
                          "fontes": sorted({s["fonte"] for pid in (m["id"] for m in pessoas) for s in subsidio.get(pid, [])})} if sub else None),
            "conferencia": [{"fonte": f, **{k: v for k, v in equacao.get(f, {}).items() if k != "fonte"},
                             "erros": erros.get(f, {}).get("obtido")} for f in ids],
            "outras_conferencias": [c for f in ids for c in outras.get(f, [])][:40],
            "em_revisao_por_motivo": sorted(({"fonte": f, "motivo": mot, "linhas": n} for f in ids for mot, n in motivos.get(f, {}).items()),
                                            key=lambda x: -x["linhas"])[:30],
        }
        out.append({"resumo": resumo, "detalhe": detalhe})
    return out


def levantamento_atividade() -> dict:
    return {"levantamento": {"data": DATA_LEVANTAMENTO, **LEVANTAMENTO_SAPL}}


def cobertura(casas_pub: list[dict]) -> dict:
    """Todas as casas: as coletadas (da coleta) e as de fora (do levantamento), com o motivo."""
    coletadas = {c["resumo"]["id"]: c["resumo"] for c in casas_pub}
    por_ibge = {c["ibge"]: c for c in coletadas.values() if c["tipo"] == "camara_municipal" and c["ibge"]}
    configuradas = {e.ibge for e in entidades.municipais()}
    de_fora = entidades.de_fora()
    camaras = []
    for l in _ler_csv("camaras-pr.csv"):
        ibge = int(l["ibge"])
        forn = l["fornecedor"]
        c = por_ibge.get(ibge)
        detalhe = None
        if c:
            situacao, motivo = c["situacao"], None
        elif ibge in de_fora:
            # configurada, mas a coleta não tem como ler: o motivo é da própria configuração
            situacao, (motivo, detalhe, _) = "fora", de_fora[ibge]
        elif l["barreira"]:
            situacao, motivo = "fora", {"robots": "robots", "robots+cloudflare": "robots_cloudflare", "anti_robo": "anti_robo",
                                        "cloudflare": "cloudflare", "sistema_interno": "sistema_interno"}.get(l["barreira"], "outro")
        elif forn in COM_ADAPTADOR:
            situacao, motivo = "fora", "na_fila" if ibge not in configuradas else "outro"
        elif forn in ("ipm",):
            situacao, motivo = "fora", "robots_cloudflare"
        elif forn in ("inga",):
            situacao, motivo = "fora", "robots"
        elif forn:
            situacao, motivo = "fora", "sem_adaptador"
        else:
            situacao, motivo = "fora", "nao_identificado"
        camaras.append({"ibge": ibge, "municipio": l["municipio"], "fornecedor": NOME_FORNECEDOR.get(forn) if forn else None,
                        "portal": l["portal"] or None, "situacao": situacao, "motivo": motivo, "base": l["base"] or None,
                        **({"detalhe": detalhe} if detalhe else {}),
                        **({"casa": c["id"], "parlamentares": c["parlamentares"], "linhas": c["linhas"]} if c else {})})
    por_uf = {c["uf"]: c for c in coletadas.values() if c["tipo"] == "assembleia"}
    assembleias = []
    for l in _ler_csv("assembleias.csv"):
        c = por_uf.get(l["uf"])
        assembleias.append({"uf": l["uf"], "sigla": l["sigla"], "nome": l["nome"], "cadeiras": int(l["cadeiras"]), "sistema": l["sistema"],
                            "situacao": c["situacao"] if c else "fora", "motivo": None if c else l["motivo"], "detalhe": l["detalhe"] or None,
                            **({"casa": c["id"], "parlamentares": c["parlamentares"], "linhas": c["linhas"]} if c else {})})
    federal = [{"id": "camara-deputados", "nome": "Câmara dos Deputados", "situacao": coletadas.get("camara-deputados", {}).get("situacao", "fora"),
                **({"parlamentares": coletadas["camara-deputados"]["parlamentares"], "linhas": coletadas["camara-deputados"]["linhas"]}
                   if "camara-deputados" in coletadas else {})},
               {"id": "senado", "nome": "Senado Federal", "situacao": "fora", "motivo": "depois"}]
    medidas = {
        "camaras_coletadas": sum(1 for c in camaras if c.get("casa")),
        "assembleias_coletadas": sum(1 for a in assembleias if a.get("casa")),
        "parlamentares": sum(c["parlamentares"] for c in coletadas.values()),
        "linhas": sum(c["linhas"] for c in coletadas.values()),
        "sistemas": sorted({s["fornecedor"] if c["tipo"] == "camara_municipal" else s["sistema"] for c in coletadas.values() for s in c["sistemas"]}),
    }
    return {"levantamento": {"data": DATA_LEVANTAMENTO, "camaras_pr": LEVANTAMENTO_CAMARAS,
                             "camaras_com_fornecedor_nomeado": sum(1 for c in camaras if c["fornecedor"])},
            "medidas": medidas, "camaras_pr": camaras, "assembleias": assembleias, "federal": federal}


# ---------------------------------------------------------------------------
# Mapas: a malha do IBGE (qualidade mínima) vira caminho de SVG, uma vez, no publicar
# ---------------------------------------------------------------------------

def _caminhos(geo: dict, largura: float, chave) -> dict:
    pontos = []
    for f in geo["features"]:
        g = f["geometry"]
        poligonos = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for pol in poligonos:
            for anel in pol:
                pontos.extend(anel)
    lon0, lon1 = min(p[0] for p in pontos), max(p[0] for p in pontos)
    lat0, lat1 = min(p[1] for p in pontos), max(p[1] for p in pontos)
    k = math.cos(math.radians((lat0 + lat1) / 2))
    escala = largura / ((lon1 - lon0) * k)
    altura = (lat1 - lat0) * escala

    def xy(p):
        return f"{(p[0] - lon0) * k * escala:.1f} {(lat1 - p[1]) * escala:.1f}"

    areas = []
    for f in geo["features"]:
        g = f["geometry"]
        poligonos = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        d = "".join("M" + "L".join(xy(p) for p in anel[:-1]) + "Z" for pol in poligonos for anel in pol)
        areas.append({"id": chave(f["properties"]["codarea"]), "d": d})
    return {"viewBox": f"0 0 {largura:.0f} {altura:.0f}", "areas": areas,
            "fonte": "IBGE, API de malhas (v3), qualidade mínima", "baixado_em": DATA_LEVANTAMENTO}


def mapas() -> dict[str, dict]:
    ufs = {str(u["ibge"]): u["sigla"] for u in json.loads((PASTA / "ufs.json").read_text(encoding="utf-8"))}
    pr = json.loads((PASTA / "malha-pr-municipios.geojson").read_text(encoding="utf-8"))
    br = json.loads((PASTA / "malha-br-uf.geojson").read_text(encoding="utf-8"))
    return {"mapa-pr.json": _caminhos(pr, 800, int), "mapa-br.json": _caminhos(br, 600, lambda c: ufs[str(c)])}
