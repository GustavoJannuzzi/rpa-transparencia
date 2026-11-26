"""publicar: os JSON da plataforma, só com o que passou na conferência.

Todo número publicado leva procedência: a fonte, a data da coleta e, quando é
uma linha, o link do documento oficial ou da página de onde saiu.
"""

from __future__ import annotations

import csv
import json
import math
import shutil
import sqlite3
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from .. import config
from ..fontes import FONTES
from ..nucleo.banco import agora
from ..nucleo.texto import cpfs_expostos, mascarar_cpf, slug
from .grafo import layout

PUBLICAVEIS = ("ok", "fora_da_soma")
PREFIXOS_URL = [
    "https://www.camara.leg.br/cota-parlamentar/documentos/publ/",
    "https://www.camara.leg.br/cota-parlamentar/nota-fiscal-eletronica?ideDocumentoFiscal=",
    "http://www.camara.leg.br/cota-parlamentar/nota-fiscal-eletronica?ideDocumentoFiscal=",
]
NOME_FONTE = {f.id: f.sistema.sistema for f in FONTES}


class CpfNaPublicacao(RuntimeError):
    """Sobrou CPF no que ia para o ar: o publicar para em vez de gravar."""


def _d(v) -> str:
    """Decimal como texto exato, sem notação científica. Completa com zeros até
    duas casas (200.0 -> 200.00), o que não muda o valor; nunca corta casas."""
    d = Decimal(v)
    if d.as_tuple().exponent > -2:
        d = d.quantize(Decimal("0.01"))
    return format(d, "f")


