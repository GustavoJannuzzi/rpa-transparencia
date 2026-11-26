"""Tabela em markdown do resultado do teste de contrato, lida do JUnit XML do pytest.

Uso: python .github/scripts/resumo_contrato.py contrato.xml [contrato-2.xml]
O segundo arquivo, quando existe, é a nova tentativa só do que reprovou: o
resultado dele vale sobre o da primeira. Vai para o resumo do job no GitHub e para
o corpo da issue quando algo reprova.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

FONTE = {
    "test_camara_api_e_arquivo": "Câmara dos Deputados (API e arquivo anual)",
    "test_elotech_api": "Elotech (API)",
    "test_tse_arquivo": "TSE (arquivo de candidaturas)",
    "test_legado_menu_e_botoes": "Portal legado da Câmara de Curitiba (navegador)",
    "test_prefeitura_filtros_e_postback": "Portal da Prefeitura de Curitiba (navegador)",
    "test_betha_diarias_tabela_e_contador": "Betha (navegador)",
}


def ler(arquivo: Path) -> dict[str, tuple[str, float, str]]:
    casos: dict[str, tuple[str, float, str]] = {}
    for caso in ET.parse(arquivo).getroot().iter("testcase"):
        falha = caso.find("failure")
        if falha is None:
            falha = caso.find("error")
        pulado = caso.find("skipped")
        if falha is not None:
            situacao, detalhe = "reprovou", (falha.get("message") or "").splitlines()[0][:200] if falha.get("message") else ""
        elif pulado is not None:
            situacao, detalhe = "pulado", (pulado.get("message") or "")[:200]
        else:
            situacao, detalhe = "passou", ""
        casos[caso.get("name", "")] = (situacao, float(caso.get("time") or 0), detalhe)
    return casos


def main(caminhos: list[str]) -> None:
    arquivos = [Path(c) for c in caminhos if Path(c).exists()]
    if not arquivos:
        print("O pytest não chegou a gravar o resultado (ver o log da rodada).")
        return
    primeira = ler(arquivos[0])
    segunda = ler(arquivos[1]) if len(arquivos) > 1 else {}
    print("| Fonte | Resultado | Tempo | Detalhe |")
    print("|---|---|---:|---|")
    for nome, (situacao, tempo, detalhe) in primeira.items():
        if nome in segunda:
            antes = detalhe
            situacao, tempo, detalhe = segunda[nome]
            situacao += " na 2ª tentativa"
            if not detalhe:
                detalhe = f"na 1ª: {antes}"
        print(f"| {FONTE.get(nome, nome)} | {situacao} | {tempo:.1f} s | {detalhe.replace('|', '/')} |")
    if not primeira:
        print("| (nenhum teste rodou) | | | |")


if __name__ == "__main__":
    main(sys.argv[1:] or ["contrato.xml"])
