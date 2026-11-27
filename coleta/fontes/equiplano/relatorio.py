"""Leitura do relatório "Empenhos de Diárias Concedidas" do Equiplano.

O "CSV" do Equiplano é o relatório impresso salvo com ponto e vírgula: o
cabeçalho da página se repete a cada página, cada empenho é um bloco de linhas
com rótulo ("Empenho", "Servidor:", "Liquidação", "Estorno de empenho",
"Pagamento"...), as colunas seguem a largura do papel (rótulos e datas saem
cortados: "Estorno de ", "Data ", "13/01/202") e a descrição é texto livre, em
várias linhas, dentro de uma célula. No fim vem o total do período, que é a
conferência do dinheiro.

Este módulo não fala com a rede: recebe o texto (já sem CPF e RG) e devolve os
empenhos lidos, o cabeçalho e o que não deu para ler.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal

from ...nucleo.texto import ValorIlegivel, cpfs_expostos, dinheiro_br, mascarar_cpf, normalizar_nome

# O arquivo vem em Windows-1252. A máscara trabalha em latin-1 (ida e volta sem
# perda de byte nenhum); a leitura, em cp1252 (aspas e travessão do Word).
CODIFICACAO = "cp1252"

RE_CPF_ROTULO = re.compile(r"CPF:\s*[\d*.\-/]+")
RE_RG_ROTULO = re.compile(r"RG:\s*[\w*.\-/]+(?:\s+[A-Z]{2}\b)?")
OMITIDO = "[omitido pelo robô]"

RE_NUMERO_ANO = re.compile(r"^\d+/\d{4}$")
RE_DATA = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
RE_SERVIDOR = re.compile(r"^\s*(\d[\d.\-/]*)\s+(.+?)\s*(?:CPF:|$)", re.S)
RE_NATUREZA = re.compile(r"^(\d(?:\.\d+)+)\s+(.+)$")
RE_CARGO_DESCRICAO = re.compile(r"CARGO\s*/\s*FUN[ÇC][ÃA]O\s*:\s*([^\r\n]+)", re.I)
RE_PERIODO = re.compile(r"Per[íi]odo de Empenho:\s*(\d{2}/\d{2}/\d{4})\s*a\s*(\d{2}/\d{2}/\d{4})")
RE_ATUALIZADO = re.compile(r"atualizados at[ée] (\d{2}/\d{2}/\d{4} \d{2}:\d{2})")
RE_LINHA_EMPENHO = re.compile(r"(?m)^Empenho;")
TITULO = "EMPENHOS DE DIARIAS CONCEDIDAS"
SEM_DIARIAS = "NAO HOUVE CONCESSAO DE DIARIAS"


def limpar(conteudo: bytes) -> bytes:
    """Tira CPF e RG do relatório, na memória, antes de qualquer gravação.

    O "Servidor:" traz "CPF: ***.837.059-** RG: ***421** PR" na maioria das câmaras
    e, em algumas (Santo Antônio do Sudoeste, nov/2026), o CPF e o RG inteiros. Os
    dois saem pelo rótulo; e qualquer CPF que sobre no texto livre, pela regra dos
    dígitos verificadores. Se ainda sobrar algum, o relatório não é gravado."""
    t = conteudo.decode("latin-1")
    t = RE_CPF_ROTULO.sub(f"CPF: {OMITIDO}", t)
    t = RE_RG_ROTULO.sub(f"RG: {OMITIDO}", t)
    t = mascarar_cpf(t)
    if cpfs_expostos(t):
        raise ValueError("sobrou CPF no relatório depois da máscara")
    return t.encode("latin-1")


@dataclass
class Movimento:
    numero: str
    data: str
    valor: Decimal
    motivo: str | None = None


@dataclass
class EmpenhoLido:
    linha: int  # linha do arquivo onde o bloco começa (para a procedência)
    numero: str
    data: str
    natureza_codigo: str
    natureza: str
    valor: Decimal
    codigo_credor: str | None = None
    nome_credor: str | None = None
    itens: list[Decimal] = field(default_factory=list)
    estornos: list[Movimento] = field(default_factory=list)
    liquidacoes: list[Movimento] = field(default_factory=list)
    estornos_liquidacao: list[Movimento] = field(default_factory=list)
    pagamentos: list[Movimento] = field(default_factory=list)
    estornos_pagamento: list[Movimento] = field(default_factory=list)
    data_inicial: str | None = None
    data_final: str | None = None
    numero_diarias: str | None = None
    valor_diaria: str | None = None
    valor_total_diarias: str | None = None
    destino: str | None = None
    cargo_na_descricao: str | None = None
    problemas: list[str] = field(default_factory=list)  # linha do bloco que não deu para ler

    @property
    def estornado(self) -> Decimal:
        return sum((m.valor for m in self.estornos), Decimal(0))

    @property
    def liquido(self) -> Decimal:
        return self.valor - self.estornado


@dataclass
class Problema:
    linha: int
    motivo: str
    texto: str  # já sem CPF; nunca leva o nome do credor


@dataclass
class Relatorio:
    entidade: str
    inicio: str | None
    fim: str | None
    total_liquido: Decimal | None
    total_texto: str | None
    atualizado_em: str | None
    empenhos_no_arquivo: int  # contados no texto, independente do leitor
    empenhos: list[EmpenhoLido]
    problemas: list[Problema]


def _celulas(linha: list[str]) -> list[str]:
    return [c.strip() for c in linha if c.strip()]


def _cabecalho_de_pagina(c: list[str], entidade: str) -> bool:
    if not c:
        return False
    primeira = normalizar_nome(c[0])
    return (c[0] == entidade or primeira == TITULO or c[0].startswith(("Período de Empenho", "Periodo de Empenho", "Página:"))
            or (len(c) == 1 and c[0].startswith("Página")))


def _valor(texto: str) -> Decimal:
    return dinheiro_br(texto)


def ler(texto: str) -> Relatorio:
    """Lê o relatório inteiro. Empenho que não fecha o formato vira problema (e vai
    para revisão), não chute; rótulo desconhecido dentro do bloco é ignorado só se
    não tiver número de documento."""
    linhas = list(csv.reader(io.StringIO(texto), delimiter=";"))
    celulas = [_celulas(l) for l in linhas]
    # o cabeçalho da página: a primeira linha com texto é o nome da entidade
    entidade = next((c[0] for c in celulas if c), "")
    m = RE_PERIODO.search(texto)
    inicio, fim = (m.group(1), m.group(2)) if m else (None, None)
    m = RE_ATUALIZADO.search(texto)
    atualizado = m.group(1) if m else None
    total = total_txt = None
    empenhos: list[EmpenhoLido] = []
    problemas: list[Problema] = []
    atual: EmpenhoLido | None = None
    secao: str | None = None  # o rótulo cujas linhas de números vêm a seguir

    i = 0
    while i < len(celulas):
        c = celulas[i]
        if not c or _cabecalho_de_pagina(c, entidade):
            i += 1
            continue
        rot = c[0]
        n = normalizar_nome(rot)
        if rot == "Empenho":
            dados = celulas[i + 1] if i + 1 < len(celulas) else []
            i += 2
            atual = None
            secao = None
            # número, data, funcional, conta, recurso, natureza e valor; a natureza e o
            # valor são achados pelo conteúdo (uma câmara pode deixar coluna vazia)
            nat_cel = next((x for x in dados[2:-1] if RE_NATUREZA.match(x) and x[:1] == "3"), None)
            if len(dados) < 4 or not RE_NUMERO_ANO.match(dados[0]) or not RE_DATA.match(dados[1]) or nat_cel is None:
                problemas.append(Problema(i - 1, "empenho fora do formato do relatório",
                                          f"{len(dados)} colunas; número {dados[0] if dados else '?'}"))
                continue
            try:
                valor = _valor(dados[-1])
            except ValorIlegivel:
                problemas.append(Problema(i - 1, f"valor do empenho ilegível: {dados[-1]!r}", f"empenho {dados[0]}"))
                continue
            nat = RE_NATUREZA.match(nat_cel)
            assert nat is not None
            atual = EmpenhoLido(linha=i - 1, numero=dados[0], data=dados[1], natureza_codigo=nat.group(1),
                                natureza=re.sub(r"\s+", " ", nat.group(2)).strip(), valor=valor)
            empenhos.append(atual)
            continue
        if n.startswith("TOTAL DE EMPENHOS LIQUIDOS"):
            total_txt = " ".join(c)
            try:
                total = _valor(c[-1])
            except ValorIlegivel:
                total = None
            atual, secao = None, None
            i += 1
            continue
        if atual is None:
            i += 1
            continue
        if rot.startswith("Servidor"):
            resto = c[1] if len(c) > 1 else ""
            ms = RE_SERVIDOR.match(resto)
            if ms:
                atual.codigo_credor, atual.nome_credor = ms.group(1), re.sub(r"\s+", " ", ms.group(2)).strip()
            secao = None
        elif n == "PRODUTO":
            secao = "itens"
        elif n.startswith("ESTORNO DE EMPENHO"):
            secao = "estornos"
        elif n.startswith("ESTORNO DE PAGAMENTO"):
            secao = "estornos_pagamento"
        elif n.startswith("ESTORNO DE"):
            # "Estorno de liquidação", que o relatório corta em "Estorno de "
            secao = "estornos_liquidacao"
        elif n.startswith("LIQUIDACAO"):
            secao = "liquidacoes"
        elif n.startswith("PAGAMENTO"):
            secao = "pagamentos"
        elif n.startswith("DATA") and any(RE_DATA.match(x) for x in c[1:]):
            # "Data inicial: 13/01/2025 Data final: 16/01/2025 Número de diárias: 3,5 Valor diária: 484,14 Valor total diárias: 1694,49"
            datas = [x for x in c[1:] if RE_DATA.match(x)]
            atual.data_inicial = datas[0] if datas else None
            atual.data_final = datas[1] if len(datas) > 1 else None
            rotulos = {normalizar_nome(x): j for j, x in enumerate(c) if x.endswith(":")}
            for chave, attr in (("NUMERO DE DIARIAS", "numero_diarias"), ("VALOR DIARIA", "valor_diaria"),
                                ("VALOR TOTAL DIARIAS", "valor_total_diarias")):
                j = rotulos.get(chave)
                if j is not None and j + 1 < len(c) and not c[j + 1].endswith(":"):
                    setattr(atual, attr, c[j + 1])
            secao = None
        elif n.startswith("DESTINO") and len(c) > 1 and not c[1].endswith(":"):
            atual.destino = atual.destino or c[1]
            secao = None
        elif RE_NUMERO_ANO.match(rot) and secao in ("estornos", "liquidacoes", "estornos_liquidacao", "pagamentos", "estornos_pagamento"):
            if len(c) < 3:
                atual.problemas.append(f"linha de {secao} incompleta (linha {i + 1} do arquivo)")
            else:
                try:
                    mov = Movimento(numero=c[0], data=c[1], valor=_valor(c[2]), motivo=c[3] if len(c) > 3 else None)
                    getattr(atual, secao).append(mov)
                except ValorIlegivel:
                    atual.problemas.append(f"valor ilegível em {secao}: {c[2]!r} (linha {i + 1} do arquivo)")
        elif secao == "itens" and len(c) >= 4 and not RE_NUMERO_ANO.match(rot):
            try:
                atual.itens.append(_valor(c[-1]))
            except ValorIlegivel:
                pass  # a descrição do item também cai aqui; o item com valor tem o total na última coluna
        else:
            for x in c:
                mc = RE_CARGO_DESCRICAO.search(x)
                if mc and atual.cargo_na_descricao is None:
                    atual.cargo_na_descricao = mc.group(1).strip()
        i += 1
    return Relatorio(entidade=entidade, inicio=inicio, fim=fim, total_liquido=total, total_texto=total_txt,
                     atualizado_em=atualizado, empenhos_no_arquivo=len(RE_LINHA_EMPENHO.findall(texto)),
                     empenhos=empenhos, problemas=problemas)
