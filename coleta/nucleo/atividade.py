"""Conferência da atividade legislativa (sessão, presença, ausência, voto, frequência).

A atividade não cria parlamentar: a pessoa vem das fontes de despesa (e do TSE), e
cada nome que uma fonte de atividade traz se liga a um vereador que já existe na
mesma casa. O nome que não fecha com nenhum, ou fecha com mais de um, vai para a
fila de revisão, e o que ele registrou não é publicado até alguém olhar.

A equação de cada fonte é a mesma ideia das despesas: o que a fonte lista na
janela = o que foi lido e ligado + o que ficou em revisão (+ os votos registrados
na janela que são de sessão de fora dela, no SAPL).
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict

from .. import entidades
from .texto import normalizar_nome

# Título antes do nome de urna ("Sgt. Tania Guerreiro", "Professor Euler"): fica de
# fora só na segunda tentativa, quando o nome inteiro não fechou.
TITULOS = {"SGT", "SARGENTO", "PROFESSOR", "PROFESSORA", "PROF", "DR", "DRA", "DOUTOR", "DOUTORA", "DELEGADA", "DELEGADO",
           "PASTOR", "PASTORA", "JORNALISTA", "VEREADOR", "VEREADORA", "MESTRE", "DONA", "IRMAO", "IRMA", "CAPITAO", "CABO",
           "SOLDADO", "TENENTE", "CORONEL", "ENFERMEIRA", "ENFERMEIRO", "MAJOR", "SUBTENENTE", "BISPO", "MISSIONARIA", "MISSIONARIO"}
PARTICULAS = {"DA", "DE", "DO", "DAS", "DOS", "E"}


def fontes_de_atividade() -> dict[str, str]:
    """fonte -> casa, das fontes de atividade."""
    from ..fontes import FONTES

    return {f.id: f.sistema.casa for f in FONTES if f.dado == "atividade"}


def _tokens(nome: str) -> frozenset[str]:
    n = normalizar_nome(nome.split(" - ")[0])  # "Giorgia Prates - Mandata Preta"
    return frozenset(t for t in n.split() if t not in PARTICULAS and t not in TITULOS)


def _candidatos(con: sqlite3.Connection, casa: str) -> dict[str, set[str]]:
    """Vereador da casa -> todos os nomes pelos quais as fontes de despesa e o TSE o chamam."""
    nomes: dict[str, set[str]] = defaultdict(set)
    for r in con.execute("SELECT id, nome, nome_civil FROM parlamentares WHERE casa=?", (casa,)):
        for n in (r["nome"], r["nome_civil"]):
            if n:
                nomes[r["id"]].add(normalizar_nome(n))
    for r in con.execute("""SELECT pi.parlamentar_id pid, p.nome, p.nome_parlamentar FROM pessoas_fonte p
                            JOIN parlamentar_ids pi ON pi.fonte=p.fonte AND pi.ref=p.ref WHERE p.casa=?""", (casa,)):
        if r["pid"] in nomes:
            for n in (r["nome"], r["nome_parlamentar"]):
                if n:
                    nomes[r["pid"]].add(normalizar_nome(n))
    c = entidades.casas().get(casa)
    if c is not None and c.municipio:
        urna: dict[str, set[str]] = defaultdict(set)
        for r in con.execute("SELECT nome_norm, nome_urna FROM candidaturas WHERE municipio=?", (normalizar_nome(c.municipio),)):
            if r["nome_urna"]:
                urna[r["nome_norm"]].add(normalizar_nome(r["nome_urna"]))
        for ns in nomes.values():
            for n in list(ns):
                ns |= urna.get(n, set())
    return {pid: {n for n in ns if n} for pid, ns in nomes.items()}


def _contido(a: frozenset[str], b: frozenset[str]) -> bool:
    """Todo nome de `a` está em `b`; uma inicial ("R" em "Sergio R. B. Balaguer") vale por
    um nome de `b` que comece com ela. Pelo menos dois nomes inteiros têm de bater."""
    inteiros = {x for x in a if len(x) > 1}
    if len(inteiros & b) < 2 or not inteiros <= b:
        return False
    return all(any(y.startswith(x) for y in b - inteiros) for x in a if len(x) == 1)


def escolher(nomes: set[str], exato: dict[str, set[str]], toks: dict[str, list[frozenset[str]]]) -> tuple[set[str], str]:
    """Os vereadores com que um conjunto de nomes da fonte de atividade fecha.

    Primeiro, o nome inteiro (sem acento, maiúsculo). Se não fechar com exatamente
    um, o nome sem título nem partícula, com pelo menos dois nomes, contido num
    nome do vereador (ou o contrário): "Sgt. Tania Guerreiro" e "Sargento Tânia
    Guerreiro" viram TANIA GUERREIRO."""
    achados: set[str] = set().union(*(exato.get(normalizar_nome(n), set()) for n in nomes))
    if len(achados) == 1:
        return achados, "nome"
    achados = set()
    for n in nomes:
        t = _tokens(n)
        if len(t) < 2:
            continue
        for pid, lista in toks.items():
            if any(len(c) >= 2 and (_contido(t, c) or _contido(c, t)) for c in lista):
                achados.add(pid)
    return achados, "nome sem o título"


