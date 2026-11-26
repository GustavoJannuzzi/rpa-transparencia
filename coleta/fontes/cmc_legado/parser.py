"""Leitura do "Relatório de Diárias de Custo" (PDF) do sistema legado da Câmara de
Curitiba, 2013 a 2016.

O PDF é uma planilha exportada: a extração de texto embaralha as células de duas
linhas, então a leitura é pela grade da tabela. O layout muda no meio da série
(11 colunas até 2014, 15 a partir de 2015), e o parser se guia pelo cabeçalho,
não pela posição. Se o cabeçalho esperado não aparece, é portal que mudou.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import pdfplumber

from ...de_para import eh_cargo_parlamentar
from ...nucleo.erros import PortalMudou
from ...nucleo.texto import ValorIlegivel, dinheiro_br, normalizar_nome, sem_acento

MESES = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6,
    "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12,
}

# Cabeçalho normalizado -> nome do campo. Os dois layouts usam estes nomes.
CABECALHOS = {
    "PORTARIA N": "portaria",
    "BENEFICIARIO": "beneficiario",
    "MATRICULA": "matricula",
    "CARGO": "cargo",
    "DESTINO": "destino",
    "JUSTIFICATIVA EVENTO": "evento",
    "PERIODO": "periodo",
    "VALOR DO EVENTO": "valor_evento",
    "QTDE DE DIARIAS": "qtde",
    "VALOR UNIT": "valor_unit",
    "VALOR TOTAL": "valor_total",
    "VALOR DA HOSPEDAGEM": "hospedagem",
    "MEIO DE TRANSPORTE": "meio_transporte",
    "VALOR DO TRANSPORTE": "transporte",
    "D O M": "dom",
}
OBRIGATORIOS = {"portaria", "beneficiario", "cargo", "periodo", "qtde", "valor_unit", "valor_total", "dom"}

# Guarda de privacidade: só cargo de vereador mantém o nome. O resto vira
# "servidor" sem nome e sem matrícula, já na leitura.

RE_LEGENDA = re.compile(r"^(Quanto ao Pag|\* Os valores)", re.I)
RE_PORTARIA = re.compile(r"^\s*(\d{1,4})\s*(?:de\s*(\d{1,2}/\d{1,2}/\d{2,4})|/\s*(\d{4}))", re.I)


def _norm_cab(c: str | None) -> str:
    t = sem_acento((c or "").replace("\n", " ")).upper()
    t = re.sub(r"[^A-Z ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _limpo(c: str | None) -> str:
    return re.sub(r"\s+", " ", (c or "").replace("\n", " ")).strip()


@dataclass
class LinhaDiaria:
    ano_relatorio: int
    pagina: int
    linha: int
    portaria: str
    data_portaria: date | None
    beneficiario: str | None  # None quando não é parlamentar
    matricula: str | None
    cargo: str
    parlamentar: bool
    destino: str
    evento: str
    periodo_original: str
    data_inicio: date | None
    data_fim: date | None
    nota_data: str | None
    qtde_original: str
    valor_unit_original: str
    valor_total: Decimal | None
    valor_total_original: str
    hospedagem: Decimal | None
    transporte: Decimal | None
    meio_transporte: str | None
    valor_evento: Decimal | None
    dom: str
    marcas: list[str] = field(default_factory=list)  # cancelada, devolvida
    competencia_bloco: int | None = None  # mês do bloco "Totais <mês>" que fecha a linha
    consistencia: str | None = None  # "ok", "nao_verificavel: ...", "diverge: ..."
    ilegivel: str | None = None


@dataclass
class TotalPDF:
    escopo: str  # "AAAA" ou "AAAA-MM"
    diarias: Decimal | None
    hospedagem: Decimal | None
    transporte: Decimal | None
    texto: str


@dataclass
class RelatorioDiarias:
    ano: int
    colunas: list[str]
    linhas: list[LinhaDiaria]
    totais: list[TotalPDF]
    paginas: int


def _data_ddmmaa(t: str, ano_padrao: int) -> date | None:
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", t.strip())
    if not m:
        return None
    d, mes, a = int(m.group(1)), int(m.group(2)), m.group(3)
    if a is None:
        ano = ano_padrao
    elif len(a) == 2:
        ano = 2000 + int(a)
    elif len(a) == 4:
        ano = int(a)
    else:
        return None  # ex.: "05/04/216": ano ilegível na fonte
    if not (2000 <= ano <= 2100):
        return None
    try:
        return date(ano, mes, d)
    except ValueError:
        return None


def ler_periodo(texto: str, ano: int) -> tuple[date | None, date | None]:
    """Quatro formatos vistos: '16/12/2013', '26/02 a 03/03', '10 a 12/03/2015',
    '05/12/2016 a 08/12/2016'."""
    t = _limpo(texto).replace("º", "").replace("°", "")
    partes = [p.strip() for p in re.split(r"\s+(?:a|à|e|[‐-―−-])\s+", t)]
    if len(partes) == 1:
        d = _data_ddmmaa(partes[0], ano)
        return d, d
    if len(partes) == 2:
        ini, fim = partes
        dfim = _data_ddmmaa(fim, ano)
        if re.fullmatch(r"\d{1,2}", ini) and dfim:
            try:
                return date(dfim.year, dfim.month, int(ini)), dfim
            except ValueError:
                return None, dfim
        dini = _data_ddmmaa(ini, dfim.year if dfim else ano)
        return dini, dfim
    return None, None


RE_QTDE_ITEM = re.compile(r"(\d+)\s*(di[aá]rias?|refei[cç][oõ]e?s?|refei[cç][aã]o|locomo[cç][aã]o)?", re.I)


def verificar_consistencia(qtde: str, unit: str, total: Decimal) -> str:
    """Quantidade × unitário = total, inclusive nos compostos
    ('02 diárias + 02 refeições' com 'R$ 610,00 + R$ 100,00')."""
    q = _limpo(qtde)
    u = _limpo(unit).replace("$", " $").replace("R $", "R$")
    if total == 0 and q in ("", "-", "0", "00"):
        return "ok"  # viagem sem diária (só transporte/hospedagem)
    qtds = [int(x) for x in re.findall(r"\d+", q)]
    valores_txt = re.findall(r"\d{1,3}(?:\.\d{3})*,\d{2}|\d+(?=\s*(?:\+|$))", u)
    try:
        valores = [dinheiro_br(v if "," in v else v + ",00") for v in valores_txt]
    except ValorIlegivel:
        return f"nao_verificavel: unitário '{_limpo(unit)}'"
    if not qtds or not valores:
        return f"nao_verificavel: quantidade '{q}' / unitário '{_limpo(unit)}'"
    if len(qtds) != len(valores):
        return f"nao_verificavel: {len(qtds)} quantidades para {len(valores)} valores"
    calc = sum((Decimal(n) * v for n, v in zip(qtds, valores)), Decimal("0"))
    if calc == total:
        return "ok"
    return f"diverge: {' + '.join(f'{n} × {v}' for n, v in zip(qtds, valores))} = {calc}, a fonte diz {total}"


def _dinheiro_opcional(t: str | None) -> Decimal | None:
    t = _limpo(t)
    if not t:
        return None
    try:
        return dinheiro_br(t)
    except ValorIlegivel:
        return None


def ler_pdf(conteudo: bytes, ano: int) -> RelatorioDiarias:
    linhas: list[LinhaDiaria] = []
    totais: list[TotalPDF] = []
    mapa: dict[str, int] | None = None
    ncols: int | None = None
    pendentes_do_bloco: list[LinhaDiaria] = []

    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        npag = len(pdf.pages)
        for ip, pagina in enumerate(pdf.pages, start=1):
            for tabela in pagina.extract_tables():
                for il, linha in enumerate(tabela, start=1):
                    celulas = [c if c is not None else "" for c in linha]
                    normal = [_norm_cab(c) for c in celulas]
                    if "BENEFICIARIO" in normal and "CARGO" in normal:
                        mapa = {}
                        for i, c in enumerate(normal):
                            for cab, campo in CABECALHOS.items():
                                if c == cab or c.startswith(cab):
                                    mapa.setdefault(campo, i)
                        faltam = OBRIGATORIOS - set(mapa)
                        if faltam:
                            raise PortalMudou(f"cabeçalho do PDF {ano} sem as colunas {sorted(faltam)}: {normal}")
                        ncols = len(celulas)
                        continue
                    if mapa is None:
                        continue  # título e notas antes do cabeçalho
                    if len(celulas) != ncols:
                        raise PortalMudou(f"PDF {ano}, página {ip}: tabela com {len(celulas)} colunas, cabeçalho tinha {ncols}")

                    texto_linha = " ".join(_limpo(c) for c in celulas)
                    mt = re.search(r"(Totais\s+([A-Za-zçÇãÃ]+)|Valor Anual\s*\((\d{4})\))", texto_linha)
                    if mt:
                        vt = celulas[mapa["valor_total"]]
                        hosp = celulas[mapa["hospedagem"]] if "hospedagem" in mapa else None
                        transp = celulas[mapa["transporte"]] if "transporte" in mapa else None
                        if mt.group(2):
                            mes = MESES.get(sem_acento(mt.group(2)).upper())
                            if mes is None:
                                raise PortalMudou(f"mês ilegível no total: {texto_linha}")
                            escopo = f"{ano}-{mes:02d}"
                            for l in pendentes_do_bloco:
                                l.competencia_bloco = mes
                            pendentes_do_bloco = []
                        else:
                            escopo = str(ano)
                        totais.append(TotalPDF(escopo, _dinheiro_opcional(vt), _dinheiro_opcional(hosp),
                                               _dinheiro_opcional(transp), texto_linha))
                        continue

                    primeira = _limpo(celulas[0])
                    if not any(_limpo(c) for c in celulas) or RE_LEGENDA.match(primeira):
                        continue  # linha vazia, título ou nota repetidos na página seguinte
                    port = _limpo(celulas[mapa["portaria"]])
                    mp = RE_PORTARIA.match(port)
                    tem_dado = _limpo(celulas[mapa["cargo"]]) or _limpo(celulas[mapa["valor_total"]])
                    if not mp and not tem_dado:
                        # conteúdo que não é diária nem total: anota, não descarta calado
                        linhas.append(_linha_ilegivel(ano, ip, il, celulas, mapa, "linha sem portaria, cargo nem valor"))
                        continue
                    lin = _ler_linha(ano, ip, il, celulas, mapa, mp)
                    linhas.append(lin)
                    pendentes_do_bloco.append(lin)
    if mapa is None:
        raise PortalMudou(f"PDF {ano} sem o cabeçalho da tabela de diárias")
    return RelatorioDiarias(ano=ano, colunas=sorted(mapa, key=mapa.get), linhas=linhas, totais=totais, paginas=npag)


def _ler_linha(ano: int, ip: int, il: int, cel: list[str], mapa: dict[str, int], mp: re.Match | None) -> LinhaDiaria:
    g = lambda campo: _limpo(cel[mapa[campo]]) if campo in mapa else ""  # noqa: E731
    cargo = g("cargo")
    parlamentar = eh_cargo_parlamentar(cargo)
    data_portaria = _data_ddmmaa(mp.group(2), ano) if mp and mp.group(2) else None
    ini, fim = ler_periodo(cel[mapa["periodo"]], ano)
    nota = None
    if ini is None:
        if data_portaria:
            ini = data_portaria
            nota = f"período ilegível na fonte ('{g('periodo')}'); data da portaria usada"
        else:
            nota = f"período ilegível na fonte ('{g('periodo')}')"
    total_txt = g("valor_total")
    dom = g("dom")
    marcas = []
    if re.search(r"CANCELAD", dom, re.I):
        marcas.append("cancelada")
    if re.search(r"DEVOLVID", dom, re.I):
        marcas.append("devolvida")
    ilegivel = None
    try:
        total = dinheiro_br(total_txt)
    except ValorIlegivel:
        total = None
        ilegivel = f"valor total ilegível: '{total_txt}'"
    lin = LinhaDiaria(
        ano_relatorio=ano, pagina=ip, linha=il,
        portaria=g("portaria"), data_portaria=data_portaria,
        beneficiario=g("beneficiario") if parlamentar else None,
        matricula=(g("matricula") or None) if parlamentar else None,
        cargo=cargo, parlamentar=parlamentar,
        destino=g("destino"), evento=g("evento") if parlamentar else "",
        periodo_original=g("periodo"), data_inicio=ini, data_fim=fim, nota_data=nota,
        qtde_original=g("qtde"), valor_unit_original=g("valor_unit"),
        valor_total=total, valor_total_original=total_txt,
        hospedagem=_dinheiro_opcional(g("hospedagem")) if "hospedagem" in mapa else None,
        transporte=_dinheiro_opcional(g("transporte")) if "transporte" in mapa else None,
        meio_transporte=g("meio_transporte") or None,
        valor_evento=_dinheiro_opcional(g("valor_evento")) if "valor_evento" in mapa else None,
        dom=dom, marcas=marcas, ilegivel=ilegivel,
    )
    if total is not None:
        lin.consistencia = verificar_consistencia(lin.qtde_original, lin.valor_unit_original, total)
    return lin


def _linha_ilegivel(ano, ip, il, cel, mapa, motivo) -> LinhaDiaria:
    g = lambda campo: _limpo(cel[mapa[campo]]) if campo in mapa else ""  # noqa: E731
    return LinhaDiaria(
        ano_relatorio=ano, pagina=ip, linha=il, portaria=g("portaria"), data_portaria=None,
        beneficiario=None, matricula=None, cargo=g("cargo"), parlamentar=False, destino="", evento="",
        periodo_original=g("periodo"), data_inicio=None, data_fim=None, nota_data=None,
        qtde_original=g("qtde"), valor_unit_original=g("valor_unit"), valor_total=None,
        valor_total_original=g("valor_total"), hospedagem=None, transporte=None, meio_transporte=None,
        valor_evento=None, dom=g("dom"), ilegivel=motivo,
    )
