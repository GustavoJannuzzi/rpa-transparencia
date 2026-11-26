"""Conferência: identidade, de-para, regras de cada fonte, totais oficiais e a
equação de cada fonte (origem = coletado + revisão).

Tudo aqui é refeito a cada rodada a partir do que a coleta gravou. O que não fecha
vai para a fila de revisão e não é publicado.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from decimal import Decimal
from itertools import pairwise
from typing import Any

from .. import de_para
from .banco import agora, js, transacao
from .texto import normalizar_nome, slug

ELEICOES_CMC = [2012, 2016, 2020, 2024]

# Situações de uma despesa
OK = "ok"                      # publicada e somada
FORA_DA_SOMA = "fora_da_soma"  # publicada como informação; a própria fonte não a soma
CRUZADA = "conferencia_cruzada"  # repetida em outro sistema; usada só para conferir
REVISAO = "revisao"            # não publicada até uma pessoa olhar


class Revisor:
    def __init__(self, con: sqlite3.Connection):
        self.con = con

    def revisao(self, fonte: str, tipo: str, chave: str, motivo: str, detalhe: dict | None = None) -> None:
        self.con.execute(
            "INSERT OR IGNORE INTO revisao(fonte, tipo, chave, motivo, detalhe, criado_em) VALUES(?,?,?,?,?,?)",
            (fonte, tipo, chave, motivo, js(detalhe or {}), agora()),
        )

    def conferencia(self, fonte: str, verificacao: str, escopo: str, esperado, obtido, resultado: str, detalhe: str = "") -> None:
        self.con.execute(
            "INSERT OR REPLACE INTO conferencias(fonte, verificacao, escopo, esperado, obtido, resultado, detalhe, conferido_em) VALUES(?,?,?,?,?,?,?,?)",
            (fonte, verificacao, escopo, None if esperado is None else str(esperado), None if obtido is None else str(obtido),
             resultado, detalhe, agora()),
        )


def _titulo(nome: str) -> str:
    minusculas = {"DA", "DE", "DO", "DAS", "DOS", "E"}
    partes = []
    for i, p in enumerate(nome.split()):
        partes.append(p.lower() if (i > 0 and p.upper() in minusculas) else p[:1].upper() + p[1:].lower())
    return " ".join(partes)


# ---------------------------------------------------------------------------
# Identidade
# ---------------------------------------------------------------------------

def identidades(con: sqlite3.Connection, rv: Revisor) -> None:
    _deputados(con, rv)
    _vereadores(con, rv)


def _deputados(con, rv: Revisor) -> None:
    pessoas = defaultdict(list)
    for r in con.execute("SELECT ref, nome, partido, uf, extra FROM pessoas_fonte WHERE fonte='camara_deputados'"):
        pessoas[r["ref"]].append(r)
    filiacoes = defaultdict(list)
    for r in con.execute(
        """SELECT ref_parlamentar ref, json_extract(extra, '$.partido_na_linha') p, MIN(competencia) d, MAX(competencia) a, COUNT(*) n
           FROM despesas WHERE fonte='camara_deputados' AND ref_parlamentar IS NOT NULL GROUP BY 1, 2"""):
        if r["p"]:
            filiacoes[r["ref"]].append((r["p"], r["d"], r["a"], r["n"]))
    refs_ceap = {r[0] for r in con.execute("SELECT DISTINCT ref_parlamentar FROM despesas WHERE fonte='camara_deputados' AND ref_parlamentar IS NOT NULL")}
    for ref in sorted(set(pessoas) | refs_ceap):
        pid = f"dep-{ref}"
        regs = pessoas.get(ref, [])
        if not regs:
            rv.revisao("camara_deputados", "identidade", ref, "deputado nas despesas mas fora da lista da legislatura na API")
            continue
        nome = regs[0]["nome"]
        uf = regs[0]["uf"]
        foto = json.loads(regs[0]["extra"] or "{}").get("foto")
        fs = sorted(filiacoes.get(ref, []), key=lambda f: (f[2], f[1]))
        atual = fs[-1][0] if fs else (regs[0]["partido"] if len({r["partido"] for r in regs}) == 1 else None)
        if atual is None:
            rv.revisao("camara_deputados", "partido", ref, "partido atual indefinido: sem despesas e com mais de um partido na lista",
                       {"partidos": sorted({r["partido"] for r in regs})})
        con.execute("INSERT INTO parlamentares(id, nome, nome_civil, casa, uf, municipio, partido_atual, extra) VALUES(?,?,?,?,?,?,?,?)",
                    (pid, nome, None, "camara-deputados", uf, None, atual, js({"foto": foto, "id_camara": ref})))
        con.execute("INSERT INTO parlamentar_ids(fonte, ref, parlamentar_id, metodo) VALUES(?,?,?,?)",
                    ("camara_deputados", ref, pid, "id da API"))
        for p, d, a, n in fs:
            con.execute("INSERT INTO filiacoes(parlamentar_id, partido, desde, ate, fonte, base) VALUES(?,?,?,?,?,?)",
                        (pid, p, d, a, "camara_deputados", f"partido informado em {n} linha(s) da cota, de {d} a {a}"))
        if not fs and atual:
            con.execute("INSERT INTO filiacoes(parlamentar_id, partido, desde, ate, fonte, base) VALUES(?,?,?,?,?,?)",
                        (pid, atual, None, None, "camara_deputados", "lista de deputados da legislatura (API)"))


class _Uniao:
    def __init__(self):
        self.pai: dict[str, str] = {}

    def achar(self, x: str) -> str:
        self.pai.setdefault(x, x)
        while self.pai[x] != x:
            self.pai[x] = self.pai[self.pai[x]]
            x = self.pai[x]
        return x

    def unir(self, a: str, b: str) -> None:
        ra, rb = self.achar(a), self.achar(b)
        if ra != rb:
            self.pai[max(ra, rb)] = min(ra, rb)


def _tokens_nome(n: str) -> set[str]:
    return {t for t in normalizar_nome(n).split() if len(t) > 2}


def _vereadores(con, rv: Revisor) -> None:
    """Pessoa = componente ligado de matrículas e nomes que aparecem juntos.

    A matrícula muda de um mandato para outro (a mesma pessoa tem 1127 e 1184),
    então ela não é a identidade: é um elo entre nomes. Os relatórios de 2013–2014
    trazem o nome curto, que é o nome de urna do TSE; a candidatura liga o nome de
    urna ao nome civil.
    """
    u = _Uniao()
    apelidos: dict[str, str] = {}
    so_apelido: set[str] = set()  # nomes que só aparecem como nome parlamentar ou de urna
    def token_ref(ref: str) -> str:
        tipo, _, valor = ref.partition(":")
        return ("m:" if tipo == "mat" else "n:") + (valor if tipo == "mat" else normalizar_nome(valor))

    for r in con.execute("SELECT fonte, ref, nome, nome_parlamentar, matricula FROM pessoas_fonte WHERE casa='cmc'"):
        toks = [] if r["ref"].startswith("gab:") else [token_ref(r["ref"])]
        if r["nome"]:
            toks.append("n:" + normalizar_nome(r["nome"]))
        if r["matricula"]:
            toks.append("m:" + r["matricula"])
        if r["ref"].startswith("gab:") and r["nome_parlamentar"]:
            toks.append("n:" + normalizar_nome(r["nome_parlamentar"]))
            so_apelido.add(normalizar_nome(r["nome_parlamentar"]))
            apelidos[normalizar_nome(r["nome"])] = r["nome_parlamentar"]
        for a, b in pairwise(toks):
            u.unir(a, b)
        for t in toks:
            u.achar(t)
    refs = {(r[0], r[1]) for r in con.execute(
        "SELECT DISTINCT fonte, ref_parlamentar FROM despesas WHERE fonte LIKE 'cmc_%' AND ref_parlamentar IS NOT NULL")}
    refs |= {(r[0], r[1]) for r in con.execute("SELECT DISTINCT fonte, ref FROM pessoas_fonte WHERE casa='cmc' AND ref NOT LIKE 'gab:%'")}

    for _, ref in refs:
        u.achar(token_ref(ref))

    # Liga nome civil e nome de urna da mesma candidatura, só para quem aparece nas fontes da Câmara
    cands = defaultdict(list)
    for r in con.execute("SELECT ano_eleicao, nome_norm, nome_urna, partido, situacao FROM candidaturas"):
        cands[(r["ano_eleicao"], r["nome_norm"])].append(r)
        urna = normalizar_nome(r["nome_urna"])
        if urna and urna != r["nome_norm"]:
            if ("n:" + r["nome_norm"]) in u.pai or ("n:" + urna) in u.pai:
                u.unir("n:" + r["nome_norm"], "n:" + urna)
                so_apelido.add(urna)
            cands[(r["ano_eleicao"], urna)].append(r)

    componentes: dict[str, set[str]] = defaultdict(set)
    for t in list(u.pai):
        componentes[u.achar(t)].add(t)
    pid_de: dict[str, str] = {}
    info: dict[str, dict] = {}
    for grupo in componentes.values():
        nomes = sorted({t[2:] for t in grupo if t.startswith("n:")}, key=lambda n: (-len(n.split()), -len(n), n))
        if not nomes:
            continue
        canon = nomes[0]
        # nomes longos que não se parecem entre si: duas pessoas ligadas por engano
        longos = [n for n in nomes if len(n.split()) >= 3 and n not in so_apelido]
        suspeito = any(len(_tokens_nome(a) & _tokens_nome(b)) < 2 for i, a in enumerate(longos) for b in longos[i + 1:])
        pid = f"ver-cwb-{slug(canon)}"
        for t in grupo:
            pid_de[t] = pid
        info[pid] = {"canon": canon, "nomes": set(nomes), "anos": set(), "suspeito": suspeito,
                     "matriculas": sorted(t[2:] for t in grupo if t.startswith("m:"))}
        if suspeito:
            rv.revisao("cmc", "identidade", pid, "nomes diferentes ligados à mesma pessoa pelas matrículas",
                       {"nomes": nomes, "matriculas": info[pid]["matriculas"]})

    for fonte, ref in sorted(refs):
        t = token_ref(ref)
        if t not in pid_de:
            rv.revisao(fonte, "identidade", ref, "parlamentar sem nome em nenhuma das fontes", {"ref": ref})
            continue
        pid = pid_de[t]
        if info[pid]["suspeito"]:
            continue
        metodo = "matrícula" if t.startswith("m:") else "nome"
        con.execute("INSERT OR REPLACE INTO parlamentar_ids(fonte, ref, parlamentar_id, metodo) VALUES(?,?,?,?)", (fonte, ref, pid, metodo))

    # gabinetes ("gab:NOME CIVIL"): a pessoa dona do gabinete
    for (ref,) in con.execute("SELECT DISTINCT ref_parlamentar FROM gabinetes WHERE ref_parlamentar IS NOT NULL"):
        dono = pid_de.get("n:" + normalizar_nome(ref[4:]))
        if dono and not info[dono]["suspeito"]:
            con.execute("INSERT OR REPLACE INTO parlamentar_ids(fonte, ref, parlamentar_id, metodo) VALUES(?,?,?,?)", ("gabinete", ref, dono, "lotação do gabinete"))
        else:
            rv.revisao("cmc", "identidade", ref, "gabinete sem vereador identificado", {"lotacao": ref})

    for r in con.execute("""SELECT pi.parlamentar_id pid, d.ano FROM despesas d JOIN parlamentar_ids pi
                            ON pi.fonte=d.fonte AND pi.ref=d.ref_parlamentar WHERE d.fonte LIKE 'cmc_%' GROUP BY 1, 2"""):
        info[r["pid"]]["anos"].add(int(r["ano"]))
    for r in con.execute("""SELECT pi.parlamentar_id pid, p.periodo FROM pessoas_fonte p JOIN parlamentar_ids pi
                            ON pi.fonte=p.fonte AND pi.ref=p.ref WHERE p.casa='cmc'"""):
        if r["periodo"].isdigit():
            info[r["pid"]]["anos"].add(int(r["periodo"]))
        elif r["periodo"] == "atual":
            info[r["pid"]]["anos"].add(int(agora()[:4]))

    usados = sorted({r[0] for r in con.execute("SELECT DISTINCT parlamentar_id FROM parlamentar_ids WHERE parlamentar_id LIKE 'ver-%'")})
    for pid in usados:
        i = info[pid]
        civil = _titulo(i["canon"])
        apelido = next((apelidos[n] for n in i["nomes"] if n in apelidos), None)
        eleicoes = sorted({max([e for e in ELEICOES_CMC if e < a] or [0]) for a in i["anos"]} - {0})
        partido_atual = None
        urna_exib: str | None = None
        for e in eleicoes:
            achados = {(c["partido"], c["nome_urna"], c["situacao"], c["nome_norm"]) for n in i["nomes"] for c in cands.get((e, n), [])}
            partidos = {a[0] for a in achados}
            if len(partidos) == 1:
                p, urna_e, sit, _ = sorted(achados)[0]
                urna_exib = urna_e or urna_exib
                con.execute("INSERT INTO filiacoes(parlamentar_id, partido, desde, ate, fonte, base) VALUES(?,?,?,?,?,?)",
                            (pid, p, f"{e + 1}-01", f"{e + 4}-12", "tse", f"partido na eleição de {e} ({sit.lower()})"))
                partido_atual = p
            elif len(partidos) > 1:
                rv.revisao("tse", "partido", f"{pid}:{e}", "o nome casa com candidaturas de partidos diferentes na mesma eleição",
                           {"vereador": civil, "eleicao": e, "partidos": sorted(partidos)})
            else:
                rv.revisao("tse", "partido", f"{pid}:{e}", "nome não encontrado entre os candidatos a vereador da eleição",
                           {"vereador": civil, "eleicao": e, "nomes_tentados": sorted(i["nomes"])})
        nome_exib = _titulo(apelido) if apelido else (_titulo(urna_exib) if urna_exib else civil)
        con.execute("INSERT INTO parlamentares(id, nome, nome_civil, casa, uf, municipio, partido_atual, extra) VALUES(?,?,?,?,?,?,?,?)",
                    (pid, nome_exib, civil, "cmc", "PR", "Curitiba", partido_atual,
                     js({"anos": sorted(i["anos"]), "eleicoes": eleicoes, "matriculas": i["matriculas"],
                         "nome_exibido_de": "gabinete" if apelido else ("tse" if urna_exib else "nome civil")})))


# ---------------------------------------------------------------------------
# Situação de cada despesa
# ---------------------------------------------------------------------------

def _divergencias_api(con, rv: Revisor) -> set[tuple[str, int]]:
    """Amostra da API × arquivo anual, por categoria: devolve (categoria_original, ano) que divergem."""
    divergentes: set[tuple[str, int]] = set()
    amostras = con.execute("SELECT DISTINCT escopo FROM totais_oficiais WHERE fonte='camara_deputados' AND escopo LIKE 'api-%'").fetchall()
    sinal_trocado = total_api = 0
    for (escopo,) in amostras:
        _, dep, ano = escopo.split("-")
        ano = int(ano)
        api: defaultdict[str, list[Any]] = defaultdict(lambda: [0, Decimal("0")])  # [linhas, soma]
        for (cam,) in con.execute("SELECT caminho FROM originais WHERE fonte='camara_deputados' AND url LIKE ?",
                                  (f"%/deputados/{dep}/despesas?ano={ano}&%",)):
            from .. import config
            try:
                dados = json.loads((config.dados() / cam).read_text(encoding="utf-8"))["dados"]
            except FileNotFoundError:
                continue
            for d in dados:
                api[d["tipoDespesa"]][0] += 1
                api[d["tipoDespesa"]][1] += Decimal(str(d["valorDocumento"]))
                total_api += 1
                if d["valorLiquido"] and abs(Decimal(str(d["valorLiquido"])) + Decimal(str(d["valorDocumento"]))) < Decimal("0.005") and d["valorDocumento"]:
                    sinal_trocado += 1
        arq: defaultdict[str, list[Any]] = defaultdict(lambda: [0, Decimal("0")])
        for r in con.execute("SELECT categoria_original c, json_extract(extra,'$.valor_documento') v FROM despesas WHERE fonte='camara_deputados' AND ref_parlamentar=? AND ano=?", (dep, ano)):
            arq[r["c"]][0] += 1
            arq[r["c"]][1] += Decimal(r["v"] or "0")
        for cat in sorted(set(api) | set(arq)):
            a, f = api.get(cat, [0, Decimal(0)]), arq.get(cat, [0, Decimal(0)])
            ok = a[0] == f[0] and a[1] == f[1]
            rv.conferencia("camara_deputados", "api_x_arquivo", f"{dep}/{ano}/{cat}", f"API: {a[0]} linhas, R$ {a[1]}",
                           f"arquivo: {f[0]} linhas, R$ {f[1]}", "confere" if ok else "diverge")
            if not ok:
                divergentes.add((cat, ano))
    if total_api:
        rv.conferencia("camara_deputados", "sinal_valor_liquido_api", "amostra", f"{total_api} linhas da API",
                       f"{sinal_trocado} com valorLiquido = −valorDocumento", "observacao",
                       "a API devolve o valor líquido com o sinal trocado; a carga usa o arquivo anual e a conferência usa valorDocumento")
    for cat, ano in sorted(divergentes):
        rv.revisao("camara_deputados", "api_x_arquivo", f"{cat}/{ano}",
                   f"'{cat}' em {ano}: o arquivo anual e a API trazem quantidades diferentes para os mesmos deputados da amostra; "
                   "as linhas dessa categoria e ano ficam fora até a divergência ser explicada")
    return divergentes


def situacoes(con: sqlite3.Connection, rv: Revisor) -> None:
    ids = {(r[0], r[1]): r[2] for r in con.execute("SELECT fonte, ref, parlamentar_id FROM parlamentar_ids")}
    divergentes = _divergencias_api(con, rv)
    legado = _regras_legado(con, rv)
    # portal da Prefeitura: anos em que os dois caminhos de consulta não bateram
    prefeitura_divergente: set[int] = set()
    for r in con.execute("""SELECT escopo, texto_original FROM totais_oficiais
                            WHERE fonte='cmc_prefeitura' AND metrica='ano_inteiro_x_mes_a_mes' AND valor='diverge'"""):
        ano = int(r["escopo"].split("-")[1])
        prefeitura_divergente.add(ano)
        rv.revisao("cmc_prefeitura", "consulta", r["escopo"],
                   f"{ano}: a consulta do ano inteiro e a mês a mês trazem conjuntos diferentes ({r['texto_original']})")
    for r in con.execute("""SELECT escopo, valor, texto_original FROM totais_oficiais
                            WHERE fonte='cmc_prefeitura' AND metrica='ano_inteiro_x_mes_a_mes'"""):
        rv.conferencia("cmc_prefeitura", "ano_inteiro_x_mes_a_mes", r["escopo"], "o mesmo conjunto de linhas", r["texto_original"],
                       "confere" if r["valor"] == "confere" else "diverge",
                       "dois caminhos independentes de consulta no portal, que não publica total")
    prefeitura_fixo = frozenset(prefeitura_divergente)
    lote = []
    cur = con.execute("""SELECT chave, fonte, tipo, ref_parlamentar, beneficiario_tipo, cargo_original, categoria_original,
                                valor, ano, competencia, fornecedor_nome, extra FROM despesas""")
    while True:
        linhas = cur.fetchmany(20000)
        if not linhas:
            break
        for d in linhas:
            lote.append(_situacao(d, ids, divergentes, legado, rv, prefeitura_fixo))
        con.executemany("INSERT OR REPLACE INTO despesa_situacao(chave, situacao, motivo, parlamentar_id, categoria) VALUES(?,?,?,?,?)", lote)
        lote.clear()


def _situacao(d, ids, divergentes, legado, rv: Revisor, prefeitura_divergente: frozenset = frozenset()):
    fonte = d["fonte"]
    extra = json.loads(d["extra"] or "{}")
    valor = Decimal(d["valor"])
    cat = de_para.categoria(fonte, d["categoria_original"])
    pid = ids.get((fonte, d["ref_parlamentar"])) if d["ref_parlamentar"] else None
    motivos: list[str] = []
    situacao = OK
    por_linha = False  # há motivo próprio desta linha (não só o do escopo, que já tem item na revisão)

    detalhes: dict = {}

    def rev(m: str, escopo: bool = False, **det):
        nonlocal situacao, por_linha
        motivos.append(m)
        detalhes.update(det)
        situacao = REVISAO
        por_linha = por_linha or not escopo

    if cat is None:
        rev("categoria sem de-para", categoria_original=d["categoria_original"])
    if d["beneficiario_tipo"] == "parlamentar" and pid is None:
        rev("parlamentar sem identidade resolvida")

    if d["tipo"] == "cota_federal":
        if not (d["fornecedor_nome"] or "").strip():
            rev("despesa sem fornecedor")
        if valor < 0:
            vdoc = Decimal(extra.get("valor_documento") or "0")
            regra = de_para.regra_negativo(fonte, cat[0]) if cat else None
            if regra and vdoc < 0:
                motivos.append("compensação de bilhete (valor e documento negativos)")
            else:
                rev("valor líquido negativo com o documento maior que zero: a fonte não explica o sinal", valor_liquido=str(valor), valor_documento=str(vdoc))
        if extra.get("ano_arquivo") and int(extra["ano_arquivo"]) != int(d["ano"]):
            rev("linha de outro ano dentro do arquivo anual", ano_linha=d["ano"], ano_arquivo=extra["ano_arquivo"])
        if (d["categoria_original"], int(d["ano"])) in divergentes:
            rev("arquivo anual e API divergem nesta categoria e ano (ver conferência)", escopo=True)
    else:
        papel = de_para.cargo(fonte, d["cargo_original"])
        if papel is None:
            rev("cargo sem de-para", cargo_original=d["cargo_original"])
        elif papel == "vereador" and d["beneficiario_tipo"] != "parlamentar":
            rev("cargo de vereador escrito de um jeito que a guarda de privacidade não reconhece; o nome foi descartado na leitura", cargo_original=d["cargo_original"])
        elif papel == "servidor" and d["beneficiario_tipo"] == "parlamentar":
            rev("cargo de servidor com nome gravado")
        marcas = extra.get("marcas") or []
        if fonte == "cmc_legado":
            decisao = legado.get(d["chave"])
            if decisao:
                s, m = decisao
                if s == REVISAO:
                    rev(m, escopo=m.startswith("o total do mês"))
                elif situacao == OK:
                    situacao = s
                    motivos.append(m)
        elif fonte == "cmc_elotech":
            sem_diaria = valor == 0 and extra.get("quantidade") in (0, None)
            if "cancelada" in marcas:
                if Decimal(extra.get("valor_anulado") or "0") == Decimal(extra.get("valor_empenho") or "-1") and situacao == OK:
                    situacao = FORA_DA_SOMA
                    motivos.append("cancelada totalmente na fonte (anulado = empenhado)")
                elif not sem_diaria:
                    rev("cancelada na fonte, mas o valor anulado não é igual ao empenhado")
            elif not str(extra.get("consistencia", "ok")).startswith("ok") and not sem_diaria:
                rev("a linha não fecha (empenhado − anulado ≠ diárias)", consistencia=extra.get("consistencia"))
            if sem_diaria:
                motivos.append("viagem sem diária (só passagem)")
        elif fonte == "cmc_prefeitura":
            if int(d["ano"]) in prefeitura_divergente:
                rev("a consulta do ano inteiro e a consulta mês a mês do portal trazem conjuntos diferentes; sem total publicado, "
                    "não dá para saber qual está completo", escopo=True)
            if int(d["ano"]) >= 2026 and situacao == OK:
                situacao = CRUZADA
                motivos.append("2026 é do Betha; a linha da Prefeitura serve para conferir a fronteira")
            if extra.get("devolvido") and Decimal(extra["devolvido"]) > 0:
                motivos.append(f"devolvido R$ {extra['devolvido']}")
        elif fonte == "cmc_betha":
            motivos.append("valor previsto da diária (como a fonte rotula)")
    if situacao == REVISAO and por_linha:
        rv.revisao(fonte, "despesa", d["chave"], "; ".join(m for m in motivos if m), {"ano": d["ano"], "cargo": d["cargo_original"],
                   "categoria": d["categoria_original"], "valor": d["valor"], **detalhes})
    return (d["chave"], situacao, "; ".join(motivos) or None, pid, cat[0] if cat else None)


def _regras_legado(con, rv: Revisor) -> dict[str, tuple[str, str]]:
    """Totais por mês e por ano do PDF contra a soma das linhas. Devolve chave -> (situação, motivo)."""
    decisoes: dict[str, tuple[str, str]] = {}
    linhas = con.execute("""SELECT chave, ano, competencia, valor, extra FROM despesas WHERE fonte='cmc_legado'""").fetchall()
    totais = {(r["escopo"], r["metrica"]): Decimal(r["valor"]) for r in con.execute(
        "SELECT escopo, metrica, valor FROM totais_oficiais WHERE fonte='cmc_legado' AND metrica LIKE 'valor_%'")}
    por_mes = defaultdict(list)
    por_ano = defaultdict(list)
    for l in linhas:
        e = json.loads(l["extra"] or "{}")
        item = {"chave": l["chave"], "valor": Decimal(l["valor"]), "e": e,
                "hosp": Decimal(e["hospedagem"]) if e.get("hospedagem") else Decimal(0),
                "transp": Decimal(e["transporte"]) if e.get("transporte") else Decimal(0)}
        por_ano[int(l["ano"])].append(item)
        if e.get("competencia_do_bloco"):
            por_mes[l["competencia"]].append(item)
    metricas = (("valor_diarias", "valor"), ("valor_hospedagem", "hosp"), ("valor_transporte", "transp"))

    def soma(itens, campo, excluir=False):
        return sum((i[campo] for i in itens if not (excluir and i["e"].get("marcas"))), Decimal(0))

    confirmado_mes: set[str] = set()
    for mes, itens in sorted(por_mes.items()):
        oficiais = {m: totais.get((mes, m)) for m, _ in metricas}
        if not any(v is not None for v in oficiais.values()):
            continue
        tudo = all(oficiais[m] is None or soma(itens, c) == oficiais[m] for m, c in metricas)
        sem_marcadas = all(oficiais[m] is None or soma(itens, "valor" if c == "valor" else c, excluir=(c == "valor")) == oficiais[m]
                           for m, c in metricas)
        for m, c in metricas:
            if oficiais[m] is not None:
                obtido = soma(itens, c)
                rv.conferencia("cmc_legado", f"total_mensal_{m.removeprefix('valor_')}", mes, oficiais[m], obtido,
                               "confere" if obtido == oficiais[m] else ("confere_sem_marcadas" if c == "valor" and sem_marcadas else "diverge"))
        if tudo or sem_marcadas:
            confirmado_mes.add(mes)
            for i in itens:
                if i["e"].get("marcas") and sem_marcadas and not tudo:
                    decisoes[i["chave"]] = (FORA_DA_SOMA, f"{', '.join(i['e']['marcas'])} na fonte; o total do mês da própria fonte não a soma")
                elif str(i["e"].get("consistencia") or "").startswith("diverge"):
                    decisoes[i["chave"]] = (REVISAO, "a linha não fecha (quantidade × unitário ≠ total), embora o total do mês confira")
        else:
            rv.revisao("cmc_legado", "total", mes, f"o total do mês {mes} no PDF não fecha com a soma das linhas")
            for i in itens:
                decisoes[i["chave"]] = (REVISAO, f"o total do mês {mes} não fecha")
    for ano, itens in sorted(por_ano.items()):
        for m, c in metricas:
            oficial = totais.get((str(ano), m))
            if oficial is None:
                continue
            fora = {k for k, (s, _) in decisoes.items() if s == FORA_DA_SOMA}
            obtido = sum((i[c] for i in itens if not (c == "valor" and i["chave"] in fora)), Decimal(0))
            rv.conferencia("cmc_legado", f"total_anual_{m.removeprefix('valor_')}", str(ano), oficial, obtido,
                           "confere" if obtido == oficial else "diverge")
        tem_total = any((str(ano), m) in totais for m, _ in metricas)
        for i in itens:
            if i["chave"] in decisoes:
                continue
            cons = str(i["e"].get("consistencia") or "")
            if cons.startswith("diverge"):
                decisoes[i["chave"]] = (REVISAO, "a linha não fecha (quantidade × unitário ≠ total)")
            elif not tem_total and i["e"].get("marcas"):
                decisoes[i["chave"]] = (REVISAO, "cancelada ou devolvida na fonte, e o relatório do ano não tem total para confirmar se entra na soma")
            elif not tem_total and cons.startswith("nao_verificavel"):
                decisoes[i["chave"]] = (REVISAO, "quantidade × unitário não verificável e o relatório do ano não tem total")
        if not tem_total:
            rv.conferencia("cmc_legado", "total_anual_diarias", str(ano), None, sum((i["valor"] for i in itens), Decimal(0)),
                           "sem_total_na_fonte", "o relatório deste ano não traz total; a conferência é só a de cada linha")
    return decisoes


# ---------------------------------------------------------------------------
# Fronteiras, gabinetes, contagens e a equação de cada fonte
# ---------------------------------------------------------------------------

def fronteira_2026(con, rv: Revisor) -> None:
    """Prefeitura × Betha em 2026: o mesmo registro em dois sistemas.

    O par é pela pessoa (ou, para servidor, pelo cargo) e pela data de início; o
    valor é comparado depois, porque o Betha publica o valor previsto na concessão
    e a Prefeitura o valor empenhado.
    """
    def chave(r):
        return (r["data"], r["parlamentar_id"] or f"servidor:{normalizar_nome(r['cargo_original'])}")
    betha = defaultdict(list)
    for r in con.execute("""SELECT d.chave, d.data, d.valor, d.cargo_original, s.parlamentar_id FROM despesas d
                            JOIN despesa_situacao s USING(chave) WHERE d.fonte='cmc_betha' AND d.ano=2026"""):
        betha[chave(r)].append(r)
    pares = valor_igual = sem_par = sem_par_ver = 0
    for r in con.execute("""SELECT d.chave, d.data, d.valor, d.cargo_original, d.beneficiario_tipo, s.parlamentar_id FROM despesas d
                            JOIN despesa_situacao s USING(chave) WHERE d.fonte='cmc_prefeitura' AND d.ano>=2026"""):
        candidatos = betha.get(chave(r), [])
        if candidatos:
            igual = next((c for c in candidatos if Decimal(c["valor"]) == Decimal(r["valor"])), None)
            escolhido = igual or candidatos[0]
            candidatos.remove(escolhido)
            pares += 1
            valor_igual += igual is not None
            if igual is None and r["beneficiario_tipo"] == "parlamentar":
                rv.revisao("cmc_prefeitura", "fronteira", r["chave"], "diária de vereador de 2026 com valor diferente nos dois sistemas",
                           {"prefeitura": r["valor"], "betha": escolhido["valor"], "data": r["data"]})
        else:
            sem_par += 1
            if r["beneficiario_tipo"] == "parlamentar":
                sem_par_ver += 1
                rv.revisao("cmc_prefeitura", "fronteira", r["chave"], "diária de vereador de 2026 na Prefeitura sem par no Betha",
                           {"data": r["data"], "valor": r["valor"]})
    restantes = sum(len(v) for v in betha.values())
    rv.conferencia("cmc_prefeitura", "fronteira_betha_2026", "2026", "mesma diária nos dois sistemas",
                   f"{pares} com par (valor igual em {valor_igual}); {sem_par} só na Prefeitura ({sem_par_ver} de vereador); {restantes} só no Betha",
                   "confere" if sem_par == 0 and pares == valor_igual else "parcial",
                   "par por pessoa (ou cargo, para servidor) e data de início; o Betha mostra o valor previsto e a Prefeitura o empenhado")
    f = con.execute("SELECT valor FROM totais_oficiais WHERE fonte='cmc_prefeitura' AND escopo LIKE 'fronteira-%'").fetchone()
    if f is not None:
        rv.conferencia("cmc_prefeitura", "fronteira_elotech", "2023", 0, f[0], "confere" if f[0] == "0" else "diverge",
                       "o ano anterior a 2024 tem de vir vazio na Prefeitura (é do Elotech)")


def gabinetes(con, rv: Revisor) -> None:
    b = {r["ref_parlamentar"]: r for r in con.execute("SELECT * FROM gabinetes WHERE fonte='cmc_betha'")}
    e = {r["ref_parlamentar"]: r for r in con.execute("SELECT * FROM gabinetes WHERE fonte='cmc_elotech'")}
    iguais = 0
    for ref in sorted(set(b) | set(e)):
        rb, re_ = b.get(ref), e.get(ref)
        if rb is None or re_ is None:
            rv.revisao("cmc_betha", "gabinete", ref, "gabinete em só um dos dois sistemas de pessoal")
            continue
        if rb["pessoas"] != re_["pessoas"]:
            rv.revisao("cmc_betha", "gabinete", ref,
                       f"Betha conta {rb['pessoas']} pessoas no gabinete e o Elotech, {re_['pessoas']}")
        else:
            iguais += 1
    rv.conferencia("cmc_betha", "gabinetes_betha_x_elotech", "pessoas por gabinete", len(set(b) | set(e)), iguais,
                   "confere" if iguais == len(set(b) | set(e)) else "parcial",
                   "a quantidade de pessoas tem de bater; os valores medem coisas diferentes (remuneração contratual no Betha, remuneração no Elotech) e são publicados cada um com o seu rótulo")


def equacoes(con, rv: Revisor) -> None:
    """Para cada fonte: origem = coletado + revisão, e nenhum erro em aberto."""
    def n(sql, *a):
        return con.execute(sql, a).fetchone()[0] or 0

    def origem(fonte: str) -> tuple[int | None, str]:
        if fonte == "camara_deputados":
            return int(n("SELECT SUM(CAST(valor AS INTEGER)) FROM totais_oficiais WHERE fonte=? AND metrica='linhas_no_arquivo'", fonte)), "linhas da legislatura nos arquivos anuais"
        if fonte == "cmc_elotech":
            return int(n("SELECT SUM(CAST(valor AS INTEGER)) FROM totais_oficiais WHERE fonte=? AND metrica='registros' AND escopo LIKE 'diarias-%'", fonte)), "totalElements da API de diárias"
        if fonte == "cmc_betha":
            return int(n("SELECT SUM(CAST(valor AS INTEGER)) FROM totais_oficiais WHERE fonte=? AND metrica='registros' AND escopo LIKE 'diarias-%'", fonte)), "contador 'Registros encontrados' da tela"
        if fonte == "cmc_legado":
            return int(n("SELECT SUM(CAST(valor AS INTEGER)) FROM totais_oficiais WHERE fonte=? AND metrica='linhas_lidas'", fonte)), "linhas de diária nas tabelas dos PDFs"
        if fonte == "cmc_prefeitura":
            return int(n("SELECT SUM(CAST(valor AS INTEGER)) FROM totais_oficiais WHERE fonte=? AND metrica='registros_lidos'", fonte)), "linhas lidas mês a mês (a fonte não publica contagem)"
        return None, ""

    for fonte in [r[0] for r in con.execute("SELECT DISTINCT fonte FROM inventario")]:
        erros = n("SELECT COUNT(*) FROM inventario WHERE fonte=? AND situacao='erro'", fonte)
        pend = n("SELECT COUNT(*) FROM inventario WHERE fonte=? AND situacao='pendente'", fonte)
        rv.conferencia(fonte, "erros_em_aberto", "inventário", 0, erros + pend, "confere" if erros + pend == 0 else "diverge",
                       f"{erros} item(ns) com erro, {pend} pendente(s)")
        o, base = origem(fonte)
        if o is None:
            continue
        coletado = n("""SELECT COUNT(*) FROM despesas d JOIN despesa_situacao s USING(chave)
                        WHERE d.fonte=? AND s.situacao IN ('ok','fora_da_soma','conferencia_cruzada')""", fonte)
        em_rev = n("SELECT COUNT(*) FROM despesas d JOIN despesa_situacao s USING(chave) WHERE d.fonte=? AND s.situacao='revisao'", fonte)
        pend_l = n("SELECT COUNT(*) FROM pendencias WHERE fonte=?", fonte)
        soma = coletado + em_rev + pend_l
        rv.conferencia(fonte, "origem_igual_coletado_mais_revisao", "todas as linhas", o, soma,
                       "confere" if soma == o else "diverge",
                       f"origem ({base}) = {o}; coletado = {coletado}; revisão = {em_rev + pend_l}")


def pendencias(con, rv: Revisor) -> None:
    for r in con.execute("SELECT * FROM pendencias"):
        rv.revisao(r["fonte"], "leitura", r["chave"], r["motivo"], {"texto_original": r["texto_original"], "local": r["localizador"]})


def contagens(con, rv: Revisor) -> None:
    lista = con.execute("SELECT valor FROM totais_oficiais WHERE fonte='camara_deputados' AND metrica='parlamentares'").fetchone()
    if lista:
        com_despesa = con.execute("SELECT COUNT(DISTINCT ref_parlamentar) FROM despesas WHERE fonte='camara_deputados' AND ref_parlamentar IS NOT NULL").fetchone()[0]
        fora = con.execute("""SELECT COUNT(DISTINCT ref_parlamentar) FROM despesas WHERE fonte='camara_deputados' AND ref_parlamentar IS NOT NULL
                              AND ref_parlamentar NOT IN (SELECT ref FROM pessoas_fonte WHERE fonte='camara_deputados')""").fetchone()[0]
        rv.conferencia("camara_deputados", "parlamentares_x_lista_oficial", "legislatura 57", lista[0],
                       f"{com_despesa} com despesa; {fora} fora da lista", "confere" if fora == 0 else "diverge",
                       "todo deputado com despesa tem de estar na lista da legislatura; quem não gastou não aparece no arquivo")
    for r in con.execute("SELECT escopo, valor FROM totais_oficiais WHERE fonte='tse' AND metrica='eleitos'"):
        rv.conferencia("tse", "eleitos", r["escopo"], None, r["valor"], "observacao", "vereadores eleitos em Curitiba no arquivo do TSE")
    v = con.execute("SELECT valor FROM totais_oficiais WHERE fonte='cmc_betha' AND escopo='vereadores' AND metrica='registros'").fetchone()
    if v:
        lidos = con.execute("SELECT COUNT(*) FROM pessoas_fonte WHERE fonte='cmc_betha' AND periodo='atual'").fetchone()[0]
        rv.conferencia("cmc_betha", "lista_de_vereadores", "atual", v[0], lidos, "confere" if str(lidos) == v[0] else "diverge")


LIMPAR = ["parlamentares", "parlamentar_ids", "filiacoes", "despesa_situacao", "revisao", "conferencias"]


def conferir(con: sqlite3.Connection) -> list[str]:
    with transacao(con):
        for t in LIMPAR:
            con.execute(f"DELETE FROM {t}")
        rv = Revisor(con)
        identidades(con, rv)
        situacoes(con, rv)
        fronteira_2026(con, rv)
        gabinetes(con, rv)
        pendencias(con, rv)
        contagens(con, rv)
        equacoes(con, rv)
    resumo = []
    for r in con.execute("""SELECT fonte, resultado, COUNT(*) n FROM conferencias GROUP BY 1, 2 ORDER BY 1, 2"""):
        resumo.append(f"  conferência {r['fonte']}: {r['n']} {r['resultado']}")
    for r in con.execute("SELECT fonte, tipo, COUNT(*) n FROM revisao GROUP BY 1, 2 ORDER BY 1, 2"):
        resumo.append(f"  revisão {r['fonte']}/{r['tipo']}: {r['n']}")
    for r in con.execute("SELECT fonte, esperado, obtido, resultado FROM conferencias WHERE verificacao='origem_igual_coletado_mais_revisao'"):
        resumo.append(f"  {r['fonte']}: origem {r['esperado']} = coletado + revisão {r['obtido']} → {r['resultado']}")
    return resumo
