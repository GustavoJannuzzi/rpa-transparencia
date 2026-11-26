"""Dinheiro, datas, nomes e documentos. Nada aqui arredonda nem completa valor."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

_RE_DINHEIRO_BR = re.compile(r"-?\s*(?:R\$)?\s*-?\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|-?\d+(?:,\d{1,2})?")


class ValorIlegivel(ValueError):
    pass


def dinheiro_br(texto: str | None) -> Decimal:
    """'R$ 1.234,56' -> Decimal('1234.56'). Recusa o que não for um valor só."""
    if texto is None:
        raise ValorIlegivel("vazio")
    t = texto.replace("\xa0", " ").strip()
    if not t:
        raise ValorIlegivel("vazio")
    negativo = t.startswith("-") or t.startswith("(") or "R$ -" in t or "R$-" in t
    t = t.replace("R$", "").replace("(", "").replace(")", "").replace("-", "").strip()
    t = t.replace(" ", "")
    if not re.fullmatch(r"\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?", t):
        raise ValorIlegivel(texto)
    t = t.replace(".", "").replace(",", ".")
    try:
        v = Decimal(t)
    except InvalidOperation as e:  # pragma: no cover - a regex já filtra
        raise ValorIlegivel(texto) from e
    return -v if negativo else v


def decimal_ponto(texto: str | float | int | None) -> Decimal:
    """'1234.56' (formato dos arquivos e APIs) -> Decimal exato."""
    if texto is None or texto == "":
        raise ValorIlegivel("vazio")
    if isinstance(texto, float):
        # JSON numérico: repr do float devolve a forma curta exata do que veio
        texto = repr(texto)
    try:
        return Decimal(str(texto).strip())
    except InvalidOperation as e:
        raise ValorIlegivel(str(texto)) from e


def data_br(texto: str) -> date:
    d, m, a = re.split(r"[/-]", texto.strip())
    return date(int(a), int(m), int(d))


def sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def normalizar_nome(nome: str | None) -> str:
    """Para comparar nomes entre sistemas: maiúsculas, sem acento, sem pontuação,
    espaços simples. 'Carla Cristiana de Carvalho (Carla Pimentel)' perde o apelido."""
    if not nome:
        return ""
    n = re.sub(r"\(.*?\)", " ", nome)
    n = sem_acento(n).upper()
    n = re.sub(r"[^A-Z ]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    # o PDF de 2013 põe o cargo antes do nome ("Vereador Jorge Luiz Bernardi")
    return re.sub(r"^VEREADORA? (?=\S+ \S+)", "", n)


def apelido_entre_parenteses(nome: str | None) -> str | None:
    if not nome:
        return None
    m = re.search(r"\(([^)]+)\)", nome)
    return m.group(1).strip() if m else None


def slug(texto: str) -> str:
    s = sem_acento(texto).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def so_digitos(texto: str | None) -> str:
    return re.sub(r"\D", "", texto or "")


def documento_fornecedor(texto: str | None) -> tuple[str | None, str]:
    """Devolve (documento exibível, tipo). CNPJ formatado; CPF sempre mascarado.

    O arquivo da CEAP às vezes formata o CNPJ errado ('381.942.120/0012-0');
    por isso a base são os dígitos.
    """
    d = so_digitos(texto)
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}", "cnpj"
    if len(d) == 11:
        return f"***.{d[3:6]}.{d[6:9]}-**", "cpf"
    if not d:
        return None, "vazio"
    return None, "invalido"


_RE_CPF_FORMATADO = re.compile(r"(?<![\d*])\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")
# só não pode haver outro dígito encostado: o CPF do MEI vem colado ao nome, antes de
# letras ('...Z TUR'), antes de '-ME' e depois de 'MEI-'
_RE_ONZE_DIGITOS = re.compile(r"(?<!\d)\d{11}(?!\d)")
_FIM_DE_PALAVRA = frozenset(" \t\r\n\"',;[]{}()<>|")


def _cpf_valido(d: str) -> bool:
    n = [int(c) for c in d]
    if len(set(n)) == 1:
        return False
    for tam in (9, 10):
        if (sum(n[i] * (tam + 1 - i) for i in range(tam)) * 10) % 11 % 10 != n[tam]:
            return False
    return True


def _em_caminho(texto: str, ini: int, fim: int) -> bool:
    """A sequência está dentro de um caminho ou endereço ('publ/2402/....pdf',
    '?ideDocumentoFiscal=...'): é número de documento, não CPF."""
    while ini > 0 and texto[ini - 1] not in _FIM_DE_PALAVRA:
        ini -= 1
    while fim < len(texto) and texto[fim] not in _FIM_DE_PALAVRA:
        fim += 1
    palavra = texto[ini:fim]
    return "/" in palavra or "?" in palavra or "=" in palavra


def _cpf_solto(m: re.Match) -> bool:
    return _cpf_valido(m.group(0)) and not _em_caminho(m.string, m.start(), m.end())


def mascarar_cpf(texto: str) -> str:
    """Mascara CPF dentro de texto livre, como no documento do fornecedor.

    O nome empresarial do MEI traz o CPF do dono (o nome seguido dos 11 dígitos,
    às vezes colado a ele, com '-ME' ou depois de 'MEI-'), e a CEAP publica esse
    nome como veio. O CPF formatado é sempre mascarado. Os 11 dígitos sem outro
    dígito encostado, quando os verificadores de CPF fecham, também, onde quer
    que estejam no texto; a exceção é caminho ou endereço, onde o número é de
    documento (um telefone, em geral, não fecha os verificadores e fica).
    """
    if not texto:
        return texto
    texto = _RE_CPF_FORMATADO.sub(lambda m: f"***.{m.group(0)[4:11]}-**", texto)
    return _RE_ONZE_DIGITOS.sub(
        lambda m: f"***.{m.group(0)[3:6]}.{m.group(0)[6:9]}-**" if _cpf_solto(m) else m.group(0), texto)


def cpfs_expostos(texto: str) -> int:
    """Quantos CPFs (formatados ou soltos, com verificadores que fecham) o texto
    ainda tem, pela mesma regra de `mascarar_cpf`. Serve de trava antes de gravar."""
    formatados = sum(1 for m in _RE_CPF_FORMATADO.finditer(texto) if _cpf_valido(re.sub(r"\D", "", m.group(0))))
    return formatados + sum(1 for m in _RE_ONZE_DIGITOS.finditer(texto) if _cpf_solto(m))


def chave_hash(*partes: object) -> str:
    bruto = "\x1f".join("" if p is None else str(p) for p in partes)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:32]


def sha256_bytes(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()
