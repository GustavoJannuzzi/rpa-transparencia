"""Câmara dos Deputados: API de Dados Abertos + arquivo anual da CEAP. Sem navegador.

A API serve para consulta (lista de deputados, conferência por amostra); o
arquivo anual, para carga. Raspar a tela de quem tem API seria erro de
julgamento: aqui não há robô de navegador.
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import date
from decimal import Decimal

from ... import config
from ...modelo import Descoberta, Despesa, ItemInventario, Pendencia, PessoaFonte, Resultado, SistemaOrigem, TotalOficial
from ...nucleo.erros import PortalMudou
from ...nucleo.texto import ValorIlegivel, chave_hash, decimal_ponto, documento_fornecedor
from ..arquivos import baixar_arquivo
from ..base import Fonte

API = "https://dadosabertos.camara.leg.br/api/v2"
ARQUIVO = "https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"
LEGISLATURA = 57
ANOS = [2023, 2024, 2025, 2026]
# Conferência por amostra: a API (consulta) contra o arquivo (carga), para estes
# deputados do Paraná, escolhidos pelos menores ids da legislatura (critério fixo).
TAMANHO_AMOSTRA = 4
COLUNAS = {"txNomeParlamentar", "ideCadastro", "sgUF", "sgPartido", "codLegislatura", "txtDescricao", "txtFornecedor",
           "txtCNPJCPF", "datEmissao", "vlrDocumento", "vlrLiquido", "numMes", "numAno", "urlDocumento", "ideDocumento"}


def ler_linha_ceap(l: dict, ano: int, item: str, fonte: str, proc, ocorrencias: dict) -> Despesa | Pendencia:
    base = chave_hash(fonte, ano, l.get("ideCadastro"), l.get("txNomeParlamentar"), l.get("ideDocumento"), l.get("txtNumero"),
                      l.get("datEmissao"), l.get("vlrDocumento"), l.get("vlrLiquido"), l.get("numParcela"),
                      l.get("txtDescricao"), l.get("txtCNPJCPF"), l.get("numMes"), l.get("txtTrecho"))
    n = ocorrencias.get(base, 0)
    ocorrencias[base] = n + 1
    chave = chave_hash(base, n)
    try:
        valor = decimal_ponto(l["vlrLiquido"])
        valor_doc = decimal_ponto(l["vlrDocumento"]) if l.get("vlrDocumento") else None
    except ValorIlegivel as e:
        return Pendencia(fonte=fonte, chave=chave, motivo=f"valor ilegível: {e}",
                         texto_original=f"{l.get('txNomeParlamentar')} / {l.get('txtDescricao')} / {l.get('vlrLiquido')!r}",
                         procedencia=proc)
    try:
        mes = int(l["numMes"])
        ano_linha = int(l["numAno"])
    except (TypeError, ValueError):
        return Pendencia(fonte=fonte, chave=chave, motivo="mês/ano ilegível", procedencia=proc,
                         texto_original=f"numMes={l.get('numMes')!r} numAno={l.get('numAno')!r}")
    data = None
    if l.get("datEmissao"):
        try:
            data = date.fromisoformat(l["datEmissao"][:10])
        except ValueError:
            data = None
    doc, tipo_doc = documento_fornecedor(l.get("txtCNPJCPF"))
    ide = (l.get("ideCadastro") or "").strip()
    url_doc = (l.get("urlDocumento") or "").strip() or None
    return Despesa(
        chave=chave, fonte=fonte, item=item, tipo="cota_federal",
        ref_parlamentar=ide or None, beneficiario_tipo="parlamentar" if ide else "lideranca",
        nome_beneficiario=(l.get("txNomeParlamentar") or "").strip() or None, cargo_original=None,
        data=data, competencia=f"{ano_linha}-{mes:02d}", ano=ano_linha,
        categoria_original=(l.get("txtDescricao") or "").strip(),
        fornecedor_doc=doc, fornecedor_tipo=tipo_doc, fornecedor_nome=(l.get("txtFornecedor") or "").strip() or None,
        valor=valor, documento_url=url_doc,
        descricao=(l.get("txtDescricaoEspecificacao") or "").strip() or None,
        procedencia=proc,
        extra={"partido_na_linha": (l.get("sgPartido") or "").strip() or None, "uf": (l.get("sgUF") or "").strip() or None,
               "valor_documento": str(valor_doc) if valor_doc is not None else None,
               "valor_glosa": (l.get("vlrGlosa") or None), "tipo_documento": l.get("indTipoDocumento"),
               "ano_arquivo": ano},
    )


class CamaraDeputados(Fonte):
    id = "camara_deputados"
    ua = config.UA_ROBO
    sistema = SistemaOrigem(
        fonte="camara_deputados", casa="camara-deputados", sistema="Dados Abertos da Câmara dos Deputados",
        fornecedor="Câmara dos Deputados", modo="api", cobre_de=2023, cobre_ate=2026,
        endereco="https://dadosabertos.camara.leg.br/",
        o_que_tem="Deputados da 57ª legislatura (API) e a cota parlamentar de 2023 a 2026 (arquivo anual).",
    )

    async def descobrir(self) -> Descoberta:
        url = f"{API}/deputados?idLegislatura={LEGISLATURA}&itens=1000&ordem=ASC&ordenarPor=id"
        r, h = await self.baixar(url, headers={"Accept": "application/json"})
        dados = r.json().get("dados")
        if not isinstance(dados, list) or not dados:
            raise PortalMudou("lista de deputados veio vazia ou em outro formato")
        ids = sorted({d["id"] for d in dados})
        pr = sorted({d["id"] for d in dados if d.get("siglaUf") == "PR"})
        amostra = pr[:TAMANHO_AMOSTRA]
        itens = [ItemInventario(chave=f"deputados-{LEGISLATURA}", descricao=f"Deputados da {LEGISLATURA}ª legislatura",
                                periodo=str(LEGISLATURA), parametros={"total": len(ids)})]
        itens += [ItemInventario(chave=f"ceap-{a}", descricao=f"Cota parlamentar {a} (arquivo anual)", periodo=str(a),
                                 parametros={"ano": a}) for a in ANOS]
        itens += [ItemInventario(chave=f"api-{i}-{a}", descricao=f"Conferência: API do deputado {i} em {a}", periodo=str(a),
                                 parametros={"ano": a, "deputado": i}) for i in amostra for a in ANOS]
        totais = [TotalOficial(fonte=self.id, escopo=f"deputados-{LEGISLATURA}", metrica="parlamentares", valor=str(len(ids)),
                               texto_original=f"ids distintos em /deputados?idLegislatura={LEGISLATURA}",
                               procedencia=self.procedencia(url, h))]
        return Descoberta(itens=itens, totais=totais)

    async def coletar_item(self, item: ItemInventario) -> Resultado:
        if item.chave.startswith("deputados-"):
            return await self._deputados(item)
        if item.chave.startswith("ceap-"):
            return await self._ceap(item, int(item.parametros["ano"]))
        return await self._api_amostra(item, int(item.parametros["deputado"]), int(item.parametros["ano"]))

    async def _deputados(self, item: ItemInventario) -> Resultado:
        url = f"{API}/deputados?idLegislatura={LEGISLATURA}&itens=1000&ordem=ASC&ordenarPor=id"
        r, h = await self.baixar(url, headers={"Accept": "application/json"})
        res = Resultado()
        for i, d in enumerate(r.json()["dados"]):
            for campo in ("id", "nome", "siglaPartido", "siglaUf"):
                if campo not in d:
                    raise PortalMudou(f"deputado sem o campo {campo}")
            # o mesmo id se repete quando o deputado troca de partido: cada partido é um período
            res.pessoas.append(PessoaFonte(
                fonte=self.id, ref=str(d["id"]), periodo=f"{LEGISLATURA}:{d['siglaPartido']}", nome=d["nome"],
                partido=d["siglaPartido"], uf=d["siglaUf"], casa="camara-deputados",
                extra={"foto": d.get("urlFoto"), "ordem_na_lista": i},
                procedencia=self.procedencia(url, h, f"registro {i + 1}")))
        return res

    async def _ceap(self, item: ItemInventario, ano: int) -> Resultado:
        url = ARQUIVO.format(ano=ano)
        caminho, h, _ = await baixar_arquivo(self, url, config.cache() / "ceap" / f"Ano-{ano}.csv.zip")
        res = Resultado()
        ocorr: dict[str, int] = {}
        total_linhas = 0
        with zipfile.ZipFile(caminho) as z:
            nome = z.namelist()[0]
            with z.open(nome) as f:
                leitor = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", newline=""), delimiter=";")
                faltam = COLUNAS - set(leitor.fieldnames or [])
                if faltam:
                    raise PortalMudou(f"arquivo da CEAP {ano} sem as colunas {sorted(faltam)}")
                for i, l in enumerate(leitor, start=2):
                    if l.get("codLegislatura") != str(LEGISLATURA):
                        continue
                    total_linhas += 1
                    d = ler_linha_ceap(l, ano, item.chave, self.id, self.procedencia(url, h, f"{nome}, linha {i}"), ocorr)
                    (res.despesas if isinstance(d, Despesa) else res.pendencias).append(d)
        proc = self.procedencia(url, h, nome)
        res.totais.append(TotalOficial(fonte=self.id, escopo=f"ceap-{ano}", metrica="linhas_no_arquivo", valor=str(total_linhas),
                                       texto_original=f"linhas da legislatura {LEGISLATURA} em {nome}", procedencia=proc))
        return res

    async def _api_amostra(self, item: ItemInventario, dep: int, ano: int) -> Resultado:
        pagina, n, soma = 1, 0, Decimal("0")
        h0 = url0 = None
        while True:
            url = f"{API}/deputados/{dep}/despesas?ano={ano}&itens=100&pagina={pagina}&ordem=ASC&ordenarPor=ano"
            r, h = await self.baixar(url, headers={"Accept": "application/json"})
            h0, url0 = h0 or h, url0 or url
            j = r.json()
            dados = j.get("dados")
            if dados is None:
                raise PortalMudou("resposta de despesas sem 'dados'")
            for d in dados:
                soma += decimal_ponto(d["valorLiquido"])
                n += 1
            if not any(l.get("rel") == "next" for l in j.get("links", [])):
                break
            pagina += 1
        proc = self.procedencia(url0, h0, f"{pagina} página(s)")
        return Resultado(totais=[
            TotalOficial(fonte=self.id, escopo=f"api-{dep}-{ano}", metrica="registros", valor=str(n), procedencia=proc),
            TotalOficial(fonte=self.id, escopo=f"api-{dep}-{ano}", metrica="valor_liquido", valor=str(soma), procedencia=proc),
        ])
