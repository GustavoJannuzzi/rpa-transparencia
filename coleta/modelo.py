"""O modelo único. Toda fonte, seja API, arquivo, tela ou PDF, entrega isto.

Dinheiro é sempre Decimal exato. Procedência vai junto de cada número.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

Esfera = Literal["federal", "estadual", "municipal"]
TipoCasa = Literal["camara_federal", "senado", "assembleia", "camara_municipal"]
Modo = Literal["api", "arquivo", "robo", "robo_pdf"]
# Uma linha por nota ou registro da fonte, ou uma linha que a própria fonte já
# somou (a ALESP publica por fornecedor × tipo × mês). Agregado nunca vira nota.
Granularidade = Literal["nota", "agregado"]


class Casa(BaseModel):
    """Uma casa legislativa. A identidade de cada parlamentar é por casa."""

    id: str
    tipo: TipoCasa
    esfera: Esfera
    nome: str
    uf: str
    municipio: str | None = None
    ibge: int | None = None  # código IBGE do município (câmara municipal)
    cargo: str = "parlamentar"  # como se chama quem tem mandato nela, no singular


class SistemaOrigem(BaseModel):
    """O que desenha a linha do tempo da cobertura."""

    fonte: str
    casa: str
    sistema: str  # nome do sistema/fornecedor como aparece para quem visita
    fornecedor: str
    modo: Modo
    cobre_de: int
    cobre_ate: int
    endereco: str
    o_que_tem: str


class Procedencia(BaseModel):
    fonte: str
    url: str
    hash_original: str
    coletado_em: str
    localizador: str | None = None  # página, linha, registro


class Despesa(BaseModel):
    chave: str
    fonte: str
    item: str
    tipo: Literal["cota_federal", "diaria_municipal", "verba_estadual"]
    casa: str | None = None  # None: a casa da fonte
    granularidade: Granularidade = "nota"
    ref_parlamentar: str | None = None  # id do parlamentar NA FONTE
    beneficiario_tipo: Literal["parlamentar", "servidor", "lideranca"]
    nome_beneficiario: str | None = None  # só de parlamentar; servidor nunca tem nome gravado
    cargo_original: str | None = None
    data: date | None = None
    competencia: str  # AAAA-MM
    ano: int
    categoria_original: str
    fornecedor_doc: str | None = None
    fornecedor_tipo: str | None = None
    fornecedor_nome: str | None = None
    valor: Decimal
    documento_url: str | None = None
    descricao: str | None = None
    procedencia: Procedencia
    extra: dict = Field(default_factory=dict)


class PessoaFonte(BaseModel):
    """Um parlamentar como a fonte o apresenta."""

    fonte: str
    ref: str
    periodo: str
    nome: str
    nome_parlamentar: str | None = None
    matricula: str | None = None
    partido: str | None = None
    uf: str | None = None
    casa: str
    extra: dict = Field(default_factory=dict)
    procedencia: Procedencia


class Candidatura(BaseModel):
    ano_eleicao: int
    municipio: str
    cargo: str
    sq_candidato: str
    nome: str
    nome_norm: str
    nome_urna: str | None
    partido: str
    situacao: str
    procedencia: Procedencia


class GabineteRetrato(BaseModel):
    """Quantas pessoas e quanto custa um gabinete numa data. Ninguém tem nome aqui."""

    fonte: str
    lotacao_original: str
    competencia: str
    ref_parlamentar: str | None
    data_referencia: str
    pessoas: int
    custo: Decimal
    procedencia: Procedencia


class Remuneracao(BaseModel):
    """O que um parlamentar recebe (subsídio), como o cadastro de pessoal da casa
    mostra numa data. Só parlamentar: servidor nunca tem linha aqui."""

    fonte: str
    casa: str
    ref_parlamentar: str
    competencia: str
    data_referencia: str
    valor: Decimal
    rotulo: str
    cargo_original: str | None = None
    procedencia: Procedencia


class TotalOficial(BaseModel):
    """O que a própria fonte afirma: contagem, soma em R$, data de atualização."""

    fonte: str
    escopo: str
    metrica: str
    valor: str
    texto_original: str | None = None
    procedencia: Procedencia


class ItemInventario(BaseModel):
    chave: str
    descricao: str
    periodo: str
    parametros: dict = Field(default_factory=dict)


class Pendencia(BaseModel):
    """Linha da origem que o robô não conseguiu ler com certeza. Vai direto para a
    fila de revisão, com o texto original, e conta na conferência (origem =
    coletado + revisão)."""

    fonte: str
    chave: str
    motivo: str
    texto_original: str
    procedencia: Procedencia


class Resultado(BaseModel):
    despesas: list[Despesa] = Field(default_factory=list)
    pendencias: list[Pendencia] = Field(default_factory=list)
    pessoas: list[PessoaFonte] = Field(default_factory=list)
    candidaturas: list[Candidatura] = Field(default_factory=list)
    gabinetes: list[GabineteRetrato] = Field(default_factory=list)
    remuneracoes: list[Remuneracao] = Field(default_factory=list)
    totais: list[TotalOficial] = Field(default_factory=list)


class Descoberta(BaseModel):
    itens: list[ItemInventario]
    totais: list[TotalOficial] = Field(default_factory=list)


CASAS_FIXAS = {
    "camara-deputados": Casa(id="camara-deputados", tipo="camara_federal", esfera="federal", nome="Câmara dos Deputados", uf="BR",
                             cargo="deputado federal"),
    "cmc": Casa(id="cmc", tipo="camara_municipal", esfera="municipal", nome="Câmara Municipal de Curitiba", municipio="Curitiba",
                uf="PR", ibge=4106902, cargo="vereador"),
}
