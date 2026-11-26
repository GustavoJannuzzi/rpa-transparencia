"""Leitura de planilha XLSX sem biblioteca: o arquivo é um zip de XML.

Basta para as planilhas de dados abertos (uma folha, uma tabela a partir da
primeira linha). Cada célula volta como texto, do jeito que está no XML; quem lê
decide o que é data, número ou texto, e nada é arredondado aqui.
"""

from __future__ import annotations

import re
import zipfile
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

from .erros import PortalMudou

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_RE_COLUNA = re.compile(r"[A-Z]+")
# dia zero das datas do Excel (com o erro histórico de 1900 já compensado)
_EPOCA = date(1899, 12, 30)


def _textos(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    raiz = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(f"{_NS}t")) for si in raiz.findall(f"{_NS}si")]


def ler_xlsx(caminho: Path | str) -> list[dict[str, str | None]]:
    """Linhas da primeira folha como dicionários pelo cabeçalho (primeira linha).
    O valor é o texto da célula; célula numérica volta com o número como está no XML."""
    with zipfile.ZipFile(caminho) as z:
        textos = _textos(z)
        folhas = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
        if not folhas:
            raise PortalMudou("planilha sem folha de dados")
        raiz = ET.fromstring(z.read(folhas[0]))
    linhas: list[dict[str, str | None]] = []
    for row in raiz.iter(f"{_NS}row"):
        celulas: dict[str, str | None] = {}
        for c in row.findall(f"{_NS}c"):
            m = _RE_COLUNA.match(c.get("r") or "")
            if not m:
                continue
            tipo = c.get("t")
            v = c.find(f"{_NS}v")
            if tipo == "s" and v is not None and v.text is not None:
                celulas[m.group(0)] = textos[int(v.text)]
            elif tipo == "inlineStr":
                celulas[m.group(0)] = "".join(t.text or "" for t in c.iter(f"{_NS}t"))
            else:
                celulas[m.group(0)] = v.text if v is not None else None
        linhas.append(celulas)
    if not linhas:
        return []
    cabecalho = {col: (nome or "").strip() for col, nome in linhas[0].items()}
    return [{cabecalho[col]: val for col, val in l.items() if col in cabecalho} for l in linhas[1:] if any(v not in (None, "") for v in l.values())]


def data_serial(texto: str) -> date:
    """Data guardada como número de série do Excel ('45301' ou '45301.0')."""
    n = float(texto)
    if n != int(n):
        raise ValueError(f"data com fração de dia: {texto}")
    return _EPOCA + timedelta(days=int(n))
