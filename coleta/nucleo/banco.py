"""SQLite: estado da coleta, registros no modelo único e o que a conferência decidiu.

Valores em dinheiro são gravados como TEXT com o Decimal exato, nunca REAL.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .. import config

ESQUEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS coletas(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fonte TEXT NOT NULL, etapa TEXT NOT NULL,
  inicio TEXT NOT NULL, fim TEXT, situacao TEXT NOT NULL,
  totais TEXT, versao TEXT, mensagem TEXT
);

-- Inventário: cada coisa a coletar numa fonte. É o que dá a retomada.
CREATE TABLE IF NOT EXISTS inventario(
  fonte TEXT NOT NULL, chave TEXT NOT NULL,
  descricao TEXT, periodo TEXT, parametros TEXT,
  situacao TEXT NOT NULL DEFAULT 'pendente',   -- pendente | ok | erro | revisao
  tentativas INTEGER NOT NULL DEFAULT 0,
  ultimo_erro TEXT, evidencia TEXT, atualizado_em TEXT,
  PRIMARY KEY(fonte, chave)
);

-- O que a própria fonte diz de si: contagem, total em R$, data de atualização.
CREATE TABLE IF NOT EXISTS totais_oficiais(
  fonte TEXT NOT NULL, escopo TEXT NOT NULL, metrica TEXT NOT NULL,
  valor TEXT NOT NULL, texto_original TEXT, url TEXT, hash_original TEXT, coletado_em TEXT,
  PRIMARY KEY(fonte, escopo, metrica)
);

-- Cada original (PDF, página, resposta, arquivo) guardado com hash.
CREATE TABLE IF NOT EXISTS originais(
  hash TEXT PRIMARY KEY, fonte TEXT, url TEXT, caminho TEXT, tipo TEXT,
  tamanho INTEGER, coletado_em TEXT
);

-- Modelo único: despesa (cota federal ou diária municipal).
CREATE TABLE IF NOT EXISTS despesas(
  chave TEXT PRIMARY KEY,
  fonte TEXT NOT NULL, item TEXT NOT NULL, tipo TEXT NOT NULL,
  ref_parlamentar TEXT, beneficiario_tipo TEXT NOT NULL,
  nome_beneficiario TEXT, cargo_original TEXT,
  data TEXT, competencia TEXT, ano INTEGER,
  categoria TEXT, categoria_original TEXT,
  fornecedor_doc TEXT, fornecedor_tipo TEXT, fornecedor_nome TEXT,
  valor TEXT NOT NULL, documento_url TEXT, descricao TEXT,
  url TEXT, hash_original TEXT, localizador TEXT, coletado_em TEXT, extra TEXT
);
CREATE INDEX IF NOT EXISTS ix_desp_fonte ON despesas(fonte, ano);
CREATE INDEX IF NOT EXISTS ix_desp_ref ON despesas(ref_parlamentar);

-- Linhas da origem que o robô não leu com certeza (vão para revisão).
CREATE TABLE IF NOT EXISTS pendencias(
  chave TEXT PRIMARY KEY, fonte TEXT NOT NULL, item TEXT NOT NULL,
  motivo TEXT NOT NULL, texto_original TEXT, url TEXT, hash_original TEXT,
  localizador TEXT, coletado_em TEXT
);

-- Parlamentar como cada fonte o vê (id na fonte, nome, partido quando há).
CREATE TABLE IF NOT EXISTS pessoas_fonte(
  fonte TEXT NOT NULL, ref TEXT NOT NULL, periodo TEXT NOT NULL,
  nome TEXT, nome_parlamentar TEXT, matricula TEXT, partido TEXT, uf TEXT,
  casa TEXT, extra TEXT, url TEXT, hash_original TEXT, coletado_em TEXT,
  PRIMARY KEY(fonte, ref, periodo)
);

-- Candidaturas do TSE (só o recorte usado: vereador em Curitiba).
CREATE TABLE IF NOT EXISTS candidaturas(
  ano_eleicao INTEGER NOT NULL, municipio TEXT NOT NULL, cargo TEXT NOT NULL,
  sq_candidato TEXT NOT NULL, nome TEXT, nome_norm TEXT, nome_urna TEXT,
  partido TEXT, situacao TEXT, url TEXT, hash_original TEXT, coletado_em TEXT,
  PRIMARY KEY(ano_eleicao, sq_candidato)
);

-- Gabinete: retrato na data de referência. Sem nome de ninguém.
CREATE TABLE IF NOT EXISTS gabinetes(
  fonte TEXT NOT NULL, lotacao_original TEXT NOT NULL, competencia TEXT NOT NULL,
  ref_parlamentar TEXT, data_referencia TEXT, pessoas INTEGER NOT NULL, custo TEXT NOT NULL,
  url TEXT, hash_original TEXT, coletado_em TEXT,
  PRIMARY KEY(fonte, lotacao_original, competencia)
);

-- Daqui para baixo, tudo é refeito pelo `conferir` a cada rodada.
CREATE TABLE IF NOT EXISTS parlamentares(
  id TEXT PRIMARY KEY, nome TEXT NOT NULL, nome_civil TEXT, casa TEXT NOT NULL,
  uf TEXT, municipio TEXT, partido_atual TEXT, extra TEXT
);
CREATE TABLE IF NOT EXISTS parlamentar_ids(
  fonte TEXT NOT NULL, ref TEXT NOT NULL, parlamentar_id TEXT NOT NULL, metodo TEXT,
  PRIMARY KEY(fonte, ref)
);
CREATE TABLE IF NOT EXISTS filiacoes(
  parlamentar_id TEXT NOT NULL, partido TEXT NOT NULL, desde TEXT, ate TEXT,
  fonte TEXT, base TEXT
);
CREATE TABLE IF NOT EXISTS despesa_situacao(
  chave TEXT PRIMARY KEY, situacao TEXT NOT NULL, motivo TEXT,
  parlamentar_id TEXT, categoria TEXT
);
CREATE TABLE IF NOT EXISTS revisao(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fonte TEXT NOT NULL, tipo TEXT NOT NULL, chave TEXT NOT NULL,
  motivo TEXT NOT NULL, detalhe TEXT, criado_em TEXT,
  UNIQUE(fonte, tipo, chave)
);
CREATE TABLE IF NOT EXISTS conferencias(
  fonte TEXT NOT NULL, verificacao TEXT NOT NULL, escopo TEXT NOT NULL,
  esperado TEXT, obtido TEXT, resultado TEXT NOT NULL, detalhe TEXT, conferido_em TEXT,
  PRIMARY KEY(fonte, verificacao, escopo)
);
"""


def agora() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def conectar(caminho: Path | None = None) -> sqlite3.Connection:
    caminho = caminho or config.banco()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None: autocommit, e as transações são abertas à mão
    # (uma por item do inventário, para a retomada ser atômica).
    con = sqlite3.connect(caminho, timeout=30, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    return con


@contextmanager
def transacao(con: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        con.execute("BEGIN")
        yield con
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise


def js(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
