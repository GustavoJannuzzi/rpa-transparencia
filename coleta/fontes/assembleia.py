"""O que as fontes de assembleia têm em comum: a casa vem de `entidades.toml`, a
despesa é a verba indenizatória (ou cota) de cada deputado, com fornecedor, e o
deputado tem identidade dentro da casa."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from .. import config, entidades
from ..entidades import EntidadeAssembleia
from ..modelo import Despesa, Granularidade, Procedencia, SistemaOrigem
from ..nucleo.texto import documento_fornecedor
from .base import Fonte


class FonteAssembleia(Fonte):
    grupo = "assembleia"
    ua = config.UA_ROBO
    o_que_tem = ""
    endereco = ""

    def __init__(self, ent: EntidadeAssembleia) -> None:
        self.ent = ent
        self.id = ent.fonte
        self.de, self.ate = entidades.periodo()
        self.sistema = SistemaOrigem(
            fonte=ent.fonte, casa=ent.casa, sistema=ent.sistema, fornecedor=ent.nome, modo=ent.modo,
            cobre_de=self.de, cobre_ate=self.ate,
            # o endereço que a plataforma mostra a quem lê: uma página que abre, nunca só a raiz de uma API
            endereco=self.endereco or ent.extra.get("documentacao") or ent.extra.get("conjunto") or ent.extra.get("api", ""),
            o_que_tem=self.o_que_tem,
        )
        super().__init__()

    def nota(self, *, chave: str, item: str, ref: str, nome: str, data: date | None, competencia: str, categoria: str,
             documento: str | None, fornecedor: str | None, valor: Decimal, proc: Procedencia, extra: dict,
             granularidade: Granularidade = "nota", documento_url: str | None = None, descricao: str | None = None) -> Despesa:
        doc, tipo_doc = documento_fornecedor(documento)
        return Despesa(
            chave=chave, fonte=self.id, item=item, tipo="verba_estadual", casa=self.ent.casa, granularidade=granularidade,
            ref_parlamentar=ref, beneficiario_tipo="parlamentar", nome_beneficiario=nome, cargo_original=self.ent.cargo,
            data=data, competencia=competencia, ano=int(competencia[:4]), categoria_original=categoria,
            fornecedor_doc=doc, fornecedor_tipo=tipo_doc, fornecedor_nome=(fornecedor or "").strip() or None,
            valor=valor, documento_url=documento_url, descricao=descricao, procedencia=proc, extra=extra,
        )
