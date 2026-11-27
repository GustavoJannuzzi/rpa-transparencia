"""importar: as linhas de algumas fontes de um banco de trabalho para o canônico."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from coleta.nucleo.banco import conectar
from coleta.nucleo.importar import TRAVA, ImportacaoRecusada, importar, tabelas_da_coleta


def _semear(pasta: Path, fonte: str, valor: str, *, situacao: str = "ok", n: int = 2) -> None:
    """Uma coleta pequena de `fonte` no banco de `pasta`, com original e evidência em arquivo."""
    con = conectar(pasta / "estado.db")
    orig = pasta / "originais" / fonte / "ab" / f"ab{fonte}{valor}.html"
    orig.parent.mkdir(parents=True, exist_ok=True)
    orig.write_text(f"<p>{fonte} {valor}</p>", encoding="utf-8")
    evid = pasta / "evidencias" / fonte / "20261126-item" / "erro.txt"
    evid.parent.mkdir(parents=True, exist_ok=True)
    evid.write_text("traço", encoding="utf-8")
    h = f"ab{fonte}{valor}"
    con.execute("INSERT INTO originais(hash, fonte, url, caminho, tipo, tamanho, coletado_em) VALUES(?,?,?,?,?,?,?)",
                (h, fonte, "https://x", str(orig.relative_to(pasta)), "html", 10, "2026-11-26"))
    con.execute("INSERT INTO coletas(fonte, etapa, inicio, situacao) VALUES(?, 'coletar', '2026-11-26', 'ok')", (fonte,))
    for i in range(n):
        con.execute("INSERT INTO inventario(fonte, chave, situacao, parametros) VALUES(?,?,?,?)",
                    (fonte, f"item-{i}", situacao, json.dumps({"i": i})))
        con.execute("""INSERT INTO despesas(chave, fonte, item, tipo, ref_parlamentar, beneficiario_tipo, competencia, ano,
                       categoria_original, valor, url, hash_original, coletado_em, extra, casa)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (f"{fonte}-{i}", fonte, f"item-{i}", "verba_estadual", "id:1", "parlamentar", "2026-10", 2026, "X", valor,
                     "https://x", h, "2026-11-26", "{}", f"al-{fonte}"))
        con.execute("INSERT INTO totais_oficiais(fonte, escopo, metrica, valor) VALUES(?,?,?,?)", (fonte, f"item-{i}", "linhas_na_origem", "1"))
    con.execute("INSERT INTO pessoas_fonte(fonte, ref, periodo, nome, casa) VALUES(?,?,?,?,?)", (fonte, "id:1", "2026", f"Pessoa {valor}", f"al-{fonte}"))
    con.execute("INSERT INTO pendencias(chave, fonte, item, motivo) VALUES(?,?,?,?)", (f"p-{fonte}", fonte, "item-0", "valor ilegível"))
    con.close()


def _foto(banco: Path) -> dict[str, list[tuple]]:
    """O conteúdo das tabelas da coleta, sem o id sequencial das coletas."""
    con = sqlite3.connect(banco)
    out = {}
    for t, cols in tabelas_da_coleta(con).items():
        lista = ", ".join(c for c in cols if not (t == "coletas" and c == "id"))
        out[t] = sorted(con.execute(f"SELECT {lista} FROM {t}").fetchall(), key=repr)
    con.close()
    return out


@pytest.fixture
def pastas(tmp_path):
    trabalho, canonico = tmp_path / "trabalho", tmp_path / "canonico"
    _semear(trabalho, "alap", "200.00")
    _semear(trabalho, "alece", "300.00")
    _semear(canonico, "alap", "100.00", n=3)   # uma coleta velha da mesma fonte
    _semear(canonico, "almg", "999.00")        # outra fonte, que não pode ser tocada
    return trabalho, canonico


def test_importa_so_a_fonte_pedida_e_move_os_arquivos(pastas):
    trabalho, canonico = pastas
    antes_almg = {t: [r for r in v if "almg" in repr(r)] for t, v in _foto(canonico / "estado.db").items()}
    r = importar(trabalho / "estado.db", ["alap"], "D2", pasta_destino=canonico)
    depois = _foto(canonico / "estado.db")
    # a fonte importada fica igual à da origem: 2 itens (a coleta velha tinha 3)
    assert [x for x in depois["despesas"] if "alap" in repr(x)] == [x for x in _foto(trabalho / "estado.db")["despesas"] if "alap" in repr(x)]
    assert r.por_tabela["despesas"] == (3, 2) and r.por_tabela["inventario"] == (3, 2)
    # a outra fonte do canônico não foi tocada, e a outra fonte da origem não veio
    assert {t: [x for x in v if "almg" in repr(x)] for t, v in depois.items()} == antes_almg
    assert not any("alece" in repr(x) for v in depois.values() for x in v)
    # os arquivos foram para o canônico, nos mesmos caminhos relativos
    assert (canonico / "originais" / "alap" / "ab" / "abalap200.00.html").exists()
    assert not (trabalho / "originais" / "alap" / "ab" / "abalap200.00.html").exists()
    assert (canonico / "evidencias" / "alap" / "20261126-item" / "erro.txt").exists()
    # a trava fica com quem importou
    assert "sessão D2" in (canonico / TRAVA).read_text(encoding="utf-8")


