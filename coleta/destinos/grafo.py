"""Layout do grafo calculado na geração dos dados (ForceAtlas2), não no navegador
de quem visita. Semente fixa: a mesma entrada dá o mesmo desenho."""

from __future__ import annotations

import math

import networkx as nx
import numpy as np


def layout(nos: list[str], arestas: list[tuple[str, str, float]], iteracoes: int = 400, espalhar: float = 4.0,
           gravidade: float = 1.5) -> dict[str, tuple[float, float]]:
    g: nx.Graph[str] = nx.Graph()
    g.add_nodes_from(sorted(nos))
    for a, b, w in sorted(arestas):
        g.add_edge(a, b, weight=float(w))
    if g.number_of_nodes() == 0:
        return {}
    # Quem não tem ligação nenhuma não tem força que o segure: a repulsão o joga
    # longe e o enquadramento encolhe todo o resto. Esses vão para um anel em volta.
    ligados = [n for n in g if g.degree(n) > 0]
    isolados = sorted(n for n in g if g.degree(n) == 0)
    pos: dict[str, np.ndarray] = {}
    if ligados:
        h = g.subgraph(ligados).copy()
        p = nx.forceatlas2_layout(h, max_iter=iteracoes, scaling_ratio=espalhar, gravity=gravidade, strong_gravity=False,
                                  weight="weight", linlog=False, distributed_action=True, seed=7)
        pos.update({n: np.asarray(v, dtype=float) for n, v in p.items()})
    P = np.array(list(pos.values())) if pos else np.zeros((1, 2))
    centro = np.median(P, axis=0)
    raio = float(np.percentile(np.linalg.norm(P - centro, axis=1), 98)) if pos else 1.0
    raio = raio or 1.0
    for i, n in enumerate(isolados):
        ang = 2 * math.pi * i / max(1, len(isolados))
        pos[n] = centro + 1.12 * raio * np.array([math.cos(ang), math.sin(ang)])
    # escala pelo percentil 98 e pelo anel, não pelo ponto mais distante
    esc = 1.15 * raio
    return {n: (round(float((v[0] - centro[0]) / esc * 500), 2), round(float((v[1] - centro[1]) / esc * 500), 2))
            for n, v in pos.items()}