def _sem_cpf(obj):
    """Última barreira antes do repositório público: nenhum texto sai com CPF."""
    if isinstance(obj, str):
        return mascarar_cpf(obj)
    if isinstance(obj, dict):
        return {k: _sem_cpf(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sem_cpf(v) for v in obj]
    return obj


def _escrever(caminho: Path, obj) -> int:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(_sem_cpf(obj), ensure_ascii=False, separators=(",", ":"))
    # trava: o que sobrar (um número fora de texto, um formato novo) para a publicação
    if n := cpfs_expostos(txt):
        raise CpfNaPublicacao(f"{caminho.name}: {n} CPF(s) sem máscara; nada foi gravado neste arquivo")
    caminho.write_text(txt, encoding="utf-8")
    return len(txt)


def _url_compacta(url: str | None):
    if not url:
        return None
    for i, p in enumerate(PREFIXOS_URL):
        if url.startswith(p):
            return [i, url[len(p):]]
    return url


def _ultima_coleta(con) -> dict[str, str]:
    # só rodadas que de fato coletaram algum item (uma rodada que só retomou o que
    # já estava ok não muda a data dos dados)
    return {r[0]: r[1] for r in con.execute(
        "SELECT fonte, MAX(fim) FROM coletas WHERE etapa='coletar' AND json_extract(totais, '$.ok') > 0 GROUP BY fonte")}


def publicar(con: sqlite3.Connection) -> list[str]:
    destino = config.destino_plataforma()
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)
    coleta = _ultima_coleta(con)
    log: list[str] = []
    tamanho = 0

    cats_rotulo = {}
    from .. import de_para
    for (fonte, origem), linha in de_para._tabela("categorias.csv").items():
        cats_rotulo[linha["categoria"]] = linha["rotulo"]

    parl = {r["id"]: dict(r) for r in con.execute("SELECT * FROM parlamentares")}
    filiacoes = defaultdict(list)
    for r in con.execute("SELECT * FROM filiacoes ORDER BY parlamentar_id, desde"):
        filiacoes[r["parlamentar_id"]].append({"partido": r["partido"], "desde": r["desde"], "ate": r["ate"], "base": r["base"], "fonte": r["fonte"]})

    # ---------- despesas publicáveis, por parlamentar ----------
    por_parl: dict[str, list] = defaultdict(list)
    tot_parl_cat: dict[str, Counter] = defaultdict(Counter)
    tot_parl_ano: dict[str, Counter] = defaultdict(Counter)
    tot_partido_cat: dict[str, Counter] = defaultdict(Counter)
    tot_partido_mes: dict[str, Counter] = defaultdict(Counter)
    fontes_partido: dict[str, set] = defaultdict(set)
    # procedência por recorte: quais fontes e quantas linhas entraram em cada soma
    rec_ano: dict[tuple, list] = defaultdict(lambda: [set(), 0])
    rec_cat: dict[tuple, list] = defaultdict(lambda: [set(), 0])
    rec_pmes: dict[tuple, list] = defaultdict(lambda: [set(), 0])
    rec_pcat: dict[tuple, list] = defaultdict(lambda: [set(), 0])
    fontes_parl: dict[str, set] = defaultdict(set)
    fornecedores_dep: dict[str, Counter] = defaultdict(Counter)  # pid -> cnpj -> n linhas
    nomes_forn: dict[str, str] = {}
    camara_cmc_ano: dict[int, dict] = defaultdict(lambda: {"vereadores": Decimal(0), "servidores": Decimal(0), "linhas": 0})
    exportar = defaultdict(list)

    def partido_em(pid: str, competencia: str) -> str | None:
        fs = filiacoes.get(pid, [])
        for f in fs:
            if (f["desde"] or "0000") <= competencia <= (f["ate"] or "9999"):
                return f["partido"]
        return parl.get(pid, {}).get("partido_atual")

    cur = con.execute("""SELECT d.*, s.situacao, s.motivo, s.parlamentar_id, s.categoria AS cat_unica FROM despesas d JOIN despesa_situacao s USING(chave)
                         WHERE s.situacao IN ('ok','fora_da_soma') ORDER BY d.fonte, d.data, d.chave""")
    n_pub = 0
    while True:
        linhas = cur.fetchmany(20000)
        if not linhas:
            break
        for d in linhas:
            n_pub += 1
            valor = Decimal(d["valor"])
            soma = d["situacao"] == "ok"
            pid = d["parlamentar_id"]
            if d["fonte"].startswith("cmc_"):
                k = "vereadores" if d["beneficiario_tipo"] == "parlamentar" else "servidores"
                if soma:
                    camara_cmc_ano[int(d["ano"])][k] += valor
                camara_cmc_ano[int(d["ano"])]["linhas"] += 1
            if not pid:
                continue
            extra = json.loads(d["extra"] or "{}")
            info: dict = {}
            if not soma:
                info["s"] = d["motivo"]
            elif d["motivo"]:
                info["o"] = d["motivo"]
            if d["fonte"].startswith("cmc_"):
                info["f"] = d["fonte"]
                info["loc"] = d["localizador"]
                info["src"] = d["url"]
                info["k"] = d["coletado_em"][:10]
                if d["descricao"]:
                    info["x"] = d["descricao"][:240]
                for campo in ("hospedagem", "transporte", "devolvido"):
                    if extra.get(campo) and extra[campo] not in ("None", "0", "0.00"):
                        info[campo[:4]] = extra[campo]
            forn = (d["fornecedor_doc"], d["fornecedor_nome"]) if d["fornecedor_nome"] else None
            linha = (d["data"] or d["competencia"], d["competencia"], d["cat_unica"], forn, _d(valor),
                     _url_compacta(d["documento_url"]), info or None, d["fonte"], d["coletado_em"][:10])
            por_parl[pid].append(linha)
            fontes_parl[pid].add(d["fonte"])
            if soma:
                tot_parl_cat[pid][d["cat_unica"]] += valor
                tot_parl_ano[pid][int(d["ano"])] += valor
                for chave_rec, dic in (((pid, int(d["ano"])), rec_ano), ((pid, d["cat_unica"]), rec_cat)):
                    dic[chave_rec][0].add(d["fonte"])
                    dic[chave_rec][1] += 1
                p = partido_em(pid, d["competencia"])
                if p:
                    tot_partido_cat[p][d["cat_unica"]] += valor
                    tot_partido_mes[p][d["competencia"]] += valor
                    fontes_partido[p].add(d["fonte"])
                    for chave_rec, dic in (((p, d["competencia"]), rec_pmes), ((p, d["cat_unica"]), rec_pcat)):
                        dic[chave_rec][0].add(d["fonte"])
                        dic[chave_rec][1] += 1
                if d["fornecedor_tipo"] == "cnpj" and d["fornecedor_doc"]:
                    fornecedores_dep[pid][d["fornecedor_doc"]] += 1
                    nomes_forn.setdefault(d["fornecedor_doc"], d["fornecedor_nome"])
            exportar[d["fonte"]].append((pid, parl.get(pid, {}).get("nome"), d["data"], d["competencia"], d["cat_unica"],
                                         d["fornecedor_nome"], d["fornecedor_doc"], _d(valor), d["situacao"], d["documento_url"],
                                         d["coletado_em"]))

    # ---------- gabinetes (só onde Betha e Elotech contam as mesmas pessoas) ----------
    revisados = {r[0] for r in con.execute("SELECT chave FROM revisao WHERE tipo='gabinete'")}
    gab_pid = {r[0]: r[1] for r in con.execute("SELECT ref, parlamentar_id FROM parlamentar_ids WHERE fonte='gabinete'")}
    gab_por_pid: dict[str, list] = defaultdict(list)
    for r in con.execute("SELECT * FROM gabinetes"):
        pid = gab_pid.get(r["ref_parlamentar"])
        if r["ref_parlamentar"] in revisados or pid is None:
            continue
        gab_por_pid[pid].append({"fonte": r["fonte"], "rotulo": "remuneração contratual" if r["fonte"] == "cmc_betha" else "remuneração",
                                 "competencia": r["competencia"], "data_referencia": r["data_referencia"], "pessoas": r["pessoas"],
                                 "custo": _d(r["custo"]), "k": r["coletado_em"][:10], "src": r["url"], "lotacao": r["lotacao_original"]})

    # ---------- arquivos por parlamentar ----------
    indice = []
    for pid, p in parl.items():
        linhas = sorted(por_parl.get(pid, []), key=lambda l: l[0], reverse=True)
        anos = sorted({int(l[1][:4]) for l in linhas}, reverse=True)
        total = sum(tot_parl_cat[pid].values(), Decimal(0))
        extra = json.loads(p["extra"] or "{}")
        cab = {
            "id": pid, "nome": p["nome"], "nome_civil": p["nome_civil"], "casa": p["casa"], "uf": p["uf"],
            "municipio": p["municipio"], "partido": p["partido_atual"], "filiacoes": filiacoes.get(pid, []),
            "anos": anos, "fontes": sorted(fontes_parl.get(pid, set())),
            "total": _d(total), "linhas": sum(1 for l in linhas if not (l[6] and "s" in l[6])),
            "por_categoria": {c: _d(v) for c, v in tot_parl_cat[pid].most_common()},
            "por_ano": {str(a): _d(v) for a, v in sorted(tot_parl_ano[pid].items())},
            "procedencia_ano": {str(a): {"fontes": sorted(rec_ano[(pid, a)][0]), "linhas": rec_ano[(pid, a)][1]} for a in sorted(tot_parl_ano[pid])},
            "procedencia_categoria": {c: {"fontes": sorted(rec_cat[(pid, c)][0]), "linhas": rec_cat[(pid, c)][1]} for c in tot_parl_cat[pid]},
            "gabinete": gab_por_pid.get(pid, []),
            "mandatos": extra.get("eleicoes", []), "id_camara": extra.get("id_camara"),
            "top_fornecedores": [{"doc": doc, "nome": nomes_forn.get(doc), "linhas": n}
                                 for doc, n in fornecedores_dep[pid].most_common(8)],
            "p": {"coleta": {f: (coleta.get(f) or "")[:10] for f in fontes_parl.get(pid, set())}},
        }
        tamanho += _escrever(destino / "parlamentares" / f"{pid}.json", cab)
        for a in anos:
            tamanho += _escrever(destino / "parlamentares" / pid / f"{a}.json", _arquivo_ano([l for l in linhas if l[1].startswith(str(a))]))
        indice.append({"id": pid, "nome": p["nome"], "casa": p["casa"], "uf": p["uf"], "partido": p["partido_atual"],
                       "total": _d(total), "linhas": cab["linhas"], "gabinete": bool(cab["gabinete"])})
    indice.sort(key=lambda x: x["nome"])
    tamanho += _escrever(destino / "parlamentares.json", indice)

    # ---------- partidos ----------
    membros = defaultdict(list)
    for i in indice:
        if i["partido"]:
            membros[i["partido"]].append({"id": i["id"], "nome": i["nome"], "casa": i["casa"], "uf": i["uf"], "total": i["total"]})
    partidos = []
    for sigla in sorted(set(membros) | set(tot_partido_cat)):
        total = sum(tot_partido_cat[sigla].values(), Decimal(0))
        obj = {"sigla": sigla, "membros": sorted(membros.get(sigla, []), key=lambda m: m["nome"]),
               "por_categoria": {c: _d(v) for c, v in tot_partido_cat[sigla].most_common()},
               "por_mes": {m: _d(v) for m, v in sorted(tot_partido_mes[sigla].items())},
               "total": _d(total),
               "fontes": sorted(fontes_partido.get(sigla, set())),
               "procedencia_mes": {m: {"fontes": sorted(rec_pmes[(sigla, m)][0]), "linhas": rec_pmes[(sigla, m)][1]} for m in sorted(tot_partido_mes[sigla])},
               "procedencia_categoria": {c: {"fontes": sorted(rec_pcat[(sigla, c)][0]), "linhas": rec_pcat[(sigla, c)][1]} for c in tot_partido_cat[sigla]},
               "coleta": {f: (coleta.get(f) or "")[:10] for f in sorted(fontes_partido.get(sigla, set()))},
               "regra": "soma das despesas conferidas de cada parlamentar no mês em que estava no partido (deputados: partido informado na linha da cota; vereadores: partido na eleição do mandato)"}
        tamanho += _escrever(destino / "partidos" / f"{slug(sigla)}.json", obj)
        partidos.append({"sigla": sigla, "slug": slug(sigla), "federal": sum(1 for m in membros.get(sigla, []) if m["casa"] == "camara-deputados"),
                         "municipal": sum(1 for m in membros.get(sigla, []) if m["casa"] == "cmc"), "total": _d(total)})
    tamanho += _escrever(destino / "partidos.json", partidos)
    tamanho += _escrever(destino / "categorias.json", cats_rotulo)

    # ---------- grafos ----------
    tamanho += _escrever(destino / "grafo-brasil.json", _grafo_brasil(parl, fornecedores_dep, nomes_forn, coleta))
    tamanho += _escrever(destino / "grafo-parana.json", _grafo_parana(parl, filiacoes, indice))

    # ---------- fontes, cobertura, conferência e revisão ----------
    tamanho += _escrever(destino / "fontes.json", _fontes(con, coleta, camara_cmc_ano))
    tamanho += _escrever(destino / "revisao.json", _revisao(con))

    # ---------- CSV ----------
    pasta_csv = config.dados() / "exportacao"
    pasta_csv.mkdir(parents=True, exist_ok=True)
    for fonte, linhas in exportar.items():
        with (pasta_csv / f"{fonte}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["parlamentar_id", "parlamentar", "data", "competencia", "categoria", "fornecedor", "documento_fornecedor",
                        "valor", "situacao", "link_documento", "coletado_em"])
            w.writerows(_sem_cpf(linhas))
    log.append(f"publicadas {n_pub} despesas de {len(indice)} parlamentares; {len(partidos)} partidos; {tamanho / 1e6:.1f} MB de JSON em {destino}")
    log.append(f"CSV em {pasta_csv}")
    return log


