"""Gera as amostras das fontes novas (Elotech genérico, CLDF, ALMG, ALESP) a partir dos
originais que a coleta guardou em `dados/`. Roda na máquina que coleta:

    python -m coleta.testes.apoio.gerar_amostras_casas

Anonimização (o repositório é público):
- nome de servidor vira "SERVIDOR TARJADO n"; só fica o nome de quem tem cargo de
  vereador ou está no cadastro de vereadores (agente político);
- o texto livre do motivo da viagem é omitido (pode citar servidor pelo nome);
- todo CPF vira um número de dígitos repetidos ("111.111.111-11"), que não fecha o
  dígito verificador e por isso não passa por CPF verdadeiro em lugar nenhum;
- fornecedor pessoa física vira "FORNECEDOR PF TARJADO";
- a planilha XLSX da amostra é escrita de novo, só com as linhas escolhidas.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import sqlite3
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from ... import config
from ...de_para import eh_cargo_parlamentar
from ...fontes.elotech.fonte import eh_natureza_parlamentar
from ...nucleo.planilha import ler_xlsx
from ...nucleo.texto import normalizar_nome, so_digitos

AMOSTRAS = Path(__file__).parents[1] / "amostras"
CPF_FALSO = ["111.111.111-11", "222.222.222-22", "333.333.333-33", "444.444.444-44", "555.555.555-55", "666.666.666-66",
             "777.777.777-77", "888.888.888-88", "999.999.999-99"]


def _orig(con, fonte: str, padrao: str) -> Path:
    (cam,) = con.execute("SELECT caminho FROM originais WHERE fonte=? AND url LIKE ? ORDER BY coletado_em DESC LIMIT 1",
                         (fonte, padrao)).fetchone()
    return config.dados() / cam


def elotech(con) -> None:
    pasta = AMOSTRAS / "elotech"
    pasta.mkdir(parents=True, exist_ok=True)
    serv = json.loads(_orig(con, "elotech_maringa", "%/api/servidores?entidade=6&exercicio=2025%").read_text(encoding="utf-8"))
    campos = ("matricula", "nome", "descricaoNatureza", "descricaoCargo", "descricaoLotacao", "situacao", "remuneracao", "entidade", "exercicio")
    vereadores = [{k: x.get(k) for k in campos} for x in serv["content"] if eh_natureza_parlamentar(x.get("descricaoNatureza"))]
    # um servidor de gabinete, tarjado, para o teste ver que ele não vira vereador
    outro = next(x for x in serv["content"] if not eh_natureza_parlamentar(x.get("descricaoNatureza")))
    vereadores.append({**{k: outro.get(k) for k in campos}, "nome": "SERVIDOR TARJADO 0", "matricula": "999999"})
    nomes_vereadores = {normalizar_nome(v["nome"]) for v in vereadores[:-1]}
    (pasta / "maringa_servidores_2025.json").write_text(json.dumps({**{k: serv[k] for k in serv if k != "content"}, "content": vereadores,
                                                                    "totalElements": len(vereadores), "last": True},
                                                                   ensure_ascii=False, indent=1), encoding="utf-8")
    dia = json.loads(_orig(con, "elotech_maringa", "%/api/diarias?exercicio=2025&%size=100").read_text(encoding="utf-8"))
    for i, x in enumerate(dia["content"]):
        x["motivo"] = "texto omitido na amostra"
        if not eh_cargo_parlamentar(x.get("cargo")) and normalizar_nome(x.get("nome")) not in nomes_vereadores:
            x["nome"] = f"SERVIDOR TARJADO {i + 1}"
            x["matricula"] = None
    (pasta / "maringa_diarias_2025.json").write_text(json.dumps(dia, ensure_ascii=False, indent=1), encoding="utf-8")
    ent = json.loads(_orig(con, "elotech_maringa", "%/api/entidades").read_text(encoding="utf-8"))
    (pasta / "maringa_entidades.json").write_text(json.dumps([{k: e.get(k) for k in ("id", "nome", "cnpj")} for e in ent],
                                                             ensure_ascii=False, indent=1), encoding="utf-8")


def _cpf_falso(mapa: dict, cpf: str | None) -> str | None:
    d = so_digitos(cpf)
    if not d:
        return cpf
    return mapa.setdefault(d, CPF_FALSO[len(mapa) % len(CPF_FALSO)])


def _xlsx(caminho: Path, linhas: list[list[str | None]]) -> None:
    """Planilha mínima: uma folha, texto em linha (inlineStr), número como número."""
    def col(i: int) -> str:
        return chr(ord("A") + i)

    linhas_xml = []
    for r, l in enumerate(linhas, start=1):
        celulas = []
        for c, v in enumerate(l):
            if v is None or v == "":
                continue
            ref = f"{col(c)}{r}"
            if r > 1 and v.replace(".", "", 1).isdigit():
                celulas.append(f'<c r="{ref}"><v>{v}</v></c>')
            else:
                celulas.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(v)}</t></is></c>')
        linhas_xml.append(f'<row r="{r}">{"".join(celulas)}</row>')
    folha = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
             + "".join(linhas_xml) + "</sheetData></worksheet>")
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/worksheets/sheet1.xml", folha)


def cldf(con) -> None:
    pasta = AMOSTRAS / "cldf"
    pasta.mkdir(parents=True, exist_ok=True)
    cpfs: dict[str, str] = {}
    # CSV de 2023: 12 linhas, com o CNPJ gravado como número ("…0001170.0")
    bruto = (config.dados() / "cache" / "cldf" / "65722740-44b5-47e2-a7c1-c05f25f6e936.csv").read_bytes().decode("utf-8-sig")
    leitor = csv.DictReader(io.StringIO(bruto), delimiter=";")
    linhas = [l for _, l in zip(range(400), leitor, strict=False)]
    escolhidas = linhas[:10] + [l for l in linhas if " de " in (l["DATA_COMPROVANTE"] or "")][:2]
    saida = io.StringIO()
    w = csv.DictWriter(saida, fieldnames=leitor.fieldnames or [], delimiter=";")
    w.writeheader()
    for l in escolhidas:
        l = dict(l)
        l["CPF_PARLAMENTAR"] = _cpf_falso(cpfs, l["CPF_PARLAMENTAR"])
        if so_digitos(l["CPF_PRESTADOR"]):
            l["CPF_PRESTADOR"] = _cpf_falso(cpfs, l["CPF_PRESTADOR"])
            l["NOME_PRESTADOR"] = "FORNECEDOR PF TARJADO"
        l["OBSERVACOES"] = ""
        w.writerow(l)
    (pasta / "verbas_2023_amostra.csv").write_text(saida.getvalue(), encoding="utf-8")
    # planilha de 2025: cabeçalho por extenso, datas mês/dia e dia/mês, linhas com as colunas deslocadas
    planilha = ler_xlsx(config.dados() / "cache" / "cldf" / "1d6f9214-b0d8-4266-a27a-b4ec3c50b250.xlsx")
    cab = list(planilha[0].keys())
    texto = [l for l in planilha if "/" in (l.get(cab[6]) or "")]
    deslocadas = [l for l in planilha if (l.get(cab[6]) or "").replace(".", "", 1).isdigit() and not (l.get(cab[6]) or "").isdigit()][:2]
    seriais = [l for l in planilha if (l.get(cab[6]) or "").isdigit() and len(l.get(cab[6]) or "") == 5][:4]
    escolhidas = texto[:3] + [l for l in texto if int((l.get(cab[6]) or "0/0").split("/")[0]) > 12][:2] + seriais + deslocadas
    tabela: list[list[str | None]] = [list[str | None](cab)]
    for l in escolhidas:
        l = dict(l)
        l[cab[1]] = _cpf_falso(cpfs, l.get(cab[1]))
        if so_digitos(l.get(cab[4])):
            l[cab[4]] = _cpf_falso(cpfs, l.get(cab[4]))
            l[cab[2]] = "FORNECEDOR PF TARJADO"
        l[cab[9]] = None
        tabela.append([l.get(k) for k in cab])
    _xlsx(pasta / "verbas_2025_amostra.xlsx", tabela)
    # a página do conjunto, só com a lista de recursos
    html = _orig(con, "cldf", "%/dataset/verbas-indenizatorias").read_text(encoding="utf-8")
    ini = html.find('<ul class="resource-list">')
    fim = html.find("</section>", ini)
    (pasta / "conjunto.html").write_text("<html><body>" + html[ini:fim] + "</body></html>", encoding="utf-8")


def almg(con) -> None:
    pasta = AMOSTRAS / "almg"
    pasta.mkdir(parents=True, exist_ok=True)
    j = json.loads(_orig(con, "almg", "%/deputados/12193/2025/9?formato=json").read_text(encoding="utf-8"))
    cpfs: dict[str, str] = {}
    for t in j["list"]:
        for n in t["listaDetalheVerba"]:
            if len(so_digitos(n.get("cpfCnpj"))) == 11:
                n["cpfCnpj"] = so_digitos(_cpf_falso(cpfs, n["cpfCnpj"]))
                n["nomeEmitente"] = "EMITENTE PF TARJADO"
    (pasta / "verba_mes.json").write_text(json.dumps(j, ensure_ascii=False, indent=1), encoding="utf-8")


def alesp(con) -> None:
    pasta = AMOSTRAS / "alesp"
    pasta.mkdir(parents=True, exist_ok=True)
    regs: list[dict] = []
    vistos_anos: dict[int, int] = {}
    with gzip.open(config.dados() / "cache" / "alesp" / "despesas.json.gz", "rt", encoding="utf-8") as f:
        from ...fontes.alesp.fonte import registros

        for x in registros(f):
            a = int(x["ano"])
            if vistos_anos.get(a, 0) < (8 if a in (2022, 2023, 2026) else 0):
                vistos_anos[a] = vistos_anos.get(a, 0) + 1
                regs.append(x)
            if len(regs) >= 24:
                break
    cpfs: dict[str, str] = {}
    for x in regs:
        x["valor"] = str(x["valor"])
        if x.get("cpf"):
            x["cpf"] = so_digitos(_cpf_falso(cpfs, x["cpf"]))
            x["fornecedor"] = "FORNECEDOR PF TARJADO"
    texto = json.dumps({"despesas": regs}, ensure_ascii=False, indent=1)
    # o valor volta a ser número no JSON, como na fonte
    for x in regs:
        texto = texto.replace(f'"valor": "{x["valor"]}"', f'"valor": {x["valor"]}')
    (pasta / "despesas_amostra.json").write_text(texto, encoding="utf-8")


def main() -> None:
    con = sqlite3.connect(config.banco())
    con.row_factory = sqlite3.Row
    elotech(con)
    cldf(con)
    almg(con)
    alesp(con)
    print("amostras gravadas em", AMOSTRAS)


if __name__ == "__main__":
    main()