def indices(cand: dict[str, set[str]]) -> tuple[dict[str, set[str]], dict[str, list[frozenset[str]]]]:
    exato: dict[str, set[str]] = defaultdict(set)
    for pid, ns in cand.items():
        for n in ns:
            exato[n].add(pid)
    return exato, {pid: [_tokens(n) for n in ns] for pid, ns in cand.items()}


def ligar(con: sqlite3.Connection, rv) -> None:
    """Liga cada parlamentar das fontes de atividade a um vereador que já existe."""
    por_casa: dict[str, list[str]] = defaultdict(list)
    for fonte, casa in fontes_de_atividade().items():
        por_casa[casa].append(fonte)
    for casa, fontes in por_casa.items():
        exato, toks = indices(_candidatos(con, casa))
        for fonte in fontes:
            refs = [r[0] for r in con.execute(
                "SELECT DISTINCT ref_parlamentar FROM atividades WHERE fonte=? AND ref_parlamentar IS NOT NULL", (fonte,))]
            nomes_ref: dict[str, set[str]] = defaultdict(set)
            for r in con.execute("SELECT ref, nome, nome_parlamentar FROM pessoas_fonte WHERE fonte=?", (fonte,)):
                for n in (r["nome"], r["nome_parlamentar"]):
                    if n and n.strip():
                        nomes_ref[r["ref"]].add(n.strip())
            for ref in refs:
                nomes = nomes_ref.get(ref, set())
                if not nomes:
                    rv.revisao(fonte, "identidade", ref, "parlamentar sem nome no cadastro da fonte", {"ref": ref})
                    continue
                achados, metodo = escolher(nomes, exato, toks)
                if len(achados) == 1:
                    con.execute("INSERT OR REPLACE INTO parlamentar_ids(fonte, ref, parlamentar_id, metodo) VALUES(?,?,?,?)",
                                (fonte, ref, achados.pop(), metodo))
                else:
                    n_reg = con.execute("SELECT COUNT(*) FROM atividades WHERE fonte=? AND ref_parlamentar=?", (fonte, ref)).fetchone()[0]
                    motivo = ("o nome casa com mais de um vereador da casa" if achados
                              else "o nome não fecha com nenhum vereador das fontes de despesa da casa")
                    rv.revisao(fonte, "identidade", ref, motivo, {"nomes": sorted(nomes), "registros": n_reg,
                                                                   **({"candidatos": sorted(achados)} if achados else {})})