def _arquivo_ano(linhas: list[tuple]) -> dict:
    """Formato em colunas: tabela de fornecedores, de categorias e de coletas uma vez por arquivo."""
    fornecedores: list = []
    idx_f: dict = {}
    categorias: list = []
    idx_c: dict = {}
    coletas: list = []
    idx_k: dict = {}
    saida = []
    for data, _comp, cat, forn, valor, url, info, fonte, coleta in linhas:
        if forn is not None and forn not in idx_f:
            idx_f[forn] = len(fornecedores)
            fornecedores.append(list(forn))
        if cat not in idx_c:
            idx_c[cat] = len(categorias)
            categorias.append(cat)
        k = (fonte, coleta)
        if k not in idx_k:
            idx_k[k] = len(coletas)
            coletas.append({"fonte": fonte, "coletado_em": coleta})
        saida.append([data, idx_c[cat], idx_f[forn] if forn is not None else -1, valor,
                      (f"{url[0]}:{url[1]}" if isinstance(url, list) else url), idx_k[k], info])
    return {"colunas": ["data", "categoria", "fornecedor", "valor", "documento", "coleta", "info"],
            "prefixos_documento": PREFIXOS_URL, "categorias": categorias, "fornecedores": fornecedores,
            "coletas": coletas, "linhas": saida}


