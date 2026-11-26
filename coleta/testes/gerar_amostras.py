"""Gera as amostras dos testes a partir dos originais que o robô gravou em dados/.

As amostras vão para o repositório público, então saem daqui sem nome de
servidor, sem CPF de pessoa física e sem campos de dado pessoal que o projeto
não usa. Parlamentar continua com o nome (é o dado público que a plataforma
mostra). Tudo o mais é a resposta real, como veio.

Uso (precisa do PyMuPDF só para tarjar os PDFs; não é dependência do robô):
    python -m coleta.testes.gerar_amostras
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
import sqlite3
import zipfile
from pathlib import Path

from .. import config
from ..de_para import eh_cargo_parlamentar
from ..nucleo.texto import normalizar_nome, sem_acento

AMOSTRAS = Path(__file__).parent / "amostras"
DATA = "2026-11-25"


def _orig(con, fonte: str, like: str) -> list[tuple[str, Path]]:
    return [(u, config.dados() / c) for u, c in con.execute(
        "SELECT url, caminho FROM originais WHERE fonte=? AND url LIKE ? ORDER BY url", (fonte, like))]


def legado(con) -> None:
    import fitz  # PyMuPDF
    import pdfplumber

    from ..fontes.cmc_legado.parser import CABECALHOS, _norm_cab
    pasta = AMOSTRAS / "cmc_legado"
    pasta.mkdir(parents=True, exist_ok=True)
    for url, caminho in _orig(con, "cmc_legado", "%Diarias_%.pdf"):
        ano = re.search(r"Diarias_(\d{4})", url).group(1)
        tarjas: dict[int, list] = {}
        with pdfplumber.open(caminho) as pdf:
            for ip, pagina in enumerate(pdf.pages):
                mapa = None
                for t in pagina.find_tables():
                    for linha, texto in zip(t.rows, t.extract()):
                        normal = [_norm_cab(c) for c in texto]
                        if "BENEFICIARIO" in normal and "CARGO" in normal:
                            mapa = {CABECALHOS[c]: i for i, c in enumerate(normal) if c in CABECALHOS}
                            continue
                        if mapa is None:
                            continue
                        cargo = texto[mapa["cargo"]] if mapa.get("cargo") is not None else ""
                        if cargo and not eh_cargo_parlamentar(cargo):
                            for campo in ("beneficiario", "matricula"):
                                if campo in mapa and linha.cells[mapa[campo]]:
                                    tarjas.setdefault(ip, []).append(linha.cells[mapa[campo]])
                if mapa is None and ip > 0:
                    pass
        doc = fitz.open(caminho)
        for ip, caixas in tarjas.items():
            pg = doc[ip]
            for x0, top, x1, bottom in caixas:
                pg.add_redact_annot(fitz.Rect(x0 + 0.3, top + 0.3, x1 - 0.3, bottom - 0.3), text="", fill=(1, 1, 1))
            pg.apply_redactions()
        doc.save(pasta / f"Diarias_{ano}.pdf", garbage=3, deflate=True)
    # a aplicação React do portal (sem dado pessoal), para o teste de resiliência offline
    import httpx
    spa = pasta / "spa"
    spa.mkdir(exist_ok=True)
    base = "https://transparencia-legada.cmc.pr.gov.br"
    with httpx.Client(headers={"User-Agent": config.UA_ROBO}, timeout=60) as c:
        index = c.get(base + "/").text
        (spa / "index.html").write_text(index, encoding="utf-8")
        for rel in re.findall(r'(?:src|href)="(/static/[^"]+)"', index):
            (spa / rel.lstrip("/")).parent.mkdir(parents=True, exist_ok=True)
            (spa / rel.lstrip("/")).write_bytes(c.get(base + rel).content)


def _anon_textos(texto: str, nomes: dict[str, str]) -> str:
    for nome, troca in sorted(nomes.items(), key=lambda x: -len(x[0])):
        texto = re.sub(_padrao_nome(nome), troca, texto, flags=re.I)
    return texto


_VARIANTES = {"A": "AÀÁÂÃÄ", "E": "EÈÉÊË", "I": "IÌÍÎÏ", "O": "OÒÓÔÕÖ", "U": "UÙÚÛÜ", "C": "CÇ"}


def _padrao_nome(nome: str) -> str:
    """O mesmo nome aparece com um ou dois espaços e com ou sem acento
    ('JOSE' na coluna do credor, 'José' na finalidade)."""
    def palavra(p: str) -> str:
        return "".join(f"[{_VARIANTES[c]}]" if c in _VARIANTES else re.escape(c) for c in sem_acento(p).upper())
    return r"\b" + r"\s+".join(palavra(p) for p in nome.split()) + r"\b"


def elotech(con) -> None:
    pasta = AMOSTRAS / "cmc_elotech"
    pasta.mkdir(parents=True, exist_ok=True)
    for ano in (2017, 2018, 2022, 2023):
        (url, cam), = _orig(con, "cmc_elotech", f"%/api/diarias?exercicio={ano}&%size=100")
        j = json.loads(cam.read_text(encoding="utf-8"))
        for i, x in enumerate(j["content"]):
            if not eh_cargo_parlamentar(re.sub(r"/\d+$", "", x.get("cargo") or "")):
                if x.get("nome"):
                    x["nome"] = f"SERVIDOR(A) {i + 1}"
                x["motivo"] = "(texto omitido na amostra: cita o nome de servidor)"
                x["matricula"] = "0" if x.get("matricula") else x.get("matricula")
        (pasta / f"diarias_{ano}.json").write_text(json.dumps(j, ensure_ascii=False, indent=1), encoding="utf-8")
    (url, cam), = _orig(con, "cmc_elotech", "%/api/servidores?entidade=1&exercicio=2026%")
    j = json.loads(cam.read_text(encoding="utf-8"))
    escolhidos = [x for x in j["content"] if normalizar_nome(x.get("descricaoNatureza")) == "VEREADOR"][:6]
    escolhidos += [x for x in j["content"] if (x.get("descricaoLotacao") or "").startswith("GAB")][:40]
    for i, x in enumerate(escolhidos):
        if normalizar_nome(x.get("descricaoNatureza")) != "VEREADOR":
            x["nome"] = f"SERVIDOR(A) {i + 1}"
            x["matricula"] = 900000 + i
        for k in ("dataNascimento", "cpf"):
            x.pop(k, None)
    j["content"] = escolhidos
    j["totalElements"] = len(escolhidos)
    j["last"] = True
    (pasta / "servidores_2026.json").write_text(json.dumps(j, ensure_ascii=False, indent=1), encoding="utf-8")


def prefeitura(con) -> None:
    from html.parser import HTMLParser

    pasta = AMOSTRAS / "cmc_prefeitura"
    pasta.mkdir(parents=True, exist_ok=True)
    for url, cam in _orig(con, "cmc_prefeitura", "%#exercicio=2025&pagina=1"):
        html = cam.read_text(encoding="utf-8")
        ini = html.index('<table class="grid"')
        fim = html.index("</table>", ini) + len("</table>")
        tabela = html[ini:fim]
        linhas = re.findall(r"<tr class=\"grid_(?:Row|AlternatingRow)\".*?</tr>", tabela, re.S)
        nomes, mats = {}, {}
        for tr in linhas:
            tds = [re.sub(r"<[^>]+>", "", t).strip() for t in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if len(tds) > 4 and not eh_cargo_parlamentar(tds[4]):
                nomes.setdefault(tds[2], f"SERVIDOR(A) {len(nomes) + 1}")
                mats.setdefault(tds[3], str(900001 + len(mats)))
                # matrícula de servidor também sai: troca só a 4ª célula desta linha
                celulas = list(re.finditer(r"(<td[^>]*>)(.*?)(</td>)", tr, re.S))
                m = celulas[3]
                novo = tr[:m.start(2)] + re.sub(re.escape(tds[3]), mats[tds[3]], m.group(2)) + tr[m.end(2):]
                tabela = tabela.replace(tr, novo, 1)
        tabela = _anon_textos(tabela, nomes)
        # só a tabela (o resto da página tem o __VIEWSTATE e o menu do portal)
        (pasta / "diarias_2025_pagina1.html").write_text(f"<!doctype html><html><body>{tabela}</body></html>", encoding="utf-8")


def betha(con) -> None:
    pasta = AMOSTRAS / "cmc_betha"
    pasta.mkdir(parents=True, exist_ok=True)
    for url, cam in _orig(con, "cmc_betha", "%consulta/324825&pagina=1"):
        html = cam.read_text(encoding="utf-8")
        ini = html.index('<table data-v-')
        fim = html.index("</table>", ini) + len("</table>")
        tabela = html[ini:fim]
        cont = re.search(r'<span[^>]*bth-powernumber__value[^>]*>\s*\d+\s*</span>', html).group(0)
        nomes = {}
        # cada célula traz antes do valor um rótulo escondido (versão de celular);
        # sem tirá-lo, o nome vem colado ao rótulo e nenhuma troca acontece
        corpo = re.sub(r'<span[^>]*class="titleTableColumn"[^>]*>.*?</span>', "", tabela[tabela.find("<tbody"):], flags=re.S)
        for tr in re.findall(r"<tr[^>]*>.*?</tr>", corpo, re.S):
            tds = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)).strip() for t in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if len(tds) > 3 and not eh_cargo_parlamentar(tds[2]) and tds[1] not in nomes:
                nomes[tds[1]] = f"SERVIDOR(A) {len(nomes) + 1}"
        tabela = _anon_textos(tabela, nomes)
        # a finalidade às vezes traz o nome encurtado ('em nome da servidora FULANA SOBRENOME,')
        tabela = re.sub(r"(em\s+nome\s+d[ao]\s+servidora?\s+)(?!SERVIDOR\(A\))([^,<]+?)(?=\s*,|\s+para\b)",
                        r"\1SERVIDOR(A)", tabela, flags=re.I)
        sobra = [n for n in nomes if re.search(_padrao_nome(n), tabela, re.I)]
        assert not sobra, f"{len(sobra)} nome(s) de servidor ficaram na amostra do Betha"
        (pasta / "diarias_2026_pagina1.html").write_text(
            f"<!doctype html><html><body><div>{cont}</div>{tabela}</body></html>", encoding="utf-8")
        (pasta / "nomes_trocados.json").write_text(json.dumps(sorted(nomes.values()), ensure_ascii=False), encoding="utf-8")


def ceap() -> None:
    pasta = AMOSTRAS / "camara_deputados"
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = config.cache() / "ceap" / "Ano-2025.csv.zip"
    with zipfile.ZipFile(caminho) as z, z.open(z.namelist()[0]) as f:
        linhas = list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", newline=""), delimiter=";"))
        campos = linhas[0].keys()
    escolha = []
    regras = [
        lambda l: l["txtDescricao"].startswith("PASSAGEM") and l["vlrLiquido"].startswith("-"),
        lambda l: l["txtDescricao"].startswith("COMPLEMENTA") and l["vlrLiquido"].startswith("-"),
        lambda l: not l["ideCadastro"],
        lambda l: len(re.sub(r"\D", "", l["txtCNPJCPF"])) == 11,
        lambda l: not l["txtFornecedor"].strip(),
        lambda l: l["ideCadastro"] == "74383",
    ]
    for r in regras:
        escolha += [l for l in linhas if r(l)][:20]
    escolha += linhas[:120]
    vistos, final = set(), []
    for l in escolha:
        k = id(l)
        if k not in vistos:
            vistos.add(k)
            final.append(dict(l))
    for l in final:
        l["cpf"] = ""
        l["txtPassageiro"] = ""
        if len(re.sub(r"\D", "", l["txtCNPJCPF"])) == 11:
            l["txtCNPJCPF"] = "000.000.000-00"
            l["txtFornecedor"] = "PESSOA FÍSICA (nome omitido na amostra)"
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(campos), delimiter=";", lineterminator="\n")
    w.writeheader()
    w.writerows(final)
    with zipfile.ZipFile(pasta / "Ano-2025-amostra.csv.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Ano-2025.csv", buf.getvalue().encode("utf-8-sig"))


def tse() -> None:
    pasta = AMOSTRAS / "tse"
    pasta.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(config.cache() / "tse" / "consulta_cand_2024.zip") as z, z.open("consulta_cand_2024_PR.csv") as f:
        leitor = csv.DictReader(io.TextIOWrapper(f, encoding="latin-1", newline=""), delimiter=";")
        manter = ["ANO_ELEICAO", "NM_TIPO_ELEICAO", "SG_UE", "NM_UE", "DS_CARGO", "SQ_CANDIDATO", "NM_CANDIDATO",
                  "NM_URNA_CANDIDATO", "SG_PARTIDO", "DS_SIT_TOT_TURNO"]
        linhas = [{k: l[k] for k in manter} for l in leitor if l["SG_UE"] in ("75353", "75833")][:400]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=manter, delimiter=";", lineterminator="\n")
    w.writeheader()
    w.writerows(linhas)
    (pasta / "consulta_cand_2024_PR_amostra.csv").write_bytes(buf.getvalue().encode("latin-1"))


def main() -> None:
    con = sqlite3.connect(config.banco())
    legado(con)
    elotech(con)
    prefeitura(con)
    betha(con)
    ceap()
    tse()
    (AMOSTRAS / "LEIA-ME.md").write_text(
        f"# Amostras dos testes\n\nGravadas pelo próprio robô em {DATA} e geradas por `python -m coleta.testes.gerar_amostras`.\n\n"
        "São as respostas reais dos portais, com estas trocas antes de entrar no repositório:\n\n"
        "- nome e matrícula de servidor: tarjados nos PDFs; nos JSON e HTML, o nome vira `SERVIDOR(A) n` e a matrícula, 0 ou 9000nn;\n"
        "- texto de finalidade que cita servidor: omitido no Elotech; na Prefeitura e no Betha, fica com o nome trocado;\n"
        "- CPF de pessoa física (fornecedor ou deputado) e nome de passageiro: apagados;\n"
        "- HTML: só a tabela e o contador da página (o resto é o menu do portal).\n\n"
        "Parlamentar mantém o nome, que é o dado público que a plataforma mostra.\n", encoding="utf-8")
    print("amostras em", AMOSTRAS)


if __name__ == "__main__":
    main()
