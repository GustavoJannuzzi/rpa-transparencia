"""Assembleia de Minas Gerais: verba indenizatória pela API oficial de dados abertos.

Sem navegador. O robots.txt do domínio libera só `/api/v2/`, `/api/ajuda/` e
`/documentacao/`, e o robô só chama `/api/v2/`. O caminho (visto em 26/11/2026):
- lista dos deputados da legislatura (os em exercício e os que exerceram mandato);
- para cada deputado, os meses com prestação de contas fechada (`/datas`);
- para cada mês, a verba por tipo de despesa, cada tipo com o total e as notas
  (`listaDetalheVerba`): data de emissão, CNPJ ou CPF do emitente, nome, número
  do documento, valor da despesa e valor reembolsado.

A conferência é a soma das notas de cada tipo contra o total que a própria API dá
para o tipo no mês. As datas vêm como {"@class": "sql-timestamp", "$": "2026-09-01"}.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ...modelo import Descoberta, ItemInventario, Pendencia, PessoaFonte, Resultado, TotalOficial
from ...nucleo.erros import PortalMudou
from ...nucleo.texto import ValorIlegivel, chave_hash, decimal_ponto
from ..assembleia import FonteAssembleia

CAMPOS_TIPO = {"codTipoDespesa", "descTipoDespesa", "valor", "listaDetalheVerba"}
CAMPOS_NOTA = {"valorReembolsado", "dataEmissao", "cpfCnpj", "nomeEmitente", "valorDespesa"}


def data_almg(v) -> str | None:
    """{"@class": "sql-timestamp", "$": "2026-09-01"} -> "2026-09-01"."""
    if isinstance(v, dict):
        v = v.get("$")
    return str(v)[:10] if v else None


def conferir_formato_mes(j: dict) -> list[dict]:
    if not isinstance(j, dict) or "list" not in j:
        raise PortalMudou("verba do mês da ALMG sem a lista de tipos de despesa")
    for t in j["list"]:
        faltam = CAMPOS_TIPO - set(t)
        if faltam:
            raise PortalMudou(f"tipo de despesa da ALMG sem os campos {sorted(faltam)}")
        for n in t["listaDetalheVerba"]:
            faltam = CAMPOS_NOTA - set(n)
            if faltam:
                raise PortalMudou(f"nota da ALMG sem os campos {sorted(faltam)}")
    return j["list"]


def lista_deputados(j) -> list[dict]:
    lista = j.get("list") if isinstance(j, dict) and "list" in j else (j.get("listaDeputado") if isinstance(j, dict) else j)
    if not isinstance(lista, list) or (lista and not {"id", "nome"} <= set(lista[0])):
        raise PortalMudou("lista de deputados da ALMG em outro formato")
    return lista


class Almg(FonteAssembleia):
    o_que_tem = "Verba indenizatória de cada deputado estadual, nota a nota, com o emitente e o CNPJ, e a soma de cada tipo no mês."

    @property
    def api(self) -> str:
        return self.ent.extra["api"]

    async def descobrir(self) -> Descoberta:
        leg = self.ent.extra["legislatura"]
        deputados: dict[int, dict] = {}
        totais: list[TotalOficial] = []
        for situacao in ("em_exercicio", "que_exerceram_mandato"):
            url = f"{self.api}/legislaturas/{leg}/deputados/{situacao}?formato=json"
            r, h = await self.baixar(url)
            lista = lista_deputados(r.json())
            totais.append(TotalOficial(fonte=self.id, escopo=f"legislatura-{leg}", metrica=f"deputados_{situacao}", valor=str(len(lista)),
                                       procedencia=self.procedencia(url, h)))
            for d in lista:
                deputados.setdefault(int(d["id"]), {**d, "situacao": situacao})
        itens = []
        for did, d in sorted(deputados.items()):
            url = f"{self.api}/prestacao_contas/verbas_indenizatorias/deputados/{did}/datas?formato=json"
            r, _ = await self.baixar(url)
            j = r.json()
            datas = j.get("listaFechamentoVerba") if isinstance(j, dict) else None
            if datas is None:
                raise PortalMudou("resposta de /datas da ALMG sem listaFechamentoVerba")
            meses: dict[int, list[int]] = {}
            for x in datas:
                ref = data_almg(x.get("dataReferencia"))
                if not ref:
                    continue
                ano, mes = int(ref[:4]), int(ref[5:7])
                if self.de <= ano <= self.ate:
                    meses.setdefault(ano, []).append(mes)
            for ano, ms in sorted(meses.items()):
                itens.append(ItemInventario(chave=f"verbas-{did}-{ano}", descricao=f"Verba de {d['nome']} em {ano}", periodo=str(ano),
                                            parametros={"deputado": did, "nome": d["nome"], "partido": d.get("partido"),
                                                        "situacao": d["situacao"], "ano": ano, "meses": sorted(set(ms))}))
        return Descoberta(itens=itens, totais=totais)

    async def coletar_item(self, item: ItemInventario) -> Resultado:
        p = item.parametros
        did, ano = int(p["deputado"]), int(p["ano"])
        ref = f"id:{did}"
        res = Resultado()
        n_notas = 0
        tipos_ok = tipos = 0
        divergentes = []
        primeira = None
        for mes in p["meses"]:
            url = f"{self.api}/prestacao_contas/verbas_indenizatorias/deputados/{did}/{ano}/{mes}?formato=json"
            r, h = await self.baixar(url)
            for t in conferir_formato_mes(r.json()):
                tipos += 1
                soma = Decimal(0)
                lidas = 0
                for k, n in enumerate(t["listaDetalheVerba"]):
                    n_notas += 1
                    proc = self.procedencia(url, h, f"tipo {t['codTipoDespesa']}, nota {k + 1}")
                    primeira = primeira or proc
                    chave = chave_hash(self.id, did, ano, mes, t["codTipoDespesa"], n.get("id"), n.get("descDocumento"),
                                       n.get("cpfCnpj"), n.get("valorReembolsado"), k)
                    texto = f"{p['nome']}, {mes:02d}/{ano}, {t.get('descTipoDespesa')}, nota {k + 1}"
                    try:
                        valor = decimal_ponto(n["valorReembolsado"])
                        valor_despesa = decimal_ponto(n["valorDespesa"]) if n.get("valorDespesa") is not None else None
                    except ValorIlegivel as e:
                        res.pendencias.append(Pendencia(fonte=self.id, chave=chave, motivo=f"valor ilegível: {e}", texto_original=texto, procedencia=proc))
                        continue
                    soma += valor
                    lidas += 1
                    emissao = data_almg(n.get("dataEmissao"))
                    try:
                        quando = date.fromisoformat(emissao) if emissao else None
                    except ValueError:
                        quando = None
                    res.despesas.append(self.nota(
                        chave=chave, item=item.chave, ref=ref, nome=p["nome"], data=quando, competencia=f"{ano}-{mes:02d}",
                        categoria=(t.get("descTipoDespesa") or "").strip(), documento=n.get("cpfCnpj"), fornecedor=n.get("nomeEmitente"),
                        valor=valor, proc=proc,
                        extra={"valor_despesa": str(valor_despesa) if valor_despesa is not None else None,
                               "documento": n.get("descDocumento"), "cod_tipo": t.get("codTipoDespesa"),
                               "total_do_tipo_no_mes": str(t.get("valor"))}))
                try:
                    total_tipo = decimal_ponto(t["valor"])
                except ValorIlegivel:
                    total_tipo = None
                if total_tipo is not None and total_tipo == soma and lidas == len(t["listaDetalheVerba"]):
                    tipos_ok += 1
                else:
                    divergentes.append(f"{mes:02d}/{ano} {t.get('descTipoDespesa')}: total {t.get('valor')} × notas {soma}")
                    res.totais.append(TotalOficial(
                        fonte=self.id, escopo=f"{did}-{ano}-{mes:02d}-{t['codTipoDespesa']}", metrica="soma_do_tipo_diverge", valor="diverge",
                        texto_original=f"total do tipo na API {t.get('valor')}; soma das notas {soma}", procedencia=self.procedencia(url, h)))
        assert primeira is not None or n_notas == 0
        proc_item = primeira or self.procedencia(f"{self.api}/prestacao_contas/verbas_indenizatorias/deputados/{did}/datas", "")
        res.totais.append(TotalOficial(fonte=self.id, escopo=f"verbas-{did}-{ano}", metrica="linhas_na_origem", valor=str(n_notas),
                                       texto_original=f"{len(p['meses'])} meses", procedencia=proc_item))
        res.totais.append(TotalOficial(fonte=self.id, escopo=f"verbas-{did}-{ano}", metrica="tipos_que_fecham", valor=f"{tipos_ok}/{tipos}",
                                       texto_original="; ".join(divergentes)[:500] or None, procedencia=proc_item))
        res.pessoas.append(PessoaFonte(fonte=self.id, ref=ref, periodo=str(ano), nome=p["nome"], partido=p.get("partido"), uf="MG",
                                       casa=self.ent.casa, matricula=str(did),
                                       extra={"situacao_na_lista": p.get("situacao"), "partido_de": "lista de deputados da legislatura na API"},
                                       procedencia=proc_item))
        return res