def _cor_indice(siglas: list[str]) -> dict[str, int]:
    return {s: i for i, s in enumerate(sorted(siglas))}


def _grafo_brasil(parl, fornecedores_dep, nomes_forn, coleta) -> dict:
    deps = [pid for pid in parl if pid.startswith("dep-") and fornecedores_dep.get(pid)]
    n = len(deps)
    df = Counter()
    for pid in deps:
        for doc in fornecedores_dep[pid]:
            df[doc] += 1
    teto = max(3, int(n * 0.08))  # fornecedor usado por mais de 8% dos deputados não liga ninguém
    por_forn = defaultdict(list)
    for pid in deps:
        for doc in fornecedores_dep[pid]:
            if 2 <= df[doc] <= teto:
                por_forn[doc].append(pid)
    peso = Counter()
    exemplo: dict[tuple, list] = defaultdict(list)
    for doc, membros in por_forn.items():
        idf = math.log(n / df[doc])
        membros.sort()
        for i, a in enumerate(membros):
            for b in membros[i + 1:]:
                peso[(a, b)] += idf
                if len(exemplo[(a, b)]) < 3:
                    exemplo[(a, b)].append(doc)
    # cada deputado fica com as ligações mais fortes (até 5) para o grafo não virar novelo
    vizinhos = defaultdict(list)
    for (a, b), w in peso.items():
        vizinhos[a].append((w, b))
        vizinhos[b].append((w, a))
    arestas = {}
    for a, vs in vizinhos.items():
        for w, b in sorted(vs, reverse=True)[:5]:
            k = (min(a, b), max(a, b))
            arestas[k] = peso[k]
    nos = [{"id": pid, "rotulo": parl[pid]["nome"], "partido": parl[pid]["partido_atual"], "uf": parl[pid]["uf"],
            "grau": len(vizinhos.get(pid, []))} for pid in deps]
    pos = layout([no["id"] for no in nos], [(a, b, w) for (a, b), w in arestas.items()])
    for no in nos:
        no["x"], no["y"] = pos[no["id"]]
    siglas = sorted({no["partido"] for no in nos if no["partido"]})
    return {
        "nos": nos,
        "arestas": [{"a": a, "b": b, "peso": round(w, 3), "fornecedores": [{"doc": d, "nome": nomes_forn.get(d)} for d in exemplo[(a, b)]]}
                    for (a, b), w in sorted(arestas.items())],
        "partidos": siglas,
        "regra": (f"Ligação = fornecedores (CNPJ) em comum nas despesas conferidas. Cada fornecedor pesa log(N/n), em que n é o "
                  f"número de deputados que o usaram; fornecedores usados por mais de {teto} deputados (8%) não ligam ninguém. "
                  "Fornecedor pessoa física não entra. Cada deputado mostra até 5 ligações mais fortes."),
        "p": {"fonte": "camara_deputados", "coleta": (coleta.get("camara_deputados") or "")[:10]},
    }


