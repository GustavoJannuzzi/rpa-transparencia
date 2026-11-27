"""Importar a coleta de algumas fontes de outro banco para este (o canônico).

Uma coleta longa (horas no navegador, com a pausa de cada portal) roda num banco
próprio (`RPA_DADOS` apontando para uma pasta de trabalho), sem segurar o canônico.
Quando ela fecha, `importar` leva as linhas dessas fontes para o banco de destino,
numa transação só, e o tempo de trava no canônico cai de horas para minutos:

- pega a trava `EM-USO.txt` da pasta de destino (ou reconhece que já é sua) e não a
  solta: quem importou ainda roda `conferir` e `publicar` e abre o PR;
- move os arquivos que essas linhas citam (originais) e as evidências das fontes
  para a pasta de destino, nos mesmos caminhos relativos;
- apaga, no destino, as linhas dessas fontes em cada tabela que a coleta escreve e
  copia as do banco de origem. Rodar de novo dá o mesmo banco; importar uma fonte não
  toca as outras.

As tabelas que o `conferir` refaz a cada rodada não entram: ele as reconstrói. Tabela
de coleta sem a coluna `fonte` só pode vir com a fonte dona dela (as candidaturas são
do TSE); outra qualquer faz o `importar` parar antes de mexer em nada.
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .banco import agora, conectar, transacao

# O `conferir` apaga e refaz estas a cada rodada (ver conferencia.LIMPAR).
REFEITAS_PELO_CONFERIR = frozenset({"parlamentares", "parlamentar_ids", "filiacoes", "despesa_situacao", "revisao", "conferencias"})
# Tabela de coleta sem a coluna `fonte`: de quem ela é.
SEM_COLUNA_FONTE = {"candidaturas": "tse"}
# Id sequencial que ninguém referencia: no destino, cada linha ganha um novo.
ID_SEQUENCIAL = {"coletas": "id"}
TRAVA = "EM-USO.txt"


class ImportacaoRecusada(Exception):
    """A importação parou antes de mexer no destino (trava de outra sessão, coleta aberta, esquema diferente)."""


@dataclass
class Relatorio:
    destino: Path
    fontes: list[str]
    por_tabela: dict[str, tuple[int, int]] = field(default_factory=dict)  # tabela -> (apagadas, copiadas)
    arquivos_movidos: int = 0
    arquivos_ja_no_destino: int = 0
    arquivos_faltando: list[str] = field(default_factory=list)
    trava: str = ""

    def linhas(self) -> list[str]:
        out = [f"destino: {self.destino}", f"fontes: {', '.join(self.fontes)}", f"trava: {self.trava}"]
        for t, (a, c) in sorted(self.por_tabela.items()):
            out.append(f"  {t}: {a} apagadas, {c} copiadas")
        out.append(f"  arquivos: {self.arquivos_movidos} movidos, {self.arquivos_ja_no_destino} já estavam no destino")
        if self.arquivos_faltando:
            out.append(f"  arquivos citados que não existem na origem nem no destino: {len(self.arquivos_faltando)} "
                       f"(o primeiro: {self.arquivos_faltando[0]})")
        return out


def _tabelas(con: sqlite3.Connection, esquema: str = "main") -> dict[str, list[str]]:
    nomes = [r[0] for r in con.execute(f"SELECT name FROM {esquema}.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {n: [r[1] for r in con.execute(f"PRAGMA {esquema}.table_info({n})")] for n in nomes}


def tabelas_da_coleta(con: sqlite3.Connection, esquema: str = "main") -> dict[str, list[str]]:
    return {t: c for t, c in _tabelas(con, esquema).items() if t not in REFEITAS_PELO_CONFERIR}


def pegar_trava(pasta: Path, sessao: str) -> str:
    """Cria a trava ou reconhece a própria. A trava de outra sessão para tudo."""
    caminho = pasta / TRAVA
    linha = f"Em uso pela sessão {sessao} (importar)."
    try:
        with caminho.open("x", encoding="utf-8") as f:
            f.write(f"{linha}\nDesde {agora()}. Apague ao terminar (depois do merge do PR).\n")
        return f"criada ({caminho})"
    except FileExistsError:
        atual = caminho.read_text(encoding="utf-8", errors="replace")
        primeira = atual.splitlines()[0] if atual.strip() else ""
        if re.search(rf"sessão {re.escape(sessao)}(?![\w-])", primeira):
            return f"já era desta sessão ({caminho})"
        raise ImportacaoRecusada(f"o destino está em uso por outra sessão: {atual.strip()[:300]}") from None


def _mover(origem: Path, destino: Path, rel: str, rel_out: Relatorio) -> None:
    src, dst = origem / rel, destino / rel
    if dst.exists():
        rel_out.arquivos_ja_no_destino += 1
        if src.exists() and src.resolve() != dst.resolve():
            src.unlink()  # o mesmo hash, o mesmo conteúdo: a cópia da origem sobra
        return
    if not src.exists():
        rel_out.arquivos_faltando.append(rel)
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(src, dst)  # mesmo disco: renomear, sem copiar bytes
    except OSError:
        shutil.move(str(src), str(dst))
    rel_out.arquivos_movidos += 1


def _mover_arvore(origem: Path, destino: Path, rel: str, rel_out: Relatorio) -> None:
    base = origem / rel
    if not base.is_dir():
        return
    for p in sorted(base.rglob("*")):
        if p.is_file():
            _mover(origem, destino, str(p.relative_to(origem)), rel_out)


def importar(banco_origem: Path, fontes: list[str], sessao: str, *, destino: sqlite3.Connection | None = None,
             pasta_destino: Path | None = None, aceitar_pendentes: bool = False) -> Relatorio:
    """Importa as `fontes` de `banco_origem` para o banco de destino (o de `RPA_DADOS`)."""
    from .. import config

    fontes = sorted(set(fontes))
    if not fontes:
        raise ImportacaoRecusada("nenhuma fonte para importar")
    banco_origem = Path(banco_origem).resolve()
    pasta_origem = banco_origem.parent
    pasta_destino = (pasta_destino or config.dados()).resolve()
    if not banco_origem.exists():
        raise ImportacaoRecusada(f"o banco de origem não existe: {banco_origem}")
    if pasta_origem == pasta_destino:
        raise ImportacaoRecusada("a origem e o destino são a mesma pasta")
    rel = Relatorio(destino=pasta_destino, fontes=fontes)

    # 1. confere a origem antes de mexer em qualquer coisa
    src = sqlite3.connect(f"file:{banco_origem.as_posix()}?mode=ro", uri=True)
    try:
        tab_src = tabelas_da_coleta(src)
        marcas = ",".join("?" * len(fontes))
        existentes = {r[0] for r in src.execute(f"SELECT DISTINCT fonte FROM inventario WHERE fonte IN ({marcas})", fontes)}
        if set(fontes) - existentes:
            raise ImportacaoRecusada(f"a origem não tem inventário de {sorted(set(fontes) - existentes)}")
        abertos = src.execute(f"""SELECT fonte, situacao, COUNT(*) FROM inventario WHERE fonte IN ({marcas}) AND situacao != 'ok'
                                  GROUP BY 1, 2 ORDER BY 1, 2""", fontes).fetchall()
        if abertos and not aceitar_pendentes:
            raise ImportacaoRecusada("a coleta na origem não fechou: " + "; ".join(f"{f}: {n} {s}" for f, s, n in abertos)
                                     + " (rode o coletar de novo, ou importe com --aceitar-pendentes)")
        for t, cols in tab_src.items():
            if "fonte" not in cols and SEM_COLUNA_FONTE.get(t) is None:
                raise ImportacaoRecusada(f"a tabela {t} não tem a coluna fonte, e o importar não sabe de quem ela é")
        caminhos = [r[0] for r in src.execute(f"SELECT caminho FROM originais WHERE fonte IN ({marcas}) AND caminho IS NOT NULL", fontes)]
    finally:
        src.close()

    # 2. a trava do destino (e o esquema do código atual, que conectar() cria)
    pasta_destino.mkdir(parents=True, exist_ok=True)
    rel.trava = pegar_trava(pasta_destino, sessao)
    con = destino or conectar(pasta_destino / "estado.db")
    try:
        tab_dst = tabelas_da_coleta(con)
        faltam = sorted(t for t in tab_src if t not in tab_dst and (SEM_COLUNA_FONTE.get(t) is None or SEM_COLUNA_FONTE[t] in fontes))
        if faltam:
            raise ImportacaoRecusada(f"o destino não tem as tabelas {faltam}: rode o importar com o código que as cria")

        # 3. os arquivos primeiro: quando a linha existir no destino, o arquivo dela já está lá
        for c in caminhos:
            if not Path(c).is_absolute():
                _mover(pasta_origem, pasta_destino, c, rel)
        for f in fontes:
            _mover_arvore(pasta_origem, pasta_destino, os.path.join("evidencias", f), rel)
            _mover_arvore(pasta_origem, pasta_destino, os.path.join("evidencias", "videos", f), rel)

        # 4. as linhas, numa transação só
        con.execute("ATTACH DATABASE ? AS origem", (str(banco_origem),))
        try:
            with transacao(con):
                for t in sorted(tab_src):
                    dono = SEM_COLUNA_FONTE.get(t)
                    if "fonte" not in tab_src[t]:
                        if dono not in fontes:
                            continue
                        filtro, args = "", []
                    else:
                        filtro, args = f" WHERE fonte IN ({marcas})", fontes
                    cols = [c for c in tab_src[t] if c in tab_dst[t] and c != ID_SEQUENCIAL.get(t)]
                    lista = ", ".join(cols)
                    apagadas = con.execute(f"DELETE FROM main.{t}{filtro}", args).rowcount
                    # originais: a chave é o hash do conteúdo; se outra fonte já guardou o mesmo
                    # conteúdo, a linha dela fica (OR IGNORE)
                    verbo = "INSERT OR IGNORE" if t == "originais" else "INSERT"
                    copiadas = con.execute(f"{verbo} INTO main.{t}({lista}) SELECT {lista} FROM origem.{t}{filtro}", args).rowcount
                    rel.por_tabela[t] = (apagadas, copiadas)
        finally:
            con.execute("DETACH DATABASE origem")
    finally:
        if destino is None:
            con.close()
    return rel
