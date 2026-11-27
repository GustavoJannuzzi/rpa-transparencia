"""Assembleia de Goiás: a verba indenizatória, nota a nota, pela tela do app AngularJS.

O que a casa publica, visto em 26/11/2026:
- o dado aberto oficial (`api/transparencia/verbas_indenizatorias.json?ano=&mes=&todos=true`,
  documentado na página de dados abertos) só tem o TOTAL do mês por deputado
  (apresentado e indenizado), sem fornecedor;
- o detalhe com fornecedor e CNPJ só existe na tela: a rota
  `gestao-parlamentar/verba-indenizatoria/exibir/{deputado}/{ano}/{mes}` do app, que,
  ao abrir, pede ao servidor `.../verbas_indenizatorias/exibir?ano=&deputado_id=&mes=`
  (24 grupos de despesa, com subgrupos e os lançamentos: fornecedor, CNPJ ou CPF,
  data, número do documento, valor apresentado e valor indenizado).

O robô baixa o dado aberto do mês (a lista de deputados e o total oficial de cada
um), abre a rota de cada deputado no navegador e lê a resposta que a própria tela
recebe, em vez de chamar a URL interna por conta própria. A conferência é em três
níveis: os lançamentos somam o grupo, os grupos somam o total da tela, e o total da
tela é o do dado aberto, apresentado e indenizado. O valor publicado é o indenizado
(o apresentado e a glosa ficam ao lado).
"""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal

from ...modelo import Descoberta, ItemInventario, Pendencia, PessoaFonte, Resultado, TotalOficial
from ...nucleo.banco import agora
from ...nucleo.erros import FalhaTransitoria, PortalMudou
from ...nucleo.evidencia import guardar_original
from ...nucleo.texto import ValorIlegivel, chave_hash, decimal_ponto
from ..assembleia_tela import Conferencias, FonteAssembleiaTela

API = "https://transparencia.al.go.leg.br/api/transparencia/verbas_indenizatorias"
CAMPOS_LANCAMENTO = {"nome", "cnpj_cpf", "data", "numero", "valor_apresentado", "valor_indenizado"}


def sem_numero(descricao: str) -> str:
    """'02 -  COMUNICAÇÃO, TELEFONE E DADOS' -> 'COMUNICAÇÃO, TELEFONE E DADOS'."""
    return re.sub(r"\s+", " ", re.sub(r"^\s*\d+\s*-\s*", "", descricao or "")).strip()


def ler_exibir(j: dict) -> dict:
    """A resposta que a tela do deputado no mês recebe: grupos, subgrupos e lançamentos."""
    if not isinstance(j, dict) or not {"grupos", "valor_indenizado", "valor_apresentado", "deputado"} <= set(j):
        raise PortalMudou("a resposta do detalhe da ALEGO veio em outro formato")
    grupos = []
    for g in j["grupos"]:
        lanc = []
        for s in g.get("subgrupos") or []:
            for l in s.get("lancamentos") or []:
                f = l.get("fornecedor") or {}
                faltam = CAMPOS_LANCAMENTO - set(f)
                if faltam:
                    raise PortalMudou(f"lançamento da ALEGO sem os campos {sorted(faltam)}")
                lanc.append({**f, "subgrupo": sem_numero(s.get("descricao") or "")})
        grupos.append({"descricao": g["descricao"], "nome": sem_numero(g["descricao"]), "apresentado": g.get("valor_apresentado"),
                       "indenizado": g.get("valor_indenizado"), "lancamentos": lanc})
    return {"deputado": j["deputado"], "apresentado": j["valor_apresentado"], "indenizado": j["valor_indenizado"], "grupos": grupos}


def _dec(v) -> Decimal:
    return decimal_ponto(0 if v in (None, "") else v)


def data_iso(v: str | None) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


