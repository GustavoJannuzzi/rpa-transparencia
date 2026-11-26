"""Câmara de Curitiba no Elotech (2017–2023 nas diárias; pessoal até hoje): API.

A Etapa 0 achou o serviço "Web Services" publicado pelo próprio portal, sem chave
("para consumo automatizado a partir de sistemas externos"). Onde há API, não se
usa navegador. Servidores é endpoint documentado; diárias é o mesmo serviço que a
tela de diárias chama, fora do Swagger, e o teste de contrato avisa se mudar.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from decimal import Decimal

from ... import config
from ...modelo import (Descoberta, Despesa, GabineteRetrato, ItemInventario, Pendencia, PessoaFonte, Resultado,
                       SistemaOrigem, TotalOficial)
from ...nucleo.banco import agora
from ...nucleo.erros import PortalMudou
from ...de_para import eh_cargo_parlamentar
from ..base import Fonte
from ...nucleo.texto import ValorIlegivel, apelido_entre_parenteses, chave_hash, decimal_ponto, normalizar_nome

API = "https://cmcuritiba.eloweb.net/portaltransparencia-api"
TELA = "https://cmcuritiba.eloweb.net/portaltransparencia/1"
ENTIDADE = "1"
ANO_INICIAL = 2017
# Campos que toda diária tem. Os outros (matrícula, nome, anulação) a API omite quando vazios.
CAMPOS_DIARIA = {"cargo", "dataSaida", "valorEmpenho"}
RE_CARGO_COM_MATRICULA = re.compile(r"^(.*\S)\s*/\s*(\d{3,6})$")
CAMPOS_SERVIDOR = {"matricula", "nome"}
RE_GABINETE = re.compile(r"^GAB\.?\s*VER\.?\s*(.+)$")


def _cabecalhos(ano: int) -> dict[str, str]:
    return {"entidade": ENTIDADE, "exercicio": str(ano), "Accept": "application/json"}


def conferir_formato_diarias(conteudo: list[dict]) -> None:
    for x in conteudo:
        faltam = CAMPOS_DIARIA - set(x)
        if faltam:
            raise PortalMudou(f"diária do Elotech sem os campos {sorted(faltam)}")


def conferir_formato_servidores(conteudo: list[dict]) -> None:
    for x in conteudo:
        faltam = CAMPOS_SERVIDOR - set(x)
        if faltam:
            raise PortalMudou(f"servidor do Elotech sem os campos {sorted(faltam)}")


class CmcElotechAPI(Fonte):
    id = "cmc_elotech"
    ua = config.UA_ROBO
    sistema = SistemaOrigem(
        fonte="cmc_elotech", casa="cmc", sistema="Portal da Transparência Elotech", fornecedor="Elotech",
        modo="api", cobre_de=2017, cobre_ate=2023, endereco=TELA,
        o_que_tem="Diárias de 2017 a 2023 e o quadro de pessoal com lotação por gabinete (atual).",
    )

    async def _anos(self) -> list[int]:
        r, _ = await self.baixar(f"{API}/api/exercicios/entidade/{ENTIDADE}")
        anos = set()
        for x in r.json():
            ex = (x.get("id") or {}).get("exercicio") if isinstance(x.get("id"), dict) else x.get("exercicio")
            if ex:
                anos.add(int(ex))
        if not anos:
            raise PortalMudou("lista de exercícios do Elotech veio vazia ou em outro formato")
        return sorted(a for a in anos if a >= ANO_INICIAL)

    async def descobrir(self) -> Descoberta:
        anos = await self._anos()
        itens: list[ItemInventario] = []
        totais: list[TotalOficial] = []
        for ano in anos:
            url = f"{API}/api/diarias?exercicio={ano}&dataInicial={ano}-01-01&dataFinal={ano}-12-31&page=0&size=1"
            r, h = await self.baixar(url, headers=_cabecalhos(ano))
            j = r.json()
            if "totalElements" not in j:
                raise PortalMudou("resposta de diárias sem totalElements")
            total = int(j["totalElements"])
            totais.append(TotalOficial(fonte=self.id, escopo=f"diarias-{ano}", metrica="registros", valor=str(total),
                                       texto_original=f"totalElements={total}", procedencia=self.procedencia(url, h)))
            if total:
                itens.append(ItemInventario(chave=f"diarias-{ano}", descricao=f"Diárias {ano}", periodo=str(ano),
                                            parametros={"ano": ano, "total": total}))
            itens.append(ItemInventario(chave=f"servidores-{ano}", descricao=f"Vereadores e gabinetes {ano}",
                                        periodo=str(ano), parametros={"ano": ano, "atual": ano == max(anos)}))
        return Descoberta(itens=itens, totais=totais)

    async def coletar_item(self, item: ItemInventario) -> Resultado:
        ano = int(item.parametros["ano"])
        if item.chave.startswith("diarias-"):
            return await self._diarias(item, ano)
        return await self._servidores(item, ano, bool(item.parametros.get("atual")))

    async def _paginas(self, caminho: str, ano: int, tam: int):
        pagina = 0
        while True:
            url = f"{API}{caminho}&page={pagina}&size={tam}"
            r, h = await self.baixar(url, headers=_cabecalhos(ano))
            j = r.json()
            if "content" not in j:
                raise PortalMudou(f"resposta sem 'content' em {caminho}")
            yield url, h, j
            if j.get("last", True):
                break
            pagina += 1

    async def _diarias(self, item: ItemInventario, ano: int) -> Resultado:
        res = Resultado()
        total_api = None
        vistos: dict[str, int] = {}
        caminho = f"/api/diarias?exercicio={ano}&dataInicial={ano}-01-01&dataFinal={ano}-12-31"
        async for url, h, j in self._paginas(caminho, ano, 100):
            total_api = j.get("totalElements")
            conferir_formato_diarias(j["content"])
            for i, x in enumerate(j["content"]):
                local = f"página {j.get('number', 0)}, registro {i + 1}"
                base = chave_hash(self.id, ano, x.get("empenho"), x.get("numeroLiquidacao"), x.get("matricula"),
                                  x.get("dataSaida"), x.get("valorDiarias"), x.get("noAto"))
                n = vistos.get(base, 0)
                vistos[base] = n + 1
                res_item = self._uma_diaria(x, ano, item, chave_hash(base, n), self.procedencia(url, h, local))
                (res.despesas if isinstance(res_item, Despesa) else res.pendencias).append(res_item)
                if isinstance(res_item, Despesa) and res_item.beneficiario_tipo == "parlamentar":
                    res.pessoas.append(PessoaFonte(
                        fonte=self.id, ref=res_item.ref_parlamentar, periodo=str(ano),
                        nome=res_item.nome_beneficiario or "", matricula=str(x.get("matricula") or "") or None,
                        casa="cmc", procedencia=res_item.procedencia))
        n_lidos = len(res.despesas) + len(res.pendencias)
        if total_api is not None and int(total_api) != n_lidos:
            raise PortalMudou(f"a API disse {total_api} diárias em {ano} e as páginas trouxeram {n_lidos}")
        return res

    def _uma_diaria(self, x: dict, ano: int, item: ItemInventario, chave: str, proc):
        cargo = (x.get("cargo") or "").strip()
        mat = str(x.get("matricula") or "").strip() or None
        nota_mat = None
        m = RE_CARGO_COM_MATRICULA.match(cargo)
        if m and not mat:
            # visto em 2018: cargo "Vereador/1083" e nenhum campo de matrícula
            cargo, mat = m.group(1), m.group(2)
            nota_mat = f"matrícula lida do campo cargo ('{x.get('cargo')}')"
        parlamentar = eh_cargo_parlamentar(cargo)
        nota_valor = None
        try:
            if "valorDiarias" not in x and x.get("quantidadeDiarias") == 0 and decimal_ponto(x.get("valorEmpenho")) == 0:
                # viagem sem diária (só passagem): a própria fonte diz 0 diárias e 0 empenhado
                x = {**x, "valorDiarias": 0}
                nota_valor = "viagem sem diária na fonte (quantidade 0, empenho 0); só passagem"
            valor = decimal_ponto(x.get("valorDiarias"))
            empenho = decimal_ponto(x.get("valorEmpenho"))
            anulado = decimal_ponto(x.get("valorAnulado") if x.get("valorAnulado") is not None else 0)
        except ValorIlegivel as e:
            return Pendencia(fonte=self.id, chave=chave, motivo=f"valor ilegível: {e}",
                             texto_original=f"empenho {x.get('displayEmpenho')}, cargo '{cargo}'", procedencia=proc)
        try:
            data = date.fromisoformat(x["dataSaida"]) if x.get("dataSaida") else None
        except ValueError:
            data = None
        nome = (x.get("nome") or "").strip() or None
        ref = None
        if parlamentar:
            ref = f"mat:{mat}" if mat else (f"nome:{normalizar_nome(nome)}" if nome else None)
        cancel = (x.get("situacaoCancelamento") or "").strip()
        marcas = []
        if cancel and "TOTAL" in cancel.upper():
            marcas.append("cancelada")
        elif cancel and "PARCIAL" in cancel.upper():
            marcas.append("cancelada_parcialmente")
        comp_mes = data.month if data and data.year == ano else None
        if comp_mes is None:
            return Pendencia(fonte=self.id, chave=chave, motivo=f"data de saída fora do exercício ({x.get('dataSaida')})",
                             texto_original=f"empenho {x.get('displayEmpenho')}, cargo '{cargo}'", procedencia=proc)
        extra = {
            "empenho": x.get("displayEmpenho"), "ato": x.get("noAto"), "data_ato": x.get("dataAto"),
            "data_retorno": x.get("dataRetorno"), "quantidade": x.get("quantidadeDiarias"),
            "valor_unitario": str(x.get("valorUnitario")) if x.get("valorUnitario") is not None else None,
            "valor_empenho": str(empenho), "valor_anulado": str(anulado),
            "situacao_cancelamento": cancel, "marcas": marcas,
            "consistencia": "ok" if empenho - anulado == valor or (marcas and anulado == empenho) else
                            f"diverge: empenho {empenho} − anulado {anulado} ≠ diárias {valor}",
            "transporte": str(x["valorPassagem"]) if x.get("valorPassagem") is not None else None,
            "hospedagem": str(x["valorHospedagem"]) if x.get("valorHospedagem") is not None else None,
            "meio_transporte": x.get("meioTransporte"),
            "nome_na_fonte": bool(nome),
            "nota_matricula": nota_mat,
            "nota_valor": nota_valor,
        }
        return Despesa(
            chave=chave, fonte=self.id, item=item.chave, tipo="diaria_municipal", ref_parlamentar=ref,
            beneficiario_tipo="parlamentar" if parlamentar else "servidor",
            nome_beneficiario=nome if parlamentar else None, cargo_original=cargo, data=data,
            competencia=f"{ano}-{comp_mes:02d}", ano=ano, categoria_original="Diária", valor=valor,
            documento_url=f"{TELA}/diarias",
            descricao=((x.get("destino") or "") + (" — " + x["motivo"] if parlamentar and x.get("motivo") else "")).strip(" —") or None,
            procedencia=proc, extra=extra,
        )

    async def _servidores(self, item: ItemInventario, ano: int, atual: bool) -> Resultado:
        res = Resultado()
        gab: dict[str, list[Decimal]] = defaultdict(list)
        gab_proc = None
        caminho = f"/api/servidores?entidade={ENTIDADE}&exercicio={ano}&estagioVigente=true&admissaoExcepcional=false"
        total = 0
        primeira = None
        async for url, h, j in self._paginas(caminho, ano, 1000):
            conferir_formato_servidores(j["content"])
            total = j.get("totalElements", total)
            primeira = primeira or self.procedencia(url, h, "totalElements")
            for i, x in enumerate(j["content"]):
                proc = self.procedencia(url, h, f"página {j.get('number', 0)}, registro {i + 1}")
                natureza = normalizar_nome(x.get("descricaoNatureza"))
                lot = (x.get("descricaoLotacao") or "").strip()
                if natureza == "VEREADOR":
                    mat = str(x.get("matricula"))
                    res.pessoas.append(PessoaFonte(
                        fonte=self.id, ref=f"mat:{mat}", periodo=str(ano), nome=(x.get("nome") or "").strip(),
                        matricula=mat, casa="cmc",
                        extra={"situacao": x.get("situacao"), "admissao": x.get("dataAdmissao"),
                               "desligamento": x.get("dataDemissao"), "cargo": x.get("descricaoCargo")},
                        procedencia=proc))
                m = RE_GABINETE.match(lot)
                if m:
                    # A lotação diz quem é o vereador do gabinete: "GAB. VER. NOME CIVIL (NOME PARLAMENTAR)".
                    res.pessoas.append(PessoaFonte(
                        fonte=self.id, ref=f"gab:{normalizar_nome(m.group(1))}", periodo=str(ano),
                        nome=re.sub(r"\s*\(.*\)\s*$", "", m.group(1)).strip(),
                        nome_parlamentar=apelido_entre_parenteses(m.group(1)), casa="cmc",
                        extra={"lotacao": lot}, procedencia=proc))
                    if atual and (x.get("situacao") or "").upper() == "ATIVO":
                        try:
                            gab[lot].append(decimal_ponto(x.get("remuneracao")))
                        except ValorIlegivel:
                            res.pendencias.append(Pendencia(
                                fonte=self.id, chave=chave_hash(self.id, "gab", ano, lot, i), motivo="remuneração ilegível",
                                texto_original=f"lotação '{lot}' (pessoa sem nome)", procedencia=proc))
                        gab_proc = proc
        if atual and gab:
            hoje = agora()[:10]
            for lot, valores in gab.items():
                m = RE_GABINETE.match(lot)
                res.gabinetes.append(GabineteRetrato(
                    fonte=self.id, lotacao_original=lot, competencia=hoje[:7],
                    ref_parlamentar=f"gab:{normalizar_nome(m.group(1))}" if m else None,
                    data_referencia=hoje, pessoas=len(valores), custo=sum(valores, Decimal("0")),
                    procedencia=gab_proc))
        res.totais.append(TotalOficial(fonte=self.id, escopo=f"servidores-{ano}", metrica="registros", valor=str(total),
                                       texto_original=f"totalElements={total}",
                                       procedencia=primeira))
        # pessoas repetidas (mesmo gabinete, várias pessoas) são deduplicadas pela chave do banco
        return res
