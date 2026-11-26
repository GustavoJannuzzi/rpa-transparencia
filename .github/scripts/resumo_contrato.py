"""Tabela em markdown do resultado do teste de contrato, lida do JUnit XML do pytest.

Uso: python .github/scripts/resumo_contrato.py contrato.xml
Vai para o resumo do job no GitHub e para o corpo da issue quando algo reprova.
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


def main(caminho: str) -> None:
    arquivo = Path(caminho)
    if not arquivo.exists():
        print("O pytest não chegou a gravar o resultado (ver o log da rodada).")
        return
    linhas = []
    for caso in ET.parse(arquivo).getroot().iter("testcase"):
        nome = caso.get("name", "")
        falha = caso.find("failure")
        if falha is None:
            falha = caso.find("error")
        pulado = caso.find("skipped")
        if falha is not None:
            situacao = "reprovou"
            detalhe = (falha.get("message") or "").splitlines()[0][:200] if falha.get("message") else ""
        elif pulado is not None:
            situacao = "pulado"
            detalhe = (pulado.get("message") or "")[:200]
        else:
            situacao = "passou"
            detalhe = ""
        tempo = float(caso.get("time") or 0)
        linhas.append(f"| {FONTE.get(nome, nome)} | {situacao} | {tempo:.1f} s | {detalhe.replace('|', '/')} |")
    print("| Fonte | Resultado | Tempo | Detalhe |")
    print("|---|---|---:|---|")
    print("\n".join(linhas) if linhas else "| (nenhum teste rodou) | | | |")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "contrato.xml")