def _layout_parana(nos: list[dict], arestas: list[dict]) -> dict[str, tuple[float, float]]:
    """Partidos onde o ForceAtlas2 os põe (perto de quem divide gente com eles); cada
    parlamentar num anel em volta do partido atual, sem cair em cima do nó do partido.
    Quem não tem partido resolvido fica num anel de fora."""
    import math

    partidos = [n["id"] for n in nos if n["tipo"] == "partido"]
    membros: dict[str, list[str]] = defaultdict(list)
    for n in nos:
        if n["tipo"] != "partido" and n.get("partido") and f"partido:{n['partido']}" in partidos:
            membros[f"partido:{n['partido']}"].append(n["id"])
    # vizinhança entre partidos: gente que passou pelos dois
    por_pessoa = defaultdict(set)
    for a in arestas:
        por_pessoa[a["a"]].add(a["b"])
    peso = Counter()
    for ps in por_pessoa.values():
        ps = sorted(ps)
        for i, x in enumerate(ps):
            for y in ps[i + 1:]:
                peso[(x, y)] += 1
    base = layout(partidos, [(x, y, float(w)) for (x, y), w in peso.items()], iteracoes=600, espalhar=6.0, gravidade=1.0)
    raio = {p: 26 + 9 * math.sqrt(len(membros.get(p, []))) for p in partidos}
    pos = {p: [base[p][0] * 1.0, base[p][1] * 1.0] for p in partidos}
    # afasta os anéis que se sobrepõem (relaxação simples, determinística)
    for _ in range(400):
        mexeu = False
        for i, x in enumerate(partidos):
            for y in partidos[i + 1:]:
                dx, dy = pos[y][0] - pos[x][0], pos[y][1] - pos[x][1]
                d = math.hypot(dx, dy) or 0.01
                minimo = raio[x] + raio[y] + 14
                if d < minimo:
                    emp = (minimo - d) / 2
                    ux, uy = (dx / d, dy / d) if d > 0.01 else (1.0, 0.0)
                    pos[x][0] -= ux * emp
                    pos[x][1] -= uy * emp
                    pos[y][0] += ux * emp
                    pos[y][1] += uy * emp
                    mexeu = True
        if not mexeu:
            break
    out: dict[str, tuple[float, float]] = {p: (round(v[0], 2), round(v[1], 2)) for p, v in pos.items()}
    for p, ms in membros.items():
        ms = sorted(ms)
        for k, m in enumerate(ms):
            ang = 2 * math.pi * k / len(ms) - math.pi / 2
            out[m] = (round(pos[p][0] + raio[p] * math.cos(ang), 2), round(pos[p][1] + raio[p] * math.sin(ang), 2))
    soltos = sorted(n["id"] for n in nos if n["id"] not in out)
    if soltos:
        xs = [v[0] for v in out.values()] or [0]
        ys = [v[1] for v in out.values()] or [0]
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        r = max(max(xs) - cx, max(ys) - cy, 100) + 60
        for k, m in enumerate(soltos):
            ang = 2 * math.pi * k / len(soltos)
            out[m] = (round(cx + r * math.cos(ang), 2), round(cy + r * math.sin(ang), 2))
    return out


