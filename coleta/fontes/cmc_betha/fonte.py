"""Câmara de Curitiba no Betha (2026): robô de navegador.

É o adaptador genérico do Betha (`fontes/betha`) com o portal de Curitiba, que
está em `entidades.toml`, e três consultas fixas, revisadas à mão na fase 1:
as diárias de 2026, os servidores ativos (o Organograma diz de qual gabinete) e
a lista de vereadores. Fica aqui com o nome antigo porque os testes, as amostras
e o banco chamam a fonte assim.

A leitura é a do genérico: contador "Registros encontrados", 100 por página e
"Próxima" até o fim, conferindo cada linha com a resposta que a tela recebeu
(que também completa a finalidade, que a tabela corta em "... (Ver mais)").
"""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal

from ...entidades import betha
from ...modelo import Descoberta, GabineteRetrato, ItemInventario, Pendencia, PessoaFonte, Resultado, SistemaOrigem, TotalOficial
from ...nucleo.banco import agora
from ...nucleo.erros import PortalMudou
from ...nucleo.texto import ValorIlegivel, chave_hash, dinheiro_br, normalizar_nome
from ..betha.fonte import BethaCloud, chave_coluna

ENTIDADE_CURITIBA = next(e for e in betha() if e.fonte == "cmc_betha")
PORTAL = ENTIDADE_CURITIBA.tela
CONSULTAS = {
    "diarias-2026": {"id": 324825, "descricao": "Diárias 2026", "periodo": "2026"},
    "servidores-ativos": {"id": 360082, "descricao": "Servidores Públicos – Ativos (gabinetes)", "periodo": "atual"},
    "vereadores": {"id": 360083, "descricao": "Vereadores – Remunerações (lista atual)", "periodo": "atual"},
}
RE_GABINETE = re.compile(r"^GAB\.?\s*VER\.?\s*(.+)$", re.I)

__all__ = ["CONSULTAS", "PORTAL", "CmcBetha", "chave_coluna"]


class CmcBetha(BethaCloud):
    motivo_livre = True

    def __init__(self) -> None:
        super().__init__(ENTIDADE_CURITIBA)
        self.sistema = SistemaOrigem(
            fonte="cmc_betha", casa="cmc", sistema="Portal da Transparência Betha", fornecedor="Betha Sistemas",
            modo="robo", cobre_de=2026, cobre_ate=2026, endereco=PORTAL,
            o_que_tem="Diárias de 2026, servidores ativos por gabinete (Organograma) e a lista de vereadores.",
        )

    async def descobrir(self) -> Descoberta:
        itens = [ItemInventario(chave=k, descricao=v["descricao"], periodo=v["periodo"], parametros={"consulta": v["id"]})
                 for k, v in CONSULTAS.items()]
        return Descoberta(itens=itens)

    async def coletar_item(self, item: ItemInventario) -> Resultado:
        consulta = int(item.parametros["consulta"])
        linhas, contador, atualizacao, hits, hashes, url, rotulos, _ = await self._ler_consulta(consulta)
        proc0 = self.procedencia(url, hashes[0], "contador 'Registros encontrados'")
        res = Resultado(totais=[
            TotalOficial(fonte=self.id, escopo=item.chave, metrica="registros", valor=str(contador),
                         texto_original=f"Registros encontrados: {contador}", procedencia=proc0),
        ])
        if atualizacao:
            res.totais.append(TotalOficial(fonte=self.id, escopo=item.chave, metrica="atualizado_em", valor=atualizacao,
                                           texto_original=f"Última atualização dos dados em {atualizacao}", procedencia=proc0))
        if item.chave.startswith("diarias"):
            self._diarias(item, linhas, hits, hashes, url, res, rotulos)
        elif item.chave == "servidores-ativos":
            self._gabinetes(linhas, hashes, url, res, atualizacao)
        else:
            self._vereadores(linhas, hashes, url, res)
        return res

    def _gabinetes(self, linhas, hashes, url, res: Resultado, atualizacao: str | None) -> None:
        if not linhas:
            raise PortalMudou("consulta de servidores ativos veio vazia")
        cols = set(linhas[0])
        col_org = next((c for c in cols if c.startswith("ORGANOGRAMA")), None)
        col_rem = next((c for c in cols if c.startswith("REMUNERACAO")), None)
        col_sit = next((c for c in cols if c.startswith("SITUACAO")), None)
        if not col_org or not col_rem:
            raise PortalMudou(f"servidores sem Organograma/Remuneração: {sorted(cols)}")
        grupos: dict[str, list[Decimal]] = defaultdict(list)
        for i, l in enumerate(linhas, start=1):
            org = l[col_org].strip()
            if not RE_GABINETE.match(org):
                continue
            if col_sit and l[col_sit] and normalizar_nome(l[col_sit]) not in ("ATIVO", "TRABALHANDO", "EM ATIVIDADE"):
                continue
            try:
                grupos[org].append(dinheiro_br(l[col_rem]))
            except ValorIlegivel:
                proc = self.procedencia(url, hashes[l["_pagina"] - 1], f"página {l['_pagina']}, linha {i}")
                res.pendencias.append(Pendencia(fonte=self.id, chave=chave_hash(self.id, "gab", org, i),
                                                motivo=f"remuneração ilegível: {l[col_rem]!r}",
                                                texto_original=f"gabinete '{org}' (pessoa sem nome)", procedencia=proc))
        hoje = agora()[:10]
        data_ref = hoje
        if atualizacao:
            d, m_, a = atualizacao[:10].split("/")
            data_ref = f"{a}-{m_}-{d}"
        proc = self.procedencia(url, hashes[0], "todas as páginas, coluna Organograma")
        for org, valores in grupos.items():
            m = RE_GABINETE.match(org)
            assert m is not None  # grupos só tem lotação que casou com RE_GABINETE, acima
            res.gabinetes.append(GabineteRetrato(
                fonte=self.id, lotacao_original=org, competencia=data_ref[:7],
                ref_parlamentar=f"gab:{normalizar_nome(m.group(1))}", data_referencia=data_ref,
                pessoas=len(valores), custo=sum(valores, Decimal("0")), procedencia=proc))

    def _vereadores(self, linhas, hashes, url, res: Resultado) -> None:
        if not linhas:
            raise PortalMudou("lista de vereadores veio vazia")
        col_nome = next((c for c in linhas[0] if c.startswith("NOME")), None)
        col_mat = next((c for c in linhas[0] if c.startswith("MATRICULA")), None)
        if not col_nome:
            raise PortalMudou(f"lista de vereadores sem coluna de nome: {sorted(linhas[0])}")
        for i, l in enumerate(linhas, start=1):
            proc = self.procedencia(url, hashes[l["_pagina"] - 1], f"página {l['_pagina']}, linha {i}")
            nome = l[col_nome].strip()
            mat = (l.get(col_mat) or "").strip() or None if col_mat else None
            res.pessoas.append(PessoaFonte(
                fonte=self.id, ref=f"mat:{mat}" if mat else f"nome:{normalizar_nome(nome)}", periodo="atual",
                nome=nome, matricula=mat, casa="cmc", extra={"colunas": sorted(k for k in l if k != "_pagina")},
                procedencia=proc))
