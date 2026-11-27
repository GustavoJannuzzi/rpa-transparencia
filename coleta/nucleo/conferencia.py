"""Conferência: identidade, de-para, regras de cada fonte, totais oficiais e a
equação de cada fonte (origem = coletado + revisão).

Tudo aqui é refeito a cada rodada a partir do que a coleta gravou. O que não fecha
vai para a fila de revisão e não é publicado.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from decimal import Decimal
from itertools import pairwise
from typing import Any

from .. import de_para, entidades
from ..modelo import Casa
from . import atividade
from .banco import agora, js, transacao
from .texto import normalizar_nome, slug

ELEICOES_CMC = [2012, 2016, 2020, 2024]
ELEICOES_MUNICIPAIS = ELEICOES_CMC


def fontes_por_casa() -> dict[str, list[str]]:
    """Casa -> fontes de despesa e de pessoas dela (o TSE entra à parte, pelo município)."""
    from ..fontes import FONTES

    out: dict[str, list[str]] = defaultdict(list)
    for f in FONTES:
        if f.id != "tse" and f.dado == "despesa":
            out[f.sistema.casa].append(f.id)
    return dict(out)


def fontes_de_atividade() -> list[str]:
    """Fontes de atividade legislativa (sessão, presença, voto): ficam fora da identidade
    montada pelas fontes de despesa e se ligam a ela depois (`nucleo.atividade`)."""
    return list(atividade.fontes_de_atividade())


def eh_elotech(fonte: str) -> bool:
    return fonte == "cmc_elotech" or fonte.startswith("elotech_")


def eh_betha(fonte: str) -> bool:
    return fonte == "cmc_betha" or fonte.startswith("betha_")


def eh_equiplano(fonte: str) -> bool:
    return fonte.startswith("equiplano_")


def eh_pronim(fonte: str) -> bool:
    return fonte.startswith("pronim_")


def _pronim_divergente(con, rv: Revisor) -> frozenset[tuple[str, int]]:
    """Pronim: a tela não publica total. A conferência é por dois caminhos dela mesma:
    a consulta do ano inteiro e a soma das consultas mês a mês, credor a credor."""
    out = set()
    for r in con.execute("""SELECT fonte, escopo, valor, texto_original FROM totais_oficiais
                            WHERE fonte LIKE 'pronim_%' AND metrica='ano_inteiro_x_mes_a_mes'"""):
        # o detalhe vai para a página: valor solto, sem "R$" (todo R$ na plataforma tem ficha de procedência)
        detalhe = (r["texto_original"] or "").replace("R$ ", "")
        rv.conferencia(r["fonte"], "ano_inteiro_x_mes_a_mes", r["escopo"], "os mesmos credores e valores", detalhe,
                       "confere" if r["valor"] == "confere" else "diverge",
                       "dois caminhos independentes de consulta na tela, que não publica total")
        if r["valor"] != "confere":
            ano = int(r["escopo"].split("-")[1])
            out.add((r["fonte"], ano))
            rv.revisao(r["fonte"], "consulta", r["escopo"],
                       f"{ano}: a consulta do ano inteiro e a soma das consultas mês a mês não dão os mesmos credores e valores "
                       f"({detalhe})")
    return frozenset(out)


def _totais_do_relatorio(con, rv: Revisor) -> frozenset[tuple[str, int]]:
    """Equiplano: a soma dos empenhos líquidos de cada ano tem de dar o total que o
    próprio relatório imprime no rodapé. Devolve (fonte, ano) que não deram."""
    # a soma em Decimal, linha a linha, para comparar centavo a centavo
    exata: dict[tuple[str, int], Decimal] = defaultdict(Decimal)
    for r in con.execute("SELECT fonte, ano, valor FROM despesas WHERE fonte LIKE 'equiplano_%'"):
        exata[(r[0], int(r[1]))] += Decimal(r[2])
    pend = {(r[0], r[1]) for r in con.execute("SELECT fonte, item FROM pendencias WHERE fonte LIKE 'equiplano_%'")}
    divergentes = set()
    for r in con.execute("""SELECT fonte, escopo, valor, texto_original FROM totais_oficiais
                            WHERE fonte LIKE 'equiplano_%' AND metrica='total_liquido'"""):
        ano = int(r["escopo"].split("-")[1])
        obtido = exata.get((r["fonte"], ano), Decimal(0))
        esperado = Decimal(r["valor"])
        fecha = obtido == esperado and (r["fonte"], r["escopo"]) not in pend
        rv.conferencia(r["fonte"], "total_do_relatorio", r["escopo"], esperado, obtido, "confere" if fecha else "diverge",
                       "soma dos empenhos líquidos (empenhado − estornado) × o total que o relatório imprime no rodapé")
        if not fecha:
            divergentes.add((r["fonte"], ano))
            rv.revisao(r["fonte"], "consulta", r["escopo"],
                       f"{ano}: a soma dos empenhos lidos não dá o total que o relatório imprime no rodapé",
                       {"total_do_relatorio": str(esperado), "soma_lida": str(obtido)})
    return frozenset(divergentes)


# Fontes de câmara lidas pela tela, sem a tabela de cargos revisada à mão: nelas a
# conferência procura cargo do Executivo misturado na consulta da Câmara.
GRUPOS_TELA_MUNICIPAL = ("betha_",)
MOTIVO_EXECUTIVO = ("a consulta de diárias da Câmara traz cargos do Executivo municipal (Prefeitura), e a fonte não separa as "
                    "duas entidades; as diárias de servidor ficam fora da soma até alguém conferir")


def _consultas_com_executivo(con, rv: Revisor) -> frozenset[str]:
    """Fontes de câmara cuja consulta de diárias traz cargo do Executivo: a revisão ganha um item, com os cargos."""
    achados: dict[str, Counter] = defaultdict(Counter)
    for r in con.execute("""SELECT fonte, cargo_original, COUNT(*) FROM despesas
                            WHERE tipo='diaria_municipal' AND beneficiario_tipo='servidor' GROUP BY 1, 2"""):
        if r[0].startswith(GRUPOS_TELA_MUNICIPAL) and de_para.eh_cargo_do_executivo(r[1]):
            achados[r[0]][r[1]] += r[2]
    for fonte, cargos in achados.items():
        rv.revisao(fonte, "consulta", "consulta-inteira", MOTIVO_EXECUTIVO,
                   {"cargos_do_executivo": [f"{c} ({n})" for c, n in cargos.most_common(8)], "linhas": sum(cargos.values())})
    return frozenset(achados)


def prefixo_vereador(casa: Casa) -> str:
    return "ver-cwb-" if casa.id == "cmc" else f"ver-{casa.id.removeprefix('cm-')}-"

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
    por_casa = fontes_por_casa()
    for casa in entidades.casas().values():
        if casa.tipo == "camara_municipal" and por_casa.get(casa.id):
            _vereadores(con, rv, casa, por_casa[casa.id])
        elif casa.tipo == "assembleia" and por_casa.get(casa.id):
            _estaduais(con, rv, casa, por_casa[casa.id])


def _estaduais(con, rv: Revisor, casa: Casa, fontes: list[str]) -> None:
    """Deputado estadual: a identidade é a da própria fonte (id da ALMG, matrícula da
    ALESP; na CLDF, o nome, com as grafias já ligadas na leitura pelo CPF, que não é
    gravado)."""
    uf = casa.uf.lower()
    for fonte in fontes:
        pessoas: dict[str, list] = defaultdict(list)
        for r in con.execute("SELECT ref, periodo, nome, nome_parlamentar, partido, extra FROM pessoas_fonte WHERE fonte=? ORDER BY periodo",
                             (fonte,)):
            pessoas[r["ref"]].append(r)
        refs = {r[0] for r in con.execute("SELECT DISTINCT ref_parlamentar FROM despesas WHERE fonte=? AND ref_parlamentar IS NOT NULL", (fonte,))}
        parecidos = _nomes_parecidos(con, fonte, set(pessoas) | refs)
        for ref in sorted(set(pessoas) | refs):
            regs = pessoas.get(ref)
            if not regs:
                rv.revisao(fonte, "identidade", ref, "deputado nas despesas mas fora da lista de deputados da fonte")
                continue
            if ref in parecidos:
                rv.revisao(fonte, "identidade", ref,
                           f"o nome é quase igual ao de outro deputado da mesma casa ({parecidos[ref]}); sem uma linha na tabela de grafias, "
                           "não dá para saber se é a mesma pessoa escrita errado")
                continue
            tipo, _, valor = ref.partition(":")
            pid = f"est-{uf}-{valor if tipo in ('id', 'mat') else slug(valor)}"
            ult = regs[-1]
            nome = ult["nome_parlamentar"] or ult["nome"]
            civil = ult["nome"] if ult["nome_parlamentar"] and ult["nome"] != ult["nome_parlamentar"] else None
            partido = ult["partido"]
            extra = json.loads(ult["extra"] or "{}")
            con.execute("INSERT OR REPLACE INTO parlamentares(id, nome, nome_civil, casa, uf, municipio, partido_atual, extra) VALUES(?,?,?,?,?,?,?,?)",
                        (pid, nome, civil, casa.id, casa.uf, None, partido,
                         js({"ref_fonte": ref, "grafias_na_fonte": extra.get("grafias_na_fonte")})))
            con.execute("INSERT OR REPLACE INTO parlamentar_ids(fonte, ref, parlamentar_id, metodo) VALUES(?,?,?,?)",
                        (fonte, ref, pid, {"id": "id da API", "mat": "matrícula na fonte"}.get(tipo, "nome (grafias ligadas na leitura)")))
            if partido:
                con.execute("INSERT INTO filiacoes(parlamentar_id, partido, desde, ate, fonte, base) VALUES(?,?,?,?,?,?)",
                            (pid, partido, None, None, fonte, extra.get("partido_de") or "partido informado pela fonte"))


def _distancia(a: str, b: str) -> int:
    """Levenshtein (nomes curtos)."""
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        atual = [i]
        for j, cb in enumerate(b, 1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (ca != cb)))
        anterior = atual
    return anterior[-1]


def _nomes_parecidos(con, fonte: str, refs: set[str]) -> dict[str, str]:
    """Fonte que identifica o deputado pelo nome escrito (ref 'nome:'): dois nomes a
    até 2 letras um do outro, com o mesmo primeiro nome, são suspeitos de ser a mesma
    pessoa com erro de digitação. Devolve o de menos notas -> o outro. A tabela de
    grafias (de_para/grafias.csv) resolve os confirmados já na leitura."""
    por_nome = [r for r in refs if r.startswith("nome:")]
    if fonte not in CONFERENCIA_DA_TELA or len(por_nome) < 2:
        return {}
    notas = dict(con.execute("SELECT ref_parlamentar, COUNT(*) FROM despesas WHERE fonte=? GROUP BY 1", (fonte,)).fetchall())
    norm = {r: normalizar_nome(r[5:]) for r in por_nome}
    out: dict[str, str] = {}
    for a, b in ((a, b) for i, a in enumerate(sorted(por_nome)) for b in sorted(por_nome)[i + 1:]):
        na, nb = norm[a], norm[b]
        if na.split()[:1] != nb.split()[:1] or abs(len(na) - len(nb)) > 2 or _distancia(na, nb) > 2:
            continue
        menor, maior = sorted((a, b), key=lambda r: (notas.get(r, 0), r))
        out[menor] = maior[5:]
    return out


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


def _nome_parlamentar(registros: list[tuple[str, str]]) -> str | None:
    """O nome parlamentar que a Câmara usa hoje, entre os (período, nome) que o
    cadastro de pessoal dela publica para o gabinete da pessoa.

    Regra: vale o do período mais recente ("atual" conta como o mais recente de
    todos), porque a Câmara pode mudar o nome com o tempo ("PIER" no gabinete de
    2017 a 2019, "PIER PETRUZZIELLO" de 2019 em diante: fica o de agora). No empate,
    o mais completo (mais palavras, depois mais letras) e, por fim, a ordem
    alfabética. A escolha só depende dos dados, nunca da ordem em que eles chegam.
    """
    def chave(registro: tuple[str, str]) -> tuple:
        periodo, nome = registro
        recencia = 10_000 if periodo == "atual" else (int(periodo) if periodo.isdigit() else 0)
        return (-recencia, -len(nome.split()), -len(nome), nome)
    return min(registros, key=chave)[1] if registros else None


def _vereadores(con, rv: Revisor, casa: Casa, fontes: list[str]) -> None:
    """Pessoa = componente ligado de matrículas e nomes que aparecem juntos, dentro
    de uma câmara (a mesma matrícula em duas câmaras é de pessoas diferentes).

    A matrícula muda de um mandato para outro (a mesma pessoa tem 1127 e 1184),
    então ela não é a identidade: é um elo entre nomes. Os relatórios de 2013–2014
    trazem o nome curto, que é o nome de urna do TSE; a candidatura liga o nome de
    urna ao nome civil.

    O nome exibido, em ordem de preferência: (1) o nome parlamentar que a própria
    Câmara usa no gabinete, pela regra de `_nome_parlamentar`; (2) o nome de urna do
    TSE na eleição mais recente em que o partido se resolve; (3) o nome civil.
    Nenhum passo depende da ordem de um set: a mesma entrada dá o mesmo nome em
    qualquer rodada.
    """
    u = _Uniao()
    # nome civil normalizado -> (período, nome parlamentar) de cada gabinete com esse nome
    apelidos: dict[str, list[tuple[str, str]]] = defaultdict(list)
    so_apelido: set[str] = set()  # nomes que só aparecem como nome parlamentar ou de urna
    def token_ref(ref: str) -> str:
        tipo, _, valor = ref.partition(":")
        return ("m:" if tipo == "mat" else "n:") + (valor if tipo == "mat" else normalizar_nome(valor))

    marcas = ",".join("?" * len(fontes))
    municipio = normalizar_nome(casa.municipio)
    ativ = fontes_de_atividade()
    sem_ativ = f"AND fonte NOT IN ({','.join('?' * len(ativ))})" if ativ else ""
    for r in con.execute(f"SELECT fonte, ref, periodo, nome, nome_parlamentar, matricula FROM pessoas_fonte WHERE casa=? {sem_ativ}",
                         (casa.id, *ativ)):
        toks = [] if r["ref"].startswith("gab:") else [token_ref(r["ref"])]
        if r["nome"]:
            toks.append("n:" + normalizar_nome(r["nome"]))
        if r["matricula"]:
            toks.append("m:" + r["matricula"])
        if r["ref"].startswith("gab:") and r["nome_parlamentar"]:
            toks.append("n:" + normalizar_nome(r["nome_parlamentar"]))
            so_apelido.add(normalizar_nome(r["nome_parlamentar"]))
            apelidos[normalizar_nome(r["nome"])].append((r["periodo"], r["nome_parlamentar"]))
        for a, b in pairwise(toks):
            u.unir(a, b)
        for t in toks:
            u.achar(t)
    refs = {(r[0], r[1]) for r in con.execute(
        f"SELECT DISTINCT fonte, ref_parlamentar FROM despesas WHERE fonte IN ({marcas}) AND ref_parlamentar IS NOT NULL", fontes)}
    refs |= {(r[0], r[1]) for r in con.execute(f"SELECT DISTINCT fonte, ref FROM pessoas_fonte WHERE casa=? AND ref NOT LIKE 'gab:%' {sem_ativ}",
                                               (casa.id, *ativ))}

    # em ordem: a ordem de entrada na união decide a ordem dos componentes
    for _, ref in sorted(refs):
        u.achar(token_ref(ref))

    # Liga nome civil e nome de urna da mesma candidatura, só para quem aparece nas fontes da Câmara
    cands = defaultdict(list)
    for r in con.execute("SELECT ano_eleicao, nome_norm, nome_urna, partido, situacao FROM candidaturas WHERE municipio=?", (municipio,)):
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
        pid = f"{prefixo_vereador(casa)}{slug(canon)}"
        for t in grupo:
            pid_de[t] = pid
        info[pid] = {"canon": canon, "nomes": set(nomes), "anos": set(), "suspeito": suspeito,
                     "matriculas": sorted(t[2:] for t in grupo if t.startswith("m:"))}
        if suspeito:
            rv.revisao(casa.id, "identidade", pid, "nomes diferentes ligados à mesma pessoa pelas matrículas",
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
    for (ref,) in con.execute(f"SELECT DISTINCT ref_parlamentar FROM gabinetes WHERE ref_parlamentar IS NOT NULL AND fonte IN ({marcas})", fontes):
        dono = pid_de.get("n:" + normalizar_nome(ref[4:]))
        if dono and not info[dono]["suspeito"]:
            con.execute("INSERT OR REPLACE INTO parlamentar_ids(fonte, ref, parlamentar_id, metodo) VALUES(?,?,?,?)",
                        (f"gabinete:{casa.id}", ref, dono, "lotação do gabinete"))
        else:
            rv.revisao(casa.id, "identidade", ref, "gabinete sem vereador identificado", {"lotacao": ref})

    for r in con.execute(f"""SELECT pi.parlamentar_id pid, d.ano FROM despesas d JOIN parlamentar_ids pi
                             ON pi.fonte=d.fonte AND pi.ref=d.ref_parlamentar WHERE d.fonte IN ({marcas}) GROUP BY 1, 2""", fontes):
        info[r["pid"]]["anos"].add(int(r["ano"]))
    for r in con.execute("""SELECT pi.parlamentar_id pid, p.periodo FROM pessoas_fonte p JOIN parlamentar_ids pi
                            ON pi.fonte=p.fonte AND pi.ref=p.ref WHERE p.casa=?""", (casa.id,)):
        if r["periodo"].isdigit():
            info[r["pid"]]["anos"].add(int(r["periodo"]))
        elif r["periodo"] == "atual":
            info[r["pid"]]["anos"].add(int(agora()[:4]))

    usados = sorted({r[0] for r in con.execute("SELECT DISTINCT parlamentar_id FROM parlamentar_ids WHERE parlamentar_id LIKE ?",
                                                (prefixo_vereador(casa) + "%",))})
    for pid in usados:
        i = info[pid]
        civil = _titulo(i["canon"])
        apelido = _nome_parlamentar([reg for n in sorted(i["nomes"]) for reg in apelidos.get(n, [])])
        eleicoes = sorted({max([e for e in ELEICOES_MUNICIPAIS if e < a] or [0]) for a in i["anos"]} - {0})
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
                           {"vereador": civil, "eleicao": e, "municipio": casa.municipio, "nomes_tentados": sorted(i["nomes"])})
        nome_exib = _titulo(apelido) if apelido else (_titulo(urna_exib) if urna_exib else civil)
        con.execute("INSERT INTO parlamentares(id, nome, nome_civil, casa, uf, municipio, partido_atual, extra) VALUES(?,?,?,?,?,?,?,?)",
                    (pid, nome_exib, civil, casa.id, casa.uf, casa.municipio, partido_atual,
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
    estaduais = _divergencias_estaduais(con, rv)
    mistas = _consultas_com_executivo(con, rv)
    relatorio_divergente = _totais_do_relatorio(con, rv) | _pronim_divergente(con, rv)
    lote = []
    cur = con.execute("""SELECT chave, fonte, tipo, ref_parlamentar, beneficiario_tipo, cargo_original, categoria_original,
                                valor, ano, competencia, fornecedor_nome, fornecedor_doc, granularidade, extra FROM despesas""")
    while True:
        linhas = cur.fetchmany(20000)
        if not linhas:
            break
        for d in linhas:
            lote.append(_situacao(d, ids, divergentes, legado, rv, prefeitura_fixo, estaduais, mistas, relatorio_divergente))
        con.executemany("INSERT OR REPLACE INTO despesa_situacao(chave, situacao, motivo, parlamentar_id, categoria) VALUES(?,?,?,?,?)", lote)
        lote.clear()


def _situacao(d, ids, divergentes, legado, rv: Revisor, prefeitura_divergente: frozenset = frozenset(),
              divergentes_estaduais: frozenset = frozenset(), consultas_mistas: frozenset = frozenset(),
              relatorio_divergente: frozenset = frozenset()):
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

    if d["tipo"] == "verba_estadual":
        if not (d["fornecedor_nome"] or "").strip() and not (d["fornecedor_doc"] or "").strip():
            rev("despesa sem fornecedor")
        if not (d["categoria_original"] or "").strip():
            motivos[:] = [m for m in motivos if m != "categoria sem de-para"]
            rev("a fonte não classifica a despesa (classificação vazia)")
        if valor < 0 and extra.get("anulacao_explicada"):
            motivos.append("anulação de empenho: a descrição da própria casa diz que anula outro empenho (entra na soma, como no total da casa)")
        elif valor < 0:
            rev("valor negativo: a fonte não explica o sinal", valor=str(valor))
        elif valor == 0 and situacao == OK:
            situacao = FORA_DA_SOMA
            motivos.append("valor reembolsado zero na fonte" if fonte == "almg" else "valor zero na fonte")
        if extra.get("fora_do_outro_arquivo"):
            rev(f"a nota está no arquivo principal do ano, mas não em '{extra['fora_do_outro_arquivo']}', que a fonte também publica para o mesmo ano")
        if (fonte, d["chave"]) in divergentes_estaduais:
            rev("a soma das notas não fecha com o total que a própria fonte dá para o tipo de despesa no mês", escopo=True)
        # agregado (ALESP) não ganha motivo por linha: a granularidade é coluna da despesa e vai no
        # cabeçalho do parlamentar; repetida em 82 mil linhas, pesaria ~6 MB no que vai para o ar
    elif d["tipo"] == "cota_federal":
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
        if extra.get("nota_cargo") and d["beneficiario_tipo"] == "parlamentar":
            # cargo vazio na fonte, nome igual ao de um vereador no cadastro de pessoal do mesmo ano
            papel = "vereador"
            motivos.append("cargo vazio na fonte; vereador pelo cadastro de pessoal da Câmara")
        if papel is None and not (d["cargo_original"] or "").strip():
            rev("a fonte não informa o cargo, e o nome não está no cadastro de vereadores da Câmara no mesmo ano; o nome foi descartado na leitura"
                if eh_elotech(fonte) else "a fonte não informa o cargo; o nome foi descartado na leitura")
        elif papel is None:
            rev("cargo sem de-para", cargo_original=d["cargo_original"])
        elif papel == "vereador" and d["beneficiario_tipo"] != "parlamentar" and not extra.get("nota_cargo"):
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
        elif eh_elotech(fonte):
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
        elif eh_betha(fonte):
            motivos.append("valor previsto da diária (como a fonte rotula)")
        elif eh_pronim(fonte):
            if (fonte, int(d["ano"])) in relatorio_divergente:
                rev("a consulta do ano inteiro e a soma das consultas mês a mês não batem; sem total publicado, não dá para "
                    "saber qual está completa", escopo=True)
            for nota in extra.get("notas_identidade") or []:
                rev(nota + "; o nome foi descartado na leitura")
            if extra.get("anulado_inteiro") and valor == 0 and situacao == OK:
                situacao = FORA_DA_SOMA
                motivos.append("anulado inteiro na fonte (anulado = empenhado)")
            motivos.append("soma das diárias do credor no mês, como a tela mostra")
        elif eh_equiplano(fonte):
            if (fonte, int(d["ano"])) in relatorio_divergente:
                rev("a soma dos empenhos do ano não dá o total que o relatório imprime", escopo=True)
            if extra.get("nota_cargo"):
                rev("a natureza da despesa e o cargo escrito na descrição do empenho não batem; o nome foi descartado na leitura",
                    nota=extra["nota_cargo"])
            if not str(extra.get("consistencia", "ok")).startswith("ok"):
                rev("o empenho não fecha (itens ou valor total das diárias ≠ empenhado)", consistencia=extra.get("consistencia"))
            elif "cancelada" in marcas and valor == 0 and situacao == OK:
                situacao = FORA_DA_SOMA
                motivos.append("empenho estornado inteiro na fonte (estorno = empenhado)")
            elif "cancelada_parcialmente" in marcas:
                motivos.append(f"estorno parcial na fonte: empenhado R$ {extra.get('valor_empenho')}, estornado R$ {extra.get('valor_anulado')}")
        if fonte in consultas_mistas and d["beneficiario_tipo"] == "servidor":
            rev(MOTIVO_EXECUTIVO, escopo=True)
    if situacao == REVISAO and por_linha:
        rv.revisao(fonte, "despesa", d["chave"], "; ".join(m for m in motivos if m), {"ano": d["ano"], "cargo": d["cargo_original"],
                   "categoria": d["categoria_original"], "valor": d["valor"], **detalhes})
    return (d["chave"], situacao, "; ".join(motivos) or None, pid, cat[0] if cat else None)


def _divergencias_estaduais(con, rv: Revisor) -> frozenset[tuple[str, str]]:
    """Conferências das assembleias contra o que a própria fonte diz de si. Devolve
    (fonte, chave) das notas que ficam em revisão por causa de um recorte."""
    fora: set[tuple[str, str]] = set()
    # ALMG: a soma das notas de cada tipo no mês tem de dar o total do tipo
    fecham = tipos = 0
    for r in con.execute("SELECT valor FROM totais_oficiais WHERE fonte='almg' AND metrica='tipos_que_fecham'"):
        a, _, b = str(r[0]).partition("/")
        fecham += int(a or 0)
        tipos += int(b or 0)
    if tipos:
        rv.conferencia("almg", "soma_das_notas_x_total_do_tipo", "todos os meses", f"{tipos} tipos de despesa × mês", f"{fecham} fecham",
                       "confere" if fecham == tipos else "parcial",
                       "a API dá o total de cada tipo de despesa no mês e as notas dele; a soma das notas tem de dar o total")
    for r in con.execute("SELECT escopo, texto_original FROM totais_oficiais WHERE fonte='almg' AND metrica='soma_do_tipo_diverge'"):
        dep, ano, mes, cod = r["escopo"].split("-")
        rv.revisao("almg", "total", r["escopo"], f"{mes}/{ano}, tipo {cod}: {r['texto_original']}")
        for (chave,) in con.execute("""SELECT chave FROM despesas WHERE fonte='almg' AND ref_parlamentar=? AND competencia=?
                                       AND json_extract(extra, '$.cod_tipo')=?""", (f"id:{dep}", f"{ano}-{mes}", int(cod))):
            fora.add(("almg", chave))
    # CLDF: o arquivo parcial do ano tem de estar contido no principal
    for r in con.execute("SELECT escopo, valor, texto_original FROM totais_oficiais WHERE fonte='cldf' AND metrica='recurso_contido_no_principal'"):
        rv.conferencia("cldf", "outro_arquivo_do_ano_contido_no_principal", r["escopo"], "todas as notas", r["texto_original"],
                       "confere" if r["valor"] == "confere" else "diverge",
                       "a fonte publica mais de um arquivo para o mesmo ano; o robô lê o do ano inteiro e confere os outros contra ele")
    for r in con.execute("SELECT escopo, valor, texto_original FROM totais_oficiais WHERE fonte='cldf' AND metrica='recursos_no_conjunto'"):
        rv.conferencia("cldf", "recursos_do_ano", r["escopo"], None, r["valor"], "observacao", r["texto_original"])
    fora |= _divergencias_da_tela(con, rv)
    return frozenset(fora)


# O que cada assembleia lida pela tela confere, em português de leigo.
CONFERENCIA_DA_TELA = {
    "alap": "a tela dá o valor de cada elemento de despesa no mês e, no detalhe, as notas dele; as notas somam o elemento, "
            "os elementos somam o TOTAL do mês, e o TOTAL é o do histórico do ano (com o mês complementar)",
    "alece": "a tela dá, para cada deputado no mês, os empenhos e o TOTAL GERAL; os empenhos somam o total, e cada empenho da tela "
             "está no CSV do mês que a própria casa publica (mesmo CNPJ, mesmo valor), e o contrário",
    "aleto": "o PDF de cada mês traz as notas com o saldo corrido; o saldo de cada linha é o anterior menos a nota, as notas somam o total "
             "das despesas do quadro do mês, e o valor ressarcido é esse total",
    "alba": "cada linha da lista (processo, NF, valor) tem de bater com a página de detalhe da nota; no ano, as linhas de todos os "
            "deputados somam as linhas da lista sem filtro",
    "alego": "a tela de cada deputado no mês dá os lançamentos, o total de cada grupo e o total do mês; os lançamentos somam o grupo e "
             "o total, e o total é o do dado aberto da casa (indenizado e apresentado)",
    "alepe": "a tela dá os pedidos de cada mês com o total e, para cada pedido, as notas; as notas somam o total do pedido",
    "alrn": "a resposta que a tela recebe ao pesquisar traz as linhas, a contagem e a soma; a soma é o total escrito na tela, a contagem "
            "é a do paginador, cada linha aparece na tabela da tela, e os totais por categoria fecham",
}


def _divergencias_da_tela(con, rv: Revisor) -> set[tuple[str, str]]:
    """Assembleias lidas pela tela: cada item grava quantos escopos fecham (soma das
    notas × total que a tela mostra) e a lista dos que não fecham. As notas de um
    escopo que não fecha vão para a revisão."""
    fora: set[tuple[str, str]] = set()
    fontes = [r[0] for r in con.execute("SELECT DISTINCT fonte FROM totais_oficiais WHERE metrica='escopos_que_fecham' ORDER BY 1")]
    for fonte in fontes:
        fecham = escopos = 0
        divergentes: dict[str, str] = {}
        for r in con.execute("""SELECT t.valor, t.texto_original FROM totais_oficiais t JOIN inventario i ON i.fonte=t.fonte AND i.chave=t.escopo
                                WHERE t.fonte=? AND t.metrica='escopos_que_fecham' AND i.situacao='ok'""", (fonte,)):
            a, _, b = str(r[0]).partition("/")
            fecham += int(a or 0)
            escopos += int(b or 0)
            for d in json.loads(r[1] or "[]"):
                divergentes[d["escopo"]] = d["texto"]
        if not escopos:
            continue
        rv.conferencia(fonte, "soma_das_notas_x_total_da_tela", "todos os itens", f"{escopos} totais na tela", f"{fecham} fecham",
                       "confere" if fecham == escopos else "parcial",
                       CONFERENCIA_DA_TELA.get(fonte, "a tela mostra o total de cada recorte e as notas dele; a soma das notas tem de dar o total"))
        for escopo, texto in sorted(divergentes.items()):
            rv.revisao(fonte, "total", escopo, texto)
        # o contador da própria tela × as linhas que ela mostrou (observação: não mexe nas notas)
        lidos = contados = 0
        meses_diferentes = 0
        for r in con.execute("SELECT valor FROM totais_oficiais WHERE fonte=? AND metrica='contador_x_lidos'", (fonte,)):
            a, _, b = str(r[0]).partition("/")
            if a.isdigit() and b.isdigit():
                lidos += int(a)
                contados += int(b)
                meses_diferentes += a != b
        if contados:
            rv.conferencia(fonte, "contador_da_tela_x_linhas_lidas", "todos os itens", contados, lidos,
                           "confere" if lidos == contados else "observacao",
                           f"o contador 'Mostrando ... de N resultados' × as linhas que a lista mostrou; difere em {meses_diferentes} item(ns)")
        # o ano inteiro: a soma das listas por deputado × a lista sem filtro
        for r in con.execute("SELECT escopo, valor FROM totais_oficiais WHERE fonte=? AND metrica='linhas_da_lista_do_ano'", (fonte,)):
            soma, itens_ok, itens = con.execute(
                """SELECT COALESCE(SUM(CAST(t.valor AS INTEGER)), 0), COUNT(DISTINCT t.escopo),
                          (SELECT COUNT(*) FROM inventario WHERE fonte=? AND periodo=?)
                   FROM totais_oficiais t JOIN inventario i ON i.fonte=t.fonte AND i.chave=t.escopo
                   WHERE t.fonte=? AND t.metrica='linhas_da_lista' AND i.periodo=? AND i.situacao='ok'""",
                (fonte, r["escopo"], fonte, r["escopo"])).fetchone()
            completo = itens_ok == itens
            rv.conferencia(fonte, "linhas_por_deputado_x_lista_do_ano", r["escopo"], r["valor"], soma,
                           ("confere" if str(soma) == r["valor"] else "diverge") if completo else "parcial",
                           f"a lista sem filtro do ano × a soma das listas de cada deputado ({itens_ok} de {itens} deputados coletados)")
        if divergentes:
            for r in con.execute("SELECT chave, extra FROM despesas WHERE fonte=?", (fonte,)):
                if any(e in divergentes for e in json.loads(r["extra"] or "{}").get("escopos_conferencia") or ()):
                    fora.add((fonte, r["chave"]))
    return fora


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
        if eh_elotech(fonte):
            return int(n("SELECT SUM(CAST(valor AS INTEGER)) FROM totais_oficiais WHERE fonte=? AND metrica='registros' AND escopo LIKE 'diarias-%'", fonte)), "totalElements da API de diárias"
        if fonte == "cldf":
            return int(n("SELECT SUM(CAST(valor AS INTEGER)) FROM totais_oficiais WHERE fonte=? AND metrica='linhas_no_arquivo'", fonte)), "linhas do arquivo principal de cada ano"
        if fonte == "almg":
            return int(n("SELECT SUM(CAST(valor AS INTEGER)) FROM totais_oficiais WHERE fonte=? AND metrica='linhas_na_origem'", fonte)), "notas nas respostas da API, mês a mês"
        if fonte == "alesp":
            return int(n("SELECT SUM(CAST(valor AS INTEGER)) FROM totais_oficiais WHERE fonte=? AND metrica='linhas_na_origem'", fonte)), "registros do período no arquivo"
        if eh_betha(fonte):
            return int(n("SELECT SUM(CAST(valor AS INTEGER)) FROM totais_oficiais WHERE fonte=? AND metrica='registros' AND escopo LIKE 'diarias-%'", fonte)), "contador 'Registros encontrados' da tela"
        if eh_equiplano(fonte):
            return int(n("SELECT SUM(CAST(valor AS INTEGER)) FROM totais_oficiais WHERE fonte=? AND metrica='registros' AND escopo LIKE 'diarias-%'", fonte)), "blocos 'Empenho' no relatório de cada ano"
        if eh_pronim(fonte):
            return int(n("SELECT SUM(CAST(valor AS INTEGER)) FROM totais_oficiais WHERE fonte=? AND metrica='registros' AND escopo LIKE 'diarias-%'", fonte)), "linhas credor × mês nas consultas mês a mês da tela"
        if fonte == "cmc_legado":
            return int(n("SELECT SUM(CAST(valor AS INTEGER)) FROM totais_oficiais WHERE fonte=? AND metrica='linhas_lidas'", fonte)), "linhas de diária nas tabelas dos PDFs"
        if fonte == "cmc_prefeitura":
            return int(n("SELECT SUM(CAST(valor AS INTEGER)) FROM totais_oficiais WHERE fonte=? AND metrica='registros_lidos'", fonte)), "linhas lidas mês a mês (a fonte não publica contagem)"
        if fonte in CONFERENCIA_DA_TELA:
            return int(n("""SELECT SUM(CAST(t.valor AS INTEGER)) FROM totais_oficiais t JOIN inventario i ON i.fonte=t.fonte AND i.chave=t.escopo
                            WHERE t.fonte=? AND t.metrica='linhas_na_origem' AND i.situacao='ok'""", fonte)), "notas que a tela mostrou"
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
        # pendência de leitura que não é linha de despesa (subsídio ou gabinete ilegível) não entra na equação
        pend_l = n("SELECT COUNT(*) FROM pendencias WHERE fonte=? AND item NOT LIKE 'servidores-%'", fonte)
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
        ano, _, mun = r["escopo"].partition(":")
        rv.conferencia("tse", "eleitos", r["escopo"], None, r["valor"], "observacao", f"vereadores eleitos em {mun or 'Curitiba'} no arquivo do TSE")
    # cadastro de pessoal da Câmara × eleitos em 2024: quantos vereadores ativos a fonte lista hoje
    for e in entidades.elotech():
        if e.fonte == "cmc_elotech":
            continue
        ativos = con.execute("""SELECT COUNT(DISTINCT ref) FROM pessoas_fonte WHERE fonte=? AND periodo=? AND ref LIKE 'mat:%'
                                AND upper(json_extract(extra, '$.situacao'))='ATIVO'""", (e.fonte, agora()[:4])).fetchone()[0]
        eleitos = con.execute("SELECT valor FROM totais_oficiais WHERE fonte='tse' AND metrica='eleitos' AND escopo=?", (f"2024:{e.municipio}",)).fetchone()
        if ativos or eleitos:
            rv.conferencia(e.fonte, "vereadores_ativos_x_eleitos_2024", agora()[:4], eleitos[0] if eleitos else None, ativos,
                           "confere" if eleitos and str(ativos) == eleitos[0] else "observacao",
                           "vereadores ativos no cadastro de pessoal da Câmara hoje × eleitos em 2024 no TSE (suplente em exercício muda a conta)")
    # Betha: a câmara tem a consulta de diárias no menu e não a alimenta; e o que o robô
    # achou com o mesmo texto no menu e descartou pelas colunas
    for r in con.execute("""SELECT fonte, escopo FROM totais_oficiais WHERE fonte LIKE 'betha_%' AND metrica='registros'
                            AND escopo LIKE 'diarias-%' AND valor='0'"""):
        rv.conferencia(r["fonte"], "consulta_vazia", r["escopo"], None, 0, "observacao",
                       "a câmara tem a consulta de diárias no menu do portal, e ela não traz nenhum registro")
    for r in con.execute("""SELECT fonte, escopo, valor, texto_original FROM totais_oficiais
                            WHERE fonte LIKE 'betha_%' AND metrica='consulta_descartada'"""):
        rv.conferencia(r["fonte"], "consulta_descartada", r["escopo"], None, r["valor"], "observacao",
                       f"item de menu com o mesmo texto, mas sem as colunas de diária por pessoa ({r['texto_original']})")
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
        # atividade legislativa: liga os nomes aos vereadores que as fontes de despesa já identificaram
        atividade.ligar(con, rv)
        atividade.equacoes(con, rv)
    resumo = []
    for r in con.execute("""SELECT fonte, resultado, COUNT(*) n FROM conferencias GROUP BY 1, 2 ORDER BY 1, 2"""):
        resumo.append(f"  conferência {r['fonte']}: {r['n']} {r['resultado']}")
    for r in con.execute("SELECT fonte, tipo, COUNT(*) n FROM revisao GROUP BY 1, 2 ORDER BY 1, 2"):
        resumo.append(f"  revisão {r['fonte']}/{r['tipo']}: {r['n']}")
    for r in con.execute("SELECT fonte, esperado, obtido, resultado FROM conferencias WHERE verificacao='origem_igual_coletado_mais_revisao'"):
        resumo.append(f"  {r['fonte']}: origem {r['esperado']} = coletado + revisão {r['obtido']} → {r['resultado']}")
    return resumo