def _grafo_parana(parl, filiacoes, indice) -> dict:
    pessoas = [i for i in indice if (i["casa"] == "camara-deputados" and i["uf"] == "PR") or i["casa"] == "cmc"]
    nos = []
    arestas = []
    partidos = set()
    for i in pessoas:
        nos.append({"id": i["id"], "rotulo": i["nome"], "tipo": "deputado" if i["casa"] == "camara-deputados" else "vereador",
                    "partido": i["partido"], "total": i["total"]})
        vistos = set()
        for f in filiacoes.get(i["id"], []):
            if f["partido"] in vistos:
                continue
            vistos.add(f["partido"])
            partidos.add(f["partido"])
            arestas.append({"a": i["id"], "b": f"partido:{f['partido']}", "atual": f["partido"] == i["partido"],
                            "periodo": f"{f['desde'] or ''}–{f['ate'] or ''}", "base": f["base"]})
    for p in sorted(partidos):
        nos.append({"id": f"partido:{p}", "rotulo": p, "tipo": "partido", "partido": p})
    pos = _layout_parana(nos, arestas)
    for n in nos:
        n["x"], n["y"] = pos[n["id"]]
    return {"nos": nos, "arestas": arestas, "partidos": sorted(partidos),
            "regra": "Deputados federais do Paraná (partido informado nas linhas da cota) e vereadores de Curitiba (partido na eleição de cada mandato, TSE), em volta do partido atual. As linhas mais fracas levam aos partidos de mandatos anteriores; quem está no anel de fora tem o partido em revisão."}