def equacoes(con: sqlite3.Connection, rv) -> None:
    """Para cada fonte de atividade: o que a fonte lista = lido e ligado + revisão (+ fora da janela)."""
    def n(sql: str, *a) -> int:
        return int(con.execute(sql, a).fetchone()[0] or 0)

    for fonte in fontes_de_atividade():
        if not n("SELECT COUNT(*) FROM inventario WHERE fonte=?", fonte):
            continue
        ok_itens = "(SELECT chave FROM inventario WHERE fonte=? AND situacao='ok')"
        if fonte == "cmc_frequencia":
            origem = n(f"""SELECT SUM(CAST(valor AS INTEGER)) FROM totais_oficiais WHERE fonte=? AND metrica='linhas_lidas'
                           AND escopo IN {ok_itens} AND escopo NOT IN (SELECT escopo FROM totais_oficiais WHERE fonte=?
                           AND metrica='consolidado_nao_somado')""", fonte, fonte, fonte)
            base = "linhas de vereador nas tabelas dos relatórios (o consolidado anual não entra: repete os meses)"
            lidas = n("SELECT COUNT(*) FROM (SELECT DISTINCT competencia, ref_parlamentar FROM atividades WHERE fonte=?)", fonte)
            ligadas = n("""SELECT COUNT(*) FROM (SELECT DISTINCT a.competencia, a.ref_parlamentar FROM atividades a
                           JOIN parlamentar_ids pi ON pi.fonte=a.fonte AND pi.ref=a.ref_parlamentar WHERE a.fonte=?)""", fonte)
            pend = n("SELECT COUNT(*) FROM pendencias WHERE fonte=?", fonte)
            fora = 0
            pub, rev = ligadas, (lidas - ligadas) + pend
        else:
            # SAPL: sessões + presenças + ausências + votos, contados página a página do que já fechou
            # as sessões: o total_entries da lista de sessões na descoberta (as páginas vêm todas nela)
            origem = n("SELECT CAST(valor AS INTEGER) FROM totais_oficiais WHERE fonte=? AND escopo='sessoes' AND metrica='registros'", fonte)
            origem += n(f"""SELECT SUM(CAST(valor AS INTEGER)) FROM totais_oficiais WHERE fonte=? AND metrica='registros'
                            AND escopo IN {ok_itens} AND escopo NOT LIKE '0-%'""", fonte, fonte)
            base = "sessões da janela + registros de presença, ausência e voto nas páginas da API já coletadas"
            fora = n(f"""SELECT SUM(CAST(valor AS INTEGER)) FROM totais_oficiais WHERE fonte=? AND metrica='fora_da_janela'
                         AND escopo IN {ok_itens}""", fonte, fonte)
            sem_pessoa = n("SELECT COUNT(*) FROM atividades WHERE fonte=? AND ref_parlamentar IS NULL", fonte)
            ligadas = n("""SELECT COUNT(*) FROM atividades a JOIN parlamentar_ids pi ON pi.fonte=a.fonte AND pi.ref=a.ref_parlamentar
                           WHERE a.fonte=?""", fonte)
            com_pessoa = n("SELECT COUNT(*) FROM atividades WHERE fonte=? AND ref_parlamentar IS NOT NULL", fonte)
            pend = n("SELECT COUNT(*) FROM pendencias WHERE fonte=?", fonte)
            pub, rev = sem_pessoa + ligadas, (com_pessoa - ligadas) + pend
            # páginas × o total que a API deu na descoberta, por recurso (só quando o recurso fechou)
            for recurso, prefixo in (("ausencias", "3-ausencias"), ("votos", "4-votos")):
                total_api = con.execute("SELECT valor FROM totais_oficiais WHERE fonte=? AND escopo=? AND metrica='registros'",
                                        (fonte, recurso)).fetchone()
                faltam = n("SELECT COUNT(*) FROM inventario WHERE fonte=? AND chave LIKE ? AND situacao!='ok'", fonte, f"{prefixo}%")
                somado = n("""SELECT SUM(CAST(valor AS INTEGER)) FROM totais_oficiais WHERE fonte=? AND metrica='registros'
                               AND escopo LIKE ?""", fonte, f"{prefixo}%") if recurso == "votos" else n(
                    "SELECT COUNT(*) FROM atividades WHERE fonte=? AND tipo='ausencia'", fonte) + n(
                    "SELECT COUNT(*) FROM pendencias WHERE fonte=? AND chave LIKE ?", fonte, f"{fonte}:ausencia:%")
                if total_api is None:
                    continue
                if faltam:
                    rv.conferencia(fonte, "paginas_x_total_da_api", recurso, total_api[0], somado, "parcial",
                                   f"{faltam} página(s) ainda não coletada(s)")
                else:
                    rv.conferencia(fonte, "paginas_x_total_da_api", recurso, total_api[0], somado,
                                   "confere" if str(somado) == str(total_api[0]) else "diverge",
                                   "registros lidos nas páginas × total_entries que a API deu na descoberta")
        soma = pub + rev + fora
        rv.conferencia(fonte, "origem_igual_coletado_mais_revisao", "todas as linhas", origem, soma, "confere" if soma == origem else "diverge",
                       f"origem ({base}) = {origem}; coletado = {pub}; revisão = {rev}" + (f"; fora da janela = {fora}" if fora else ""))
