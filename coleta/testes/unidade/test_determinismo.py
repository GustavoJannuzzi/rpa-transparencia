"""A derivação (conferir, publicar e relatorio) não pode depender da ordem de um set.

O Python sorteia o hash das strings a cada processo (PYTHONHASHSEED), e a ordem de
um set de strings muda junto. Se essa ordem chega à saída, a mesma coleta publica
páginas diferentes a cada rodada. Foi o que aconteceu: sete vereadores de Curitiba
com despesa no sistema legado e no Elotech mudavam a ordem das datas de coleta na
página, e o nome exibido de quem tem dois nomes parlamentares no gabinete trocava
sozinho. O teste roda a derivação inteira em dois processos com sementes
diferentes e compara a saída byte a byte.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from coleta.nucleo.banco import conectar
from coleta.nucleo.conferencia import _nome_parlamentar

RAIZ = Path(__file__).resolve().parents[3]
# As duas sementes dão ordens diferentes aos dois casos abaixo no código de antes do
# conserto (conferido ao escrever o teste): com elas, o teste reprova a volta do defeito.
SEMENTES = ("0", "1")
# 01/12/2026: com a data fixa, a data de geração não entra na comparação
EPOCA = "1796097600"

# Caso da rodada B: vereador com despesa no legado (PDF) e no Elotech.
LEGADO_E_ELOTECH = [
    ("ALCIDES FONTANELLA", "4101"), ("BENEDITA ZAMBONI", "4102"), ("CORNELIO VALDUGA", "4103"),
    ("DALVINA PERUZZO", "4104"), ("ERMINIO TOMASELLI", "4105"), ("FILOMENA CASAGRANDE", "4106"),
    ("GERVASIO LORENZON", "4107"),
]
# Caso do "Pier": o gabinete de 2018 tem o nome civil com erro de digitação e o nome
# parlamentar curto; o de 2024, o nome certo e o nome parlamentar completo. A
# candidatura do TSE liga o nome curto ao civil, e as duas grafias viram uma pessoa só.
DOIS_NOMES_PARLAMENTARES = [
    # nome civil, grafia errada no gabinete antigo, nome parlamentar antigo, atual, matrícula
    ("ANSELMINO BERTOLUCCI", "ANSELMINO BERTOLUCI", "ANSEL", "ANSEL BERTOLUCCI", "4201"),
    ("BERNARDINO CAVALLARO", "BERNARDINO CAVALARO", "BERNA", "BERNA CAVALLARO", "4202"),
    ("CLAUDINO DELLATORRE", "CLAUDINO DELATORRE", "CLAUD", "CLAUD DELLATORRE", "4203"),
    ("DORIVALDO FERRAZZINI", "DORIVALDO FERAZZINI", "DORIV", "DORIV FERRAZZINI", "4204"),
    ("EUGENIANO GALLINARI", "EUGENIANO GALINARI", "EUGEN", "EUGEN GALLINARI", "4205"),
    ("FLORISBELO MANCINELLI", "FLORISBELO MANCINELI", "FLORI", "FLORI MANCINELLI", "4206"),
    ("GUMERCINDO PAGANOTTO", "GUMERCINDO PAGANOTO", "GUMER", "GUMER PAGANOTTO", "4207"),
]


def _despesa(con, chave: str, fonte: str, ano: int, ref: str, extra: dict) -> None:
    con.execute(
        """INSERT INTO despesas(chave, fonte, item, tipo, ref_parlamentar, beneficiario_tipo, nome_beneficiario, cargo_original,
             data, competencia, ano, categoria_original, valor, url, hash_original, coletado_em, extra)
           VALUES(?,?,?,'diaria_municipal',?,'parlamentar',NULL,'Vereador',?,?,?,'Diária','300.00','u','h',?,?)""",
        (chave, fonte, f"i-{ano}", ref, f"{ano}-05-10", f"{ano}-05", ano, f"{ano + 1}-01-02", json.dumps(extra)),
    )


def montar_banco(caminho: Path) -> None:
    con = conectar(caminho)
    for fonte, fim in (("cmc_legado", "2026-11-20T10:00:00-03:00"), ("cmc_elotech", "2026-11-21T10:00:00-03:00")):
        con.execute("INSERT INTO coletas(fonte, etapa, inicio, fim, situacao, totais) VALUES(?, 'coletar', ?, ?, 'ok', '{\"ok\": 1}')",
                    (fonte, fim, fim))
        con.execute("INSERT INTO inventario(fonte, chave, situacao) VALUES(?, 'i', 'ok')", (fonte,))
    for k, (nome, mat) in enumerate(LEGADO_E_ELOTECH):
        for fonte, ano in (("cmc_legado", 2015), ("cmc_elotech", 2018)):
            con.execute("INSERT INTO pessoas_fonte(fonte, ref, periodo, nome, matricula, casa) VALUES(?,?,?,?,?,'cmc')",
                        (fonte, f"mat:{mat}", str(ano), nome, mat))
        _despesa(con, f"leg{k}", "cmc_legado", 2015, f"mat:{mat}", {"competencia_do_bloco": True, "consistencia": "ok", "marcas": []})
        _despesa(con, f"elo{k}", "cmc_elotech", 2018, f"mat:{mat}", {"consistencia": "ok", "quantidade": 1})
    for k, (civil, errado, antigo, atual, mat) in enumerate(DOIS_NOMES_PARLAMENTARES):
        con.execute("INSERT INTO pessoas_fonte(fonte, ref, periodo, nome, matricula, casa) VALUES('cmc_elotech',?,?,?,?,'cmc')",
                    (f"mat:{mat}", "2024", civil, mat))
        for periodo, nome, parlamentar in (("2018", errado, antigo), ("2024", civil, atual)):
            con.execute("""INSERT INTO pessoas_fonte(fonte, ref, periodo, nome, nome_parlamentar, casa)
                           VALUES('cmc_elotech', ?, ?, ?, ?, 'cmc')""", (f"gab:{nome}", periodo, nome, parlamentar))
        con.execute("""INSERT INTO candidaturas(ano_eleicao, municipio, cargo, sq_candidato, nome, nome_norm, nome_urna, partido, situacao)
                       VALUES(2016, 'CURITIBA', 'VEREADOR', ?, ?, ?, ?, 'PXX', 'ELEITO POR QP')""", (f"sq{k}", civil, civil, antigo))
        _despesa(con, f"gab{k}", "cmc_elotech", 2024, f"mat:{mat}", {"consistencia": "ok", "quantidade": 1})
    con.close()


def derivar(base: Path, pasta: Path, semente: str, raiz: Path = RAIZ) -> Path:
    """conferir + publicar + relatorio num processo novo, com a semente dada."""
    dados = pasta / "dados"
    dados.mkdir(parents=True)
    (dados / "estado.db").write_bytes(base.read_bytes())
    env = {**os.environ, "PYTHONHASHSEED": semente, "SOURCE_DATE_EPOCH": EPOCA, "PYTHONIOENCODING": "utf-8",
           "RPA_DADOS": str(dados), "RPA_PUBLICAR": str(pasta / "publicar"), "RPA_RELATORIO": str(pasta / "relatorio")}
    passos = "from coleta.__main__ import conferir, publicar, relatorio; conferir(); publicar(); relatorio()"
    subprocess.run([sys.executable, "-c", passos], env=env, cwd=raiz, check=True, capture_output=True)
    return pasta


def _arquivos(pasta: Path) -> dict[str, bytes]:
    saida = {}
    for sub in ("publicar", "relatorio", "dados/exportacao"):
        for f in sorted((pasta / sub).rglob("*")):
            if f.is_file():
                saida[f.relative_to(pasta).as_posix()] = f.read_bytes()
    return saida


@pytest.fixture(scope="module")
def duas_rodadas(tmp_path_factory) -> list[Path]:
    tmp = tmp_path_factory.mktemp("determinismo")
    base = tmp / "base.db"
    montar_banco(base)
    return [derivar(base, tmp / f"semente-{s}", s) for s in SEMENTES]


def test_a_mesma_entrada_publica_o_mesmo_byte_a_byte_com_sementes_diferentes(duas_rodadas):
    a, b = (_arquivos(p) for p in duas_rodadas)
    assert a, "a derivação não gravou nada"
    assert sorted(a) == sorted(b)
    diferentes = [nome for nome in a if a[nome] != b[nome]]
    assert not diferentes, f"saída muda com PYTHONHASHSEED: {diferentes[:10]}"


def test_a_saida_cobre_os_dois_casos(duas_rodadas):
    pasta = duas_rodadas[0] / "publicar" / "parlamentares"
    for nome, _ in LEGADO_E_ELOTECH:
        p = json.loads((pasta / f"ver-cwb-{nome.lower().replace(' ', '-')}.json").read_text(encoding="utf-8"))
        # a ordem cronológica dos sistemas: o legado (2013) antes do Elotech (2017)
        assert list(p["p"]["coleta"]) == ["cmc_legado", "cmc_elotech"]
    for civil, _, _, atual, _ in DOIS_NOMES_PARLAMENTARES:
        p = json.loads((pasta / f"ver-cwb-{civil.lower().replace(' ', '-')}.json").read_text(encoding="utf-8"))
        assert p["nome"] == atual.title()


def test_nome_parlamentar_vale_o_do_periodo_mais_recente():
    pier = [("2017", "PIER"), ("2019", "PIER"), ("2019", "PIER PETRUZZIELLO"), ("2026", "PIER PETRUZZIELLO")]
    assert _nome_parlamentar(pier) == "PIER PETRUZZIELLO"
    assert _nome_parlamentar(list(reversed(pier))) == "PIER PETRUZZIELLO"
    # "atual" é o mais recente de todos; no empate de período, o mais completo, depois o alfabético
    assert _nome_parlamentar([("2026", "FULANO"), ("atual", "FULANINHO")]) == "FULANINHO"
    assert _nome_parlamentar([("2025", "FULANO"), ("2025", "FULANO DE TAL")]) == "FULANO DE TAL"
    assert _nome_parlamentar([("2025", "BETO"), ("2025", "BETA")]) == "BETA"
    assert _nome_parlamentar([]) is None