def _fontes(con, coleta, camara_cmc_ano) -> dict:
    fontes = []
    for f in FONTES:
        s = f.sistema
        totais = [dict(r) for r in con.execute("SELECT escopo, metrica, valor, texto_original, url, coletado_em FROM totais_oficiais WHERE fonte=? ORDER BY escopo, metrica", (f.id,))]
        conf = [dict(r) for r in con.execute("SELECT verificacao, escopo, esperado, obtido, resultado, detalhe FROM conferencias WHERE fonte=? ORDER BY verificacao, escopo", (f.id,))]
        sit = {r[0]: r[1] for r in con.execute("SELECT s.situacao, COUNT(*) FROM despesas d JOIN despesa_situacao s USING(chave) WHERE d.fonte=? GROUP BY 1", (f.id,))}
        pend = con.execute("SELECT COUNT(*) FROM pendencias WHERE fonte=?", (f.id,)).fetchone()[0]
        inv = {r[0]: r[1] for r in con.execute("SELECT situacao, COUNT(*) FROM inventario WHERE fonte=? GROUP BY 1", (f.id,))}
        ult = con.execute("""SELECT inicio, fim, situacao, totais FROM coletas WHERE fonte=? AND etapa='coletar'
                             AND json_extract(totais, '$.ok') > 0 ORDER BY id DESC LIMIT 1""", (f.id,)).fetchone()
        fontes.append({
            "id": f.id, "sistema": s.sistema, "fornecedor": s.fornecedor, "modo": s.modo, "casa": s.casa,
            "cobre_de": s.cobre_de, "cobre_ate": s.cobre_ate, "endereco": s.endereco, "o_que_tem": s.o_que_tem,
            "ultima_coleta": dict(ult) if ult else None, "inventario": inv, "situacoes": sit, "pendencias_de_leitura": pend,
            "totais_oficiais": totais, "conferencias": conf,
            "politica_robots": None,
        })
    cobertura = [
        {"de": 2010, "ate": 2012, "fonte": None, "rotulo": "Só despesas gerais da Câmara (sem diárias por pessoa)",
         "detalhe": "O sistema legado tem relatórios de despesa de 2010 a 2016, mas o de diárias começa em 2013."},
        {"de": 2013, "ate": 2016, "fonte": "cmc_legado", "rotulo": "Sistema legado — relatórios em PDF"},
        {"de": 2017, "ate": 2023, "fonte": "cmc_elotech", "rotulo": "Elotech — API pública"},
        {"de": 2024, "ate": 2025, "fonte": "cmc_prefeitura", "rotulo": "Portal da Prefeitura — postback ASP.NET",
         **({"detalhe": "Em revisão: " + "; ".join(
             f"{r[0].split('-')[1]}: {r[1]}" for r in con.execute(
                 "SELECT escopo, texto_original FROM totais_oficiais WHERE fonte='cmc_prefeitura' "
                 "AND metrica='ano_inteiro_x_mes_a_mes' AND valor='diverge' AND escopo < 'diarias-2026' ORDER BY escopo"))
             + ". O portal não publica total, então a diferença não tem como ser desempatada."}
            if con.execute("SELECT 1 FROM totais_oficiais WHERE fonte='cmc_prefeitura' AND metrica='ano_inteiro_x_mes_a_mes' "
                           "AND valor='diverge' AND escopo < 'diarias-2026'").fetchone() else {})},
        {"de": 2026, "ate": 2026, "fonte": "cmc_betha", "rotulo": "Betha — aplicação Vue",
         "detalhe": "2026 também aparece no portal da Prefeitura; as duas listas são conferidas uma contra a outra."},
    ]
    diarias_cmc = [{"ano": a, "vereadores": _d(v["vereadores"]), "servidores": _d(v["servidores"]), "linhas": v["linhas"]}
                   for a, v in sorted(camara_cmc_ano.items())]
    return {"gerado_em": agora(), "versao_robo": config.VERSAO_ROBO, "fontes": fontes, "cobertura_curitiba": cobertura,
            "diarias_camara_curitiba": diarias_cmc}


def _revisao(con) -> dict:
    grupos = []
    for r in con.execute("""SELECT fonte, tipo, motivo, COUNT(*) n FROM revisao GROUP BY 1, 2, 3 ORDER BY n DESC"""):
        exemplos = []
        for e in con.execute("SELECT chave, detalhe FROM revisao WHERE fonte=? AND tipo=? AND motivo=? LIMIT 3", (r["fonte"], r["tipo"], r["motivo"])):
            det = json.loads(e["detalhe"] or "{}")
            det.pop("texto_original", None) if r["tipo"] == "leitura" else None
            exemplos.append({"chave": e["chave"], "detalhe": det})
        grupos.append({"fonte": r["fonte"], "tipo": r["tipo"], "motivo": r["motivo"], "n": r["n"], "exemplos": exemplos})
    linhas_fora = {r[0]: r[1] for r in con.execute(
        "SELECT d.fonte, COUNT(*) FROM despesas d JOIN despesa_situacao s USING(chave) WHERE s.situacao='revisao' GROUP BY 1")}
    return {"grupos": grupos, "linhas_em_revisao_por_fonte": linhas_fora, "gerado_em": agora()}
