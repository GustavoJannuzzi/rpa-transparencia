"""relatorio: a página HTML da conferência. Um arquivo só, sem dependência externa."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from jinja2 import Environment

from .. import config
from ..fontes import FONTES
from ..nucleo.banco import agora
from ..nucleo.texto import cpfs_expostos

MODELO = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Relatório de conferência</title>
<style>
:root{--fundo:#fbfaf7;--texto:#1d1d1b;--suave:#6b6a64;--linha:#e4e1d8;--ok:#1f6f43;--div:#a3361f;--obs:#7a5b00}
@media (prefers-color-scheme:dark){:root{--fundo:#141413;--texto:#ecebe6;--suave:#a19f97;--linha:#2d2c29;--ok:#5fc08a;--div:#ef8a6f;--obs:#e0b84a}}
*{box-sizing:border-box}body{margin:0;background:var(--fundo);color:var(--texto);font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1080px;margin:0 auto;padding:40px 20px 80px}h1{font-size:28px;margin:0 0 4px}h2{font-size:20px;margin:48px 0 8px;padding-top:16px;border-top:1px solid var(--linha)}
h3{font-size:15px;margin:24px 0 6px}p.sub{color:var(--suave);margin:0 0 24px}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:13.5px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--linha);vertical-align:top}th{color:var(--suave);font-weight:600}
.confere,.confere_sem_marcadas{color:var(--ok)}.diverge{color:var(--div);font-weight:600}.parcial,.observacao,.sem_total_na_fonte{color:var(--obs)}
.eq{font-size:18px;margin:8px 0}.eq b{font-variant-numeric:tabular-nums}.tag{display:inline-block;font-size:12px;padding:1px 8px;border:1px solid var(--linha);border-radius:99px;color:var(--suave)}
code{font-size:12.5px}details{margin:6px 0}summary{cursor:pointer}
</style></head><body><main>
<h1>Relatório de conferência</h1>
<p class="sub">Gerado em {{ gerado }} · robô {{ versao }} · cada fonte: <b>origem = coletado + revisão</b>, e nenhum erro em aberto.</p>
<table><tr><th>Fonte</th><th>Como</th><th>Origem</th><th>Coletado</th><th>Revisão</th><th>Equação</th><th>Erros em aberto</th></tr>
{% for f in fontes %}<tr><td><a href="#{{ f.id }}">{{ f.sistema }}</a></td><td><span class="tag">{{ f.modo }}</span></td>
<td>{{ f.origem if f.origem is not none else "—" }}</td><td>{{ f.coletado }}</td><td>{{ f.revisao }}</td>
<td class="{{ f.eq_resultado }}">{{ f.eq_resultado or "—" }}</td><td class="{{ 'confere' if f.erros == 0 else 'diverge' }}">{{ f.erros }}</td></tr>{% endfor %}
</table>
{% for f in fontes %}
<h2 id="{{ f.id }}">{{ f.sistema }}</h2>
<p class="sub">{{ f.o_que_tem }} <span class="tag">{{ f.modo }}</span> · {{ f.endereco }}</p>
{% if f.eq %}<p class="eq">Origem <b>{{ f.eq.esperado }}</b> = coletado + revisão <b>{{ f.eq.obtido }}</b> → <span class="{{ f.eq.resultado }}">{{ f.eq.resultado }}</span><br><small>{{ f.eq.detalhe }}</small></p>{% endif %}
<h3>Conferências</h3>
<table><tr><th>Verificação</th><th>Escopo</th><th>Esperado (fonte)</th><th>Obtido (robô)</th><th>Resultado</th></tr>
{% for c in f.conferencias[:80] %}<tr><td>{{ c.verificacao }}{% if c.detalhe %}<br><small>{{ c.detalhe }}</small>{% endif %}</td><td>{{ c.escopo }}</td><td>{{ c.esperado or "" }}</td><td>{{ c.obtido or "" }}</td><td class="{{ c.resultado }}">{{ c.resultado }}</td></tr>{% endfor %}
</table>{% if f.conferencias|length > 80 %}<p class="sub">+ {{ f.conferencias|length - 80 }} conferências (todas confere) omitidas.</p>{% endif %}
<h3>Fila de revisão</h3>
{% if f.revisao_grupos %}<table><tr><th>Motivo</th><th>Tipo</th><th>Itens</th></tr>
{% for g in f.revisao_grupos %}<tr><td>{{ g.motivo }}</td><td>{{ g.tipo }}</td><td>{{ g.n }}</td></tr>{% endfor %}</table>
{% else %}<p class="sub">Nada em revisão.</p>{% endif %}
{% endfor %}
</main></body></html>"""


def gerar(con: sqlite3.Connection) -> Path:
    fontes = []
    for F in FONTES:
        fid = F.id
        eq = con.execute("SELECT * FROM conferencias WHERE fonte=? AND verificacao='origem_igual_coletado_mais_revisao'", (fid,)).fetchone()
        err = con.execute("SELECT obtido FROM conferencias WHERE fonte=? AND verificacao='erros_em_aberto'", (fid,)).fetchone()
        sit = {r[0]: r[1] for r in con.execute("SELECT s.situacao, COUNT(*) FROM despesas d JOIN despesa_situacao s USING(chave) WHERE d.fonte=? GROUP BY 1", (fid,))}
        pend = con.execute("SELECT COUNT(*) FROM pendencias WHERE fonte=?", (fid,)).fetchone()[0]
        coletado = sum(v for k, v in sit.items() if k != "revisao")
        if fid == "tse":
            coletado = con.execute("SELECT COUNT(*) FROM candidaturas").fetchone()[0]
        fontes.append({
            "id": fid, "sistema": F.sistema.sistema, "modo": {"api": "API", "arquivo": "arquivo", "robo": "robô de navegador", "robo_pdf": "robô + PDF"}[F.sistema.modo],
            "o_que_tem": F.sistema.o_que_tem, "endereco": F.sistema.endereco,
            "origem": int(eq["esperado"]) if eq else None, "coletado": coletado, "revisao": sit.get("revisao", 0) + pend,
            "eq": dict(eq) if eq else None, "eq_resultado": eq["resultado"] if eq else None,
            "erros": int(err["obtido"]) if err else 0,
            "conferencias": [dict(r) for r in con.execute(
                "SELECT * FROM conferencias WHERE fonte=? AND verificacao NOT IN ('origem_igual_coletado_mais_revisao') ORDER BY resultado='confere', verificacao, escopo", (fid,))],
            "revisao_grupos": [dict(r) for r in con.execute(
                "SELECT motivo, tipo, COUNT(*) n FROM revisao WHERE fonte=? OR (fonte='cmc' AND ?='cmc_elotech') GROUP BY 1, 2 ORDER BY n DESC", (fid, fid))],
        })
    html = Environment(autoescape=True).from_string(MODELO).render(fontes=fontes, gerado=agora(), versao=config.VERSAO_ROBO)
    if n := cpfs_expostos(html):  # o relatório também vai para a plataforma
        raise RuntimeError(f"relatório de conferência: {n} CPF(s) sem máscara; nada foi gravado")
    pasta = config.destino_relatorio()
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / "conferencia.html"
    caminho.write_text(html, encoding="utf-8")
    # cópia para a plataforma servir em /conferencia/ (a hospedagem tira o .html do endereço)
    publico = config.destino_plataforma().parent
    if publico.exists():
        destino = publico / "conferencia" / "index.html"
        destino.parent.mkdir(exist_ok=True)
        destino.write_text(html, encoding="utf-8")
    return caminho