class Alego(FonteAssembleiaTela):
    inicio = "https://transparencia.al.go.leg.br/gestao-parlamentar/verba-indenizatoria"
    o_que_tem = ("Verba indenizatória de cada deputado estadual, nota a nota, com o fornecedor e o CNPJ, lida na tela do app (o dado "
                 "aberto da casa só tem o total do mês, e serve de conferência).")

    async def _aberto(self, ano: int, mes: int) -> tuple[list[dict], str, str]:
        url = f"{API}.json?ano={ano}&mes={mes}&todos=true"
        r, h = await self.baixar(url)
        j = r.json()
        if not isinstance(j, list) or (j and not {"deputado", "valor_indenizado", "valor_apresentado"} <= set(j[0])):
            raise PortalMudou("o dado aberto da verba da ALEGO mudou de formato")
        return j, url, h

    async def descobrir(self) -> Descoberta:
        itens, totais = [], []
        hoje = agora()[:7]
        for ano in range(self.de, self.ate + 1):
            for mes in range(1, 13):
                if f"{ano}-{mes:02d}" > hoje:
                    break
                lista, url, h = await self._aberto(ano, mes)
                if not lista:
                    continue
                totais.append(TotalOficial(fonte=self.id, escopo=f"verbas-{ano}-{mes:02d}", metrica="deputados_no_dado_aberto",
                                           valor=str(len(lista)), procedencia=self.procedencia(url, h)))
                itens.append(ItemInventario(chave=f"verbas-{ano}-{mes:02d}", descricao=f"Verba indenizatória de {mes:02d}/{ano}", periodo=str(ano),
                                            parametros={"ano": ano, "mes": mes, "deputados": len(lista)}))
        return Descoberta(itens=itens, totais=totais)

    async def _tela_do_deputado(self, did: int, ano: int, mes: int) -> tuple[dict, str, str]:
        """Abre a rota do deputado no mês e lê a resposta que a tela pede ao servidor."""
        assert self.pagina is not None
        rota = f"{self.inicio}/exibir/{did}/{ano}/{mes}"
        await self.educacao.verificar_robots(rota, self.http)
        alvo = f"/verbas_indenizatorias/exibir?ano={ano}&deputado_id={did}&mes={mes}"
        async with self.educacao.vez(self.inicio):
            try:
                async with self.pagina.expect_response(lambda r: alvo in r.url, timeout=self.timeout_resposta) as info:
                    await self.pagina.goto(rota, wait_until="domcontentloaded")
                r = await info.value
            except Exception as e:
                raise FalhaTransitoria(f"a tela do deputado {did} em {mes:02d}/{ano} não carregou ({type(e).__name__})") from e
        if r.status >= 500 or r.status == 429:
            raise FalhaTransitoria(f"HTTP {r.status} em {r.url}")
        corpo = await r.body()
        h = guardar_original(self.con, self.id, corpo, r.url, "json")
        try:
            j = json.loads(corpo)
        except ValueError as e:
            raise FalhaTransitoria("o detalhe veio sem JSON") from e
        return j, r.url, h

    async def coletar_item(self, item: ItemInventario) -> Resultado:
        p = item.parametros
        ano, mes = int(p["ano"]), int(p["mes"])
        res = Resultado()
        conf = Conferencias(self.id, item.chave)
        lista, url_aberto, h_aberto = await self._aberto(ano, mes)
        proc_aberto = self.procedencia(url_aberto, h_aberto, f"dado aberto de {mes:02d}/{ano}")
        n_notas = 0
        for d in lista:
            did, nome = int(d["deputado"]["id"]), d["deputado"]["nome"]
            ref = f"id:{did}"
            j, url, h = await self._tela_do_deputado(did, ano, mes)
            det = ler_exibir(j)
            if int(det["deputado"]["id"]) != did:
                raise PortalMudou(f"a tela do deputado {did} trouxe o deputado {det['deputado']['id']}")
            escopo = f"{did}-{ano}-{mes:02d}"
            soma_i = soma_a = Decimal(0)
            lidas = n_mes = 0
            grupos_ok = True
            for g in det["grupos"]:
                soma_g = Decimal(0)
                for k, l in enumerate(g["lancamentos"]):
                    n_notas += 1
                    n_mes += 1
                    proc = self.procedencia(url, h, f"{g['descricao']}, lançamento {k + 1}")
                    chave = chave_hash(self.id, did, ano, mes, g["descricao"], l["subgrupo"], l["numero"], l["cnpj_cpf"], l["valor_indenizado"], k)
                    try:
                        indenizado = _dec(l["valor_indenizado"])
                        apresentado = _dec(l["valor_apresentado"])
                    except ValorIlegivel as e:
                        res.pendencias.append(Pendencia(fonte=self.id, chave=chave, motivo="valor ilegível",
                                                        texto_original=f"{nome} {mes:02d}/{ano} {g['descricao']}: {e}", procedencia=proc))
                        continue
                    soma_g += indenizado
                    soma_i += indenizado
                    soma_a += apresentado
                    lidas += 1
                    res.despesas.append(self.nota(
                        chave=chave, item=item.chave, ref=ref, nome=nome, data=data_iso(l["data"]), competencia=f"{ano}-{mes:02d}",
                        categoria=g["nome"], documento=l["cnpj_cpf"], fornecedor=l["nome"], valor=indenizado, proc=proc,
                        extra={"subgrupo": l["subgrupo"], "numero": l["numero"], "valor_apresentado": str(apresentado),
                               "glosa": str(apresentado - indenizado), "escopos_conferencia": [escopo]}))
                if _dec(g["indenizado"]) != soma_g:
                    grupos_ok = False
            aberto_i, aberto_a = _dec(d["valor_indenizado"]), _dec(d["valor_apresentado"])
            conf.conferir(escopo, _dec(det["indenizado"]), soma_i, self.procedencia(url, h, "total do mês na tela"),
                          f"{nome} {mes:02d}/{ano}, total indenizado da tela × soma dos lançamentos", lidas_todas=lidas == n_mes,
                          outra=(grupos_ok and aberto_i == soma_i and aberto_a == soma_a,
                                 f"dado aberto: indenizado {aberto_i}, apresentado {aberto_a}; lançamentos: apresentado {soma_a}"
                                 + ("" if grupos_ok else "; algum grupo não soma os seus lançamentos")))
            partido = (det["deputado"] or {}).get("partido") or None
            res.pessoas.append(PessoaFonte(fonte=self.id, ref=ref, periodo=str(ano), nome=nome, partido=partido, uf="GO", casa=self.ent.casa,
                                           matricula=str(did), extra={"partido_de": "partido do deputado na resposta da tela"},
                                           procedencia=proc_aberto))
        conf.fechar(res, n_notas, proc_aberto, f"{len(lista)} deputados no dado aberto")
        # o mesmo deputado em vários meses do ano: fica um registro por ano (o do último mês)
        return res