def test_importar_duas_vezes_da_o_mesmo_banco(pastas):
    trabalho, canonico = pastas
    importar(trabalho / "estado.db", ["alap", "alece"], "D2", pasta_destino=canonico)
    uma = _foto(canonico / "estado.db")
    r = importar(trabalho / "estado.db", ["alap", "alece"], "D2", pasta_destino=canonico)
    assert _foto(canonico / "estado.db") == uma
    assert r.trava.startswith("já era desta sessão") and r.arquivos_movidos == 0 and not r.arquivos_faltando


def test_trava_de_outra_sessao_e_coleta_aberta_param_antes_de_mexer(pastas):
    trabalho, canonico = pastas
    antes = _foto(canonico / "estado.db")
    (canonico / TRAVA).write_text("Em uso pela sessão D1 (worktree x): PR do Betha.\nDesde hoje.\n", encoding="utf-8")
    with pytest.raises(ImportacaoRecusada, match="outra sessão"):
        importar(trabalho / "estado.db", ["alap"], "D2", pasta_destino=canonico)
    (canonico / TRAVA).unlink()
    _semear(trabalho, "alrn", "1.00", situacao="erro", n=1)
    with pytest.raises(ImportacaoRecusada, match="não fechou"):
        importar(trabalho / "estado.db", ["alrn"], "D2", pasta_destino=canonico)
    with pytest.raises(ImportacaoRecusada, match="não tem inventário"):
        importar(trabalho / "estado.db", ["alepe"], "D2", pasta_destino=canonico)
    assert _foto(canonico / "estado.db") == antes and not (canonico / TRAVA).exists()
    # com --aceitar-pendentes, entra (e o conferir conta o erro em aberto)
    importar(trabalho / "estado.db", ["alrn"], "D2", pasta_destino=canonico, aceitar_pendentes=True)


def test_candidaturas_so_vem_com_o_tse(pastas):
    trabalho, canonico = pastas
    con = conectar(trabalho / "estado.db")
    con.execute("INSERT INTO candidaturas(ano_eleicao, municipio, cargo, sq_candidato, nome) VALUES(2024,'X','VEREADOR','1','Fulano')")
    con.execute("INSERT INTO inventario(fonte, chave, situacao) VALUES('tse', 'eleicoes', 'ok')")
    con.close()
    importar(trabalho / "estado.db", ["alap"], "D2", pasta_destino=canonico)
    assert _foto(canonico / "estado.db")["candidaturas"] == []
    importar(trabalho / "estado.db", ["tse"], "D2", pasta_destino=canonico)
    assert len(_foto(canonico / "estado.db")["candidaturas"]) == 1


def test_tabela_nova_de_outra_sessao_entra_se_tiver_a_coluna_fonte(pastas):
    """Uma tabela de coleta que outra frente criar (como as atividades) vem junto, sem mudar o importar."""
    trabalho, canonico = pastas
    for p in (trabalho, canonico):
        con = conectar(p / "estado.db")
        con.execute("CREATE TABLE IF NOT EXISTS atividades(chave TEXT PRIMARY KEY, fonte TEXT, item TEXT, rotulo TEXT)")
        con.close()
    con = conectar(trabalho / "estado.db")
    con.execute("INSERT INTO atividades VALUES('a1', 'alap', 'item-0', 'presença')")
    con.close()
    r = importar(trabalho / "estado.db", ["alap"], "D2", pasta_destino=canonico)
    assert r.por_tabela["atividades"] == (0, 1)


def test_tabela_sem_coluna_fonte_e_sem_dono_para_a_importacao(pastas):
    trabalho, canonico = pastas
    con = conectar(trabalho / "estado.db")
    con.execute("CREATE TABLE misterio(x TEXT)")
    con.close()
    with pytest.raises(ImportacaoRecusada, match="misterio"):
        importar(trabalho / "estado.db", ["alap"], "D2", pasta_destino=canonico)
