"""Elotech (Oxy e eloweb): um adaptador para qualquer câmara que usa o portal.

O portal publica uma API sem chave ("para consumo automatizado a partir de
sistemas externos"); a tela chama os mesmos serviços com os cabeçalhos `entidade`
e `exercicio`. Onde há API, não se usa navegador. Servidores é endpoint
documentado; diárias é o mesmo serviço que a tela de diárias chama, fora do
Swagger, e o teste de contrato avisa se mudar.

Uma instalação atende várias entidades (Prefeitura, Câmara, autarquias), cada
uma com um número. A entidade de cada câmara vem de `entidades.toml`, e o
`descobrir` confere o número e o CNPJ na lista de entidades da própria
instalação antes de coletar qualquer coisa.

O que muda de uma câmara para outra e o adaptador trata:
- o cargo da diária ("Vereador", "VEREADOR", "Presidente Da Camara", vazio);
- diária sem cargo: o nome só fica se estiver, igual, no cadastro de vereadores
  do mesmo ano da mesma câmara; senão é descartado na leitura e a linha vai para
  revisão ("a fonte não informa o cargo");
- a lotação, que em algumas câmaras diz de qual vereador é o gabinete
  ("Gab. Ver. Fulano") e em outras não ("Gabinete de Vereador");
- matrícula ausente na diária (então o vereador é ligado pelo nome);
- 0 diárias no ano: a fonte publica zero registros, o que é diferente de não
  publicar; a plataforma diz "nenhuma diária publicada", nunca R$ 0,00.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from decimal import Decimal

from ... import config
from ...de_para import eh_cargo_parlamentar
from ...entidades import EntidadeElotech
from ...modelo import (
    Descoberta,
    Despesa,
    GabineteRetrato,
    ItemInventario,
    Pendencia,
    PessoaFonte,
    Remuneracao,
    Resultado,
    SistemaOrigem,
    TotalOficial,
)
from ...nucleo.banco import agora
from ...nucleo.erros import PortalMudou
from ...nucleo.texto import ValorIlegivel, apelido_entre_parenteses, chave_hash, decimal_ponto, normalizar_nome, so_digitos
from ..base import Fonte

# Campos que toda diária tem. Os outros (matrícula, nome, anulação) a API omite quando
# vazios; o cargo também (visto em Umuarama, 2023), e aí vale como cargo vazio.
CAMPOS_DIARIA = {"dataSaida", "valorEmpenho"}
CAMPOS_SERVIDOR = {"matricula", "nome"}
RE_CARGO_COM_MATRICULA = re.compile(r"^(.*\S)\s*/\s*(\d{3,6})$")
# "GAB. VER. NOME CIVIL (NOME PARLAMENTAR)" em Curitiba, "Gab. Ver. Nome" em Ponta Grossa
RE_GABINETE = re.compile(r"^GAB\.?\s*VER\.?\s*(.+)$", re.I)
# natureza do vínculo no cadastro de pessoal de quem tem mandato
NATUREZAS_PARLAMENTAR = {"VEREADOR", "VEREADORA", "PRESIDENTE CAMARA", "PRESIDENTE DA CAMARA"}


def cabecalhos(entidade: int, ano: int) -> dict[str, str]:
    return {"entidade": str(entidade), "exercicio": str(ano), "Accept": "application/json"}


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


def eh_natureza_parlamentar(natureza: str | None) -> bool:
    return normalizar_nome(natureza) in NATUREZAS_PARLAMENTAR


class ElotechAPI(Fonte):
    grupo = "elotech"
    ua = config.UA_ROBO

    def __init__(self, ent: EntidadeElotech) -> None:
        self.ent = ent
        self.id = ent.fonte
        self.sistema = SistemaOrigem(
            fonte=ent.fonte, casa=ent.casa, sistema="Portal da Transparência Elotech", fornecedor="Elotech", modo="api",
            cobre_de=ent.de, cobre_ate=ent.ate, endereco=ent.tela,
            o_que_tem=(f"Diárias de {ent.de} a {ent.ate} e o cadastro de pessoal da Câmara de {ent.municipio} "
                       "(vereadores e subsídio; servidores só em totais)."),
        )
        # o texto livre do motivo da viagem pode citar servidor pelo nome; só Curitiba,
        # revisada linha a linha na fase 1, publica o motivo
        self.motivo_livre = ent.fonte == "cmc_elotech"
        self._paginas_servidores: dict[int, list[tuple[str, str, dict]]] = {}
        super().__init__()

    @property
    def api(self) -> str:
        return self.ent.api

    def _cab(self, ano: int) -> dict[str, str]:
        return cabecalhos(self.ent.entidade, ano)

    # ---------------------------------------------------------------- descobrir
    async def _conferir_entidade(self) -> None:
        url = f"{self.api}/api/entidades"
        r, _ = await self.baixar(url, headers={"Accept": "application/json"})
        lista = r.json()
        if not isinstance(lista, list):
            raise PortalMudou("a lista de entidades do Elotech veio em outro formato")
        achada = next((e for e in lista if str(e.get("id")) == str(self.ent.entidade)), None)
        if achada is None:
            raise PortalMudou(f"a entidade {self.ent.entidade} não está mais na instalação {self.ent.host}")
        if so_digitos(achada.get("cnpj")) != so_digitos(self.ent.cnpj):
            raise PortalMudou(f"a entidade {self.ent.entidade} de {self.ent.host} tem outro CNPJ ({achada.get('cnpj')}); "
                              "a configuração aponta para a Câmara errada")

    async def _anos(self) -> list[int]:
        r, _ = await self.baixar(f"{self.api}/api/exercicios/entidade/{self.ent.entidade}")
        anos = set()
        for x in r.json():
            ident = x.get("id") if isinstance(x.get("id"), dict) else x
            ent = ident.get("entidade")
            if isinstance(ent, dict) and str(ent.get("id")) != str(self.ent.entidade):
                continue  # exercício de outra entidade da mesma instalação
            ex = ident.get("exercicio")
            if ex:
                anos.add(int(ex))
        if not anos:
            raise PortalMudou("lista de exercícios do Elotech veio vazia ou em outro formato")
        # o exercício do ano seguinte às vezes já está aberto (visto em Foz do Iguaçu, nov/2026)
        teto = max(self.ent.ate, int(agora()[:4]))
        return sorted(a for a in anos if self.ent.de <= a <= teto)

    async def descobrir(self) -> Descoberta:
        await self._conferir_entidade()
        anos = await self._anos()
        itens: list[ItemInventario] = []
        totais: list[TotalOficial] = []
        for ano in anos:
            url = f"{self.api}/api/diarias?exercicio={ano}&dataInicial={ano}-01-01&dataFinal={ano}-12-31&page=0&size=1"
            r, h = await self.baixar(url, headers=self._cab(ano), aceitar=(400,))
            j = r.json()
            if r.status_code == 400:
                # visto em Renascença: o exercício aparece na lista, mas a contabilidade da
                # Câmara não tem esse ano ("Exercício não está selecionado ou não existe")
                if "exerc" not in str(j.get("message", "")).lower():
                    raise PortalMudou(f"diárias de {ano}: HTTP 400 inesperado ({str(j.get('message'))[:120]})")
                totais.append(TotalOficial(fonte=self.id, escopo=f"diarias-{ano}", metrica="exercicio_indisponivel", valor="sim",
                                           texto_original=str(j.get("message"))[:200], procedencia=self.procedencia(url, h)))
                continue
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
            url = f"{self.api}{caminho}&page={pagina}&size={tam}"
            r, h = await self.baixar(url, headers=self._cab(ano))
            j = r.json()
            if "content" not in j:
                raise PortalMudou(f"resposta sem 'content' em {caminho}")
            yield url, h, j
            if j.get("last", True):
                break
            pagina += 1

    async def _servidores_do_ano(self, ano: int) -> list[tuple[str, str, dict]]:
        """Páginas do cadastro de pessoal do ano, lidas uma vez por rodada."""
        if ano not in self._paginas_servidores:
            caminho = f"/api/servidores?entidade={self.ent.entidade}&exercicio={ano}&estagioVigente=true&admissaoExcepcional=false"
            paginas = []
            async for url, h, j in self._paginas(caminho, ano, 1000):
                conferir_formato_servidores(j["content"])
                paginas.append((url, h, j))
            self._paginas_servidores[ano] = paginas
        return self._paginas_servidores[ano]

    async def _vereadores_do_ano(self, ano: int) -> set[str]:
        nomes = set()
        for _url, _h, j in await self._servidores_do_ano(ano):
            for x in j["content"]:
                if eh_natureza_parlamentar(x.get("descricaoNatureza")) and x.get("nome"):
                    nomes.add(normalizar_nome(x["nome"]))
        return nomes

    # ---------------------------------------------------------------- diárias
    async def _diarias(self, item: ItemInventario, ano: int) -> Resultado:
        res = Resultado()
        total_api = None
        vistos: dict[str, int] = {}
        vereadores: set[str] | None = None
        caminho = f"/api/diarias?exercicio={ano}&dataInicial={ano}-01-01&dataFinal={ano}-12-31"
        async for url, h, j in self._paginas(caminho, ano, 100):
            total_api = j.get("totalElements")
            conferir_formato_diarias(j["content"])
            for i, x in enumerate(j["content"]):
                if str(x.get("entidade", self.ent.entidade)) != str(self.ent.entidade):
                    raise PortalMudou(f"a API devolveu diária da entidade {x.get('entidade')} pedindo a {self.ent.entidade}")
                local = f"página {j.get('number', 0)}, registro {i + 1}"
                base = chave_hash(self.id, ano, x.get("empenho"), x.get("numeroLiquidacao"), x.get("matricula"),
                                  x.get("dataSaida"), x.get("valorDiarias"), x.get("noAto"))
                n = vistos.get(base, 0)
                vistos[base] = n + 1
                sem_cargo = not (x.get("cargo") or "").strip() and (x.get("nome") or "").strip()
                if sem_cargo and vereadores is None:
                    vereadores = await self._vereadores_do_ano(ano)
                res_item = self._uma_diaria(x, ano, item, chave_hash(base, n), self.procedencia(url, h, local), vereadores or set())
                (res.despesas if isinstance(res_item, Despesa) else res.pendencias).append(res_item)
                if isinstance(res_item, Despesa) and res_item.beneficiario_tipo == "parlamentar" and res_item.ref_parlamentar:
                    res.pessoas.append(PessoaFonte(
                        fonte=self.id, ref=res_item.ref_parlamentar, periodo=str(ano),
                        nome=res_item.nome_beneficiario or "", matricula=str(x.get("matricula") or "") or None,
                        casa=self.ent.casa, procedencia=res_item.procedencia))
        n_lidos = len(res.despesas) + len(res.pendencias)
        if total_api is not None and int(total_api) != n_lidos:
            raise PortalMudou(f"a API disse {total_api} diárias em {ano} e as páginas trouxeram {n_lidos}")
        return res

    def _uma_diaria(self, x: dict, ano: int, item: ItemInventario, chave: str, proc, vereadores: set[str] | None = None):
        cargo = (x.get("cargo") or "").strip()
        mat = str(x.get("matricula") or "").strip() or None
        nome = (x.get("nome") or "").strip() or None
        nota_mat = nota_cargo = None
        m = RE_CARGO_COM_MATRICULA.match(cargo)
        if m and not mat:
            # visto em Curitiba, 2018: cargo "Vereador/1083" e nenhum campo de matrícula
            cargo, mat = m.group(1), m.group(2)
            nota_mat = f"matrícula lida do campo cargo ('{x.get('cargo')}')"
        parlamentar = eh_cargo_parlamentar(cargo)
        if not cargo and nome and normalizar_nome(nome) in (vereadores or set()):
            # a fonte não informa o cargo, mas o nome está, igual, no cadastro de
            # vereadores do mesmo ano da mesma câmara
            parlamentar = True
            nota_cargo = "cargo vazio na fonte; o nome é o de um vereador no cadastro de pessoal da Câmara no mesmo ano"
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
            "nota_cargo": nota_cargo,
            "nota_valor": nota_valor,
            "cargo_vazio": not cargo,
        }
        destino = " / ".join(p for p in ((x.get("destino") or "").strip(), (x.get("uf") or "").strip()) if p)
        if self.motivo_livre:
            descricao = ((x.get("destino") or "") + (" — " + x["motivo"] if parlamentar and x.get("motivo") else "")).strip(" —") or None
        else:
            objetivo = (x.get("tipoObjetivoDiaria") or "").strip()
            descricao = " — ".join(p for p in (destino, objetivo) if p) or None
        return Despesa(
            chave=chave, fonte=self.id, item=item.chave, tipo="diaria_municipal", casa=self.ent.casa, ref_parlamentar=ref,
            beneficiario_tipo="parlamentar" if parlamentar else "servidor",
            nome_beneficiario=nome if parlamentar else None, cargo_original=cargo, data=data,
            competencia=f"{ano}-{comp_mes:02d}", ano=ano, categoria_original="Diária", valor=valor,
            documento_url=f"{self.ent.tela}/diarias",
            descricao=descricao if parlamentar else (destino or None),
            procedencia=proc, extra=extra,
        )

    # ---------------------------------------------------------------- pessoal
    async def _servidores(self, item: ItemInventario, ano: int, atual: bool) -> Resultado:
        res = Resultado()
        gab: dict[str, list[Decimal]] = defaultdict(list)
        gab_proc = None
        total = 0
        primeira = None
        hoje = agora()[:10]
        for url, h, j in await self._servidores_do_ano(ano):
            total = j.get("totalElements", total)
            primeira = primeira or self.procedencia(url, h, "totalElements")
            for i, x in enumerate(j["content"]):
                proc = self.procedencia(url, h, f"página {j.get('number', 0)}, registro {i + 1}")
                lot = (x.get("descricaoLotacao") or "").strip()
                if eh_natureza_parlamentar(x.get("descricaoNatureza")):
                    mat = str(x.get("matricula"))
                    res.pessoas.append(PessoaFonte(
                        fonte=self.id, ref=f"mat:{mat}", periodo=str(ano), nome=(x.get("nome") or "").strip(),
                        matricula=mat, casa=self.ent.casa,
                        extra={"situacao": x.get("situacao"), "admissao": x.get("dataAdmissao"),
                               "desligamento": x.get("dataDemissao"), "cargo": x.get("descricaoCargo"),
                               "natureza": x.get("descricaoNatureza")},
                        procedencia=proc))
                    if atual and (x.get("situacao") or "").upper() == "ATIVO" and x.get("remuneracao") is not None:
                        try:
                            valor_rem = decimal_ponto(x.get("remuneracao"))
                            # zero no cadastro (licença, suplente sem exercício) não é subsídio
                            # de R$ 0,00: a remuneração fica sem publicar para essa pessoa
                            if valor_rem > 0:
                                res.remuneracoes.append(Remuneracao(
                                    fonte=self.id, casa=self.ent.casa, ref_parlamentar=f"mat:{mat}", competencia=hoje[:7],
                                    data_referencia=hoje, valor=valor_rem,
                                    rotulo="remuneração no cadastro de pessoal", cargo_original=x.get("descricaoNatureza"),
                                    procedencia=proc))
                        except ValorIlegivel:
                            res.pendencias.append(Pendencia(
                                fonte=self.id, chave=chave_hash(self.id, "subsidio", ano, mat), motivo="remuneração do vereador ilegível",
                                texto_original=f"matrícula {mat}, remuneração {x.get('remuneracao')!r}", procedencia=proc))
                m = RE_GABINETE.match(lot)
                if m:
                    # A lotação diz quem é o vereador do gabinete.
                    res.pessoas.append(PessoaFonte(
                        fonte=self.id, ref=f"gab:{normalizar_nome(m.group(1))}", periodo=str(ano),
                        nome=re.sub(r"\s*\(.*\)\s*$", "", m.group(1)).strip(),
                        nome_parlamentar=apelido_entre_parenteses(m.group(1)), casa=self.ent.casa,
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
