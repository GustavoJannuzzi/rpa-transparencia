"""SAPL (Interlegis): sessões plenárias, presença, ausências justificadas e votos
nominais de uma câmara municipal, pela API pública do sistema (Django REST).

Mais de cem câmaras do PR usam o SAPL. O adaptador é um só, configurado por
entidade em `entidades.toml`; nada aqui sabe de município.

O robots.txt do SAPL pede Crawl-delay de 60 s para qualquer robô, e a coleta
respeita: um pedido por minuto em cada câmara (a `Educacao` lê o robots.txt antes
do primeiro pedido). Daí o desenho:

- cada pedido traz o máximo que a API devolve numa página (100 registros);
- a coleta tem uma janela, do `de` da entidade até a data de corte, que a
  primeira descoberta fixa e as seguintes reaproveitam; o que vem depois do corte
  fica para outra rodada, e a plataforma mostra a data de corte;
- cada item do inventário é um pedido (uma página), com o filtro congelado na
  descoberta (data de corte e maior id), para a página N não mudar enquanto a
  coleta anda; a retomada pega só as páginas que faltam;
- o pedido sem paginação (`get_all`) não é usado: um teste em 26/11/2026 fez o
  servidor de Maringá responder 502 depois de 60 s.

O voto nominal não diz em que sessão foi: a API liga o voto à pauta, e a pauta à
sessão. O texto do próprio voto (`__str__`) traz o nome da sessão exatamente como
a lista de sessões o escreve ("50ª Sessão Ordinária da 2ª Sessão Legislativa da
19ª Legislatura"). O robô liga o voto à sessão por esse nome. Os votos vêm pela
data de registro (`data_hora`), que é um superconjunto da janela: voto antigo
migrado depois do início da janela vem junto e é separado como fora da janela,
pelo nome da sessão, nunca contado como lido.

Ninguém tem CPF nessa API (o cadastro de parlamentar não traz documento).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from ... import config
from ...entidades import EntidadeSapl
from ...modelo import Atividade, Descoberta, ItemInventario, Pendencia, PessoaFonte, Procedencia, Resultado, SistemaOrigem, TotalOficial
from ...nucleo.banco import agora
from ...nucleo.erros import PortalMudou
from ...nucleo.evidencia import guardar_original
from ..base import Fonte

POR_PAGINA = 100
REUSO_H = 12.0  # a descoberta refeita no mesmo dia não repete pedidos
# A página de um item tem o filtro congelado (data de corte e maior id): a resposta já
# gravada é a mesma que a API daria, e refazer um item não repete o pedido.
REUSO_ITEM_H = 0.0 if os.environ.get("RPA_SAPL_SEM_CACHE") else 24.0 * 30
# Choices do modelo JustificativaAusencia do SAPL (ausência numa matéria ou na sessão inteira).
TIPO_DE_AUSENCIA = {1: "Matéria", 2: "Sessão"}
CAMPOS = {
    "sessaoplenaria": {"id", "data_inicio", "tipo", "__str__"},
    "sessaoplenariapresenca": {"id", "sessao_plenaria", "parlamentar"},
    "justificativaausencia": {"id", "sessao_plenaria", "parlamentar", "tipo_ausencia", "data"},
    "votoparlamentar": {"id", "voto", "parlamentar", "__str__"},
    "parlamentar": {"id", "nome_completo", "nome_parlamentar"},
}
RE_VOTO = re.compile(r" - Votação: ")


def conferir_campos(recurso: str, registros: list[dict]) -> None:
    faltam = set()
    for r in registros:
        faltam |= CAMPOS[recurso] - set(r)
    if faltam:
        raise PortalMudou(f"{recurso} do SAPL sem os campos {sorted(faltam)}")


def sessao_do_voto(texto: str, nomes: dict[str, str]) -> str | None:
    """O id da sessão (da janela) cujo nome aparece no texto do voto, ou None.

    O texto é "Votação: Ordem: Ordem do Dia/Expediente: N - <matéria> em <sessão> -
    Votação: <resultado> - Parlamentar: <nome>". A matéria pode ter " em " e o
    resultado pode ter " - ", então a busca é pelo nome inteiro de cada sessão da
    janela, colado em " em " e em " - Votação: ".
    """
    for m in RE_VOTO.finditer(texto):
        antes = texto[: m.start()]
        # o nome da sessão termina onde começa " - Votação: "; procura o " em " que fecha com um nome conhecido
        i = antes.find(" em ")
        while i >= 0:
            sid = nomes.get(antes[i + 4:])
            if sid is not None:
                return sid
            i = antes.find(" em ", i + 1)
    return None


class Sapl(Fonte):
    grupo = "sapl"
    dado = "atividade"
    ua = config.UA_ROBO

    def __init__(self, ent: EntidadeSapl) -> None:
        self.ent = ent
        self.id = ent.fonte
        self.sistema = SistemaOrigem(
            fonte=ent.fonte, casa=ent.casa, sistema="SAPL (Interlegis)", fornecedor="Interlegis", modo="api",
            cobre_de=int(ent.de[:4]), cobre_ate=int(agora()[:4]), endereco=f"{ent.host}/sessao/pesquisar-sessao",
            o_que_tem=(f"Sessões plenárias, presença, ausências justificadas e votos nominais da Câmara de {ent.municipio}, "
                       f"desde {ent.de[8:10]}/{ent.de[5:7]}/{ent.de[:4]}."),
        )
        super().__init__()

    # ------------------------------------------------------------ pedidos
    def _url(self, caminho: str, **filtros) -> str:
        filtros = {k: v for k, v in filtros.items() if v is not None}
        return f"{self.ent.api}/{caminho}?{urlencode(filtros, safe=',:')}"

    async def _pedir(self, url: str, reusar_h: float = 0) -> tuple[dict, Procedencia]:
        """Um pedido à API, e a resposta gravada (comprimida) no cache da fonte.

        `reusar_h`: a descoberta reaproveita a resposta gravada há menos de tantas
        horas (refazer a descoberta não repete pedidos de um minuto cada).
        Com `RPA_SAPL_REPRODUZIR`, lê a resposta que uma coleta anterior gravou
        (mesmos bytes, mesmo hash, mesma data de coleta) em vez de pedir de novo: é
        assim que uma coleta longa feita num banco de trabalho entra no banco
        principal sem repetir horas de pedidos."""
        reproduzir = os.environ.get("RPA_SAPL_REPRODUZIR")
        nome = f"{hashlib.sha1(url.encode()).hexdigest()}.json.gz"
        destino = config.cache() / "sapl" / self.id / nome
        arq = Path(reproduzir) / self.id / nome if reproduzir else destino
        reusar = bool(reproduzir) or (reusar_h > 0 and destino.exists()
                                      and (time.time() - destino.stat().st_mtime) < reusar_h * 3600)
        if reproduzir and not arq.exists():
            raise PortalMudou(f"resposta não está na coleta gravada ({arq.name}): {url}")
        if reusar:
            gravado = json.loads(gzip.decompress(arq.read_bytes()))
            conteudo = gravado["corpo"].encode("utf-8")
            h = guardar_original(self.con, self.id, conteudo, url, "json")
            proc = Procedencia(fonte=self.id, url=url, hash_original=h, coletado_em=gravado["coletado_em"])
            return json.loads(conteudo), proc
        r, h = await self.baixar(url, headers={"Accept": "application/json"})
        coletado = agora()
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(gzip.compress(json.dumps({"url": url, "coletado_em": coletado, "corpo": r.text},
                                                     ensure_ascii=False).encode("utf-8")))
        try:
            j = r.json()
        except ValueError as e:
            raise PortalMudou(f"a API do SAPL não devolveu JSON em {url}") from e
        if not isinstance(j, dict) or "results" not in j or "pagination" not in j:
            raise PortalMudou(f"a API do SAPL mudou o formato da página em {url}")
        return j, Procedencia(fonte=self.id, url=url, hash_original=h, coletado_em=coletado)

    @staticmethod
    def _total(j: dict) -> int:
        t = j["pagination"].get("total_entries")
        if not isinstance(t, int):
            raise PortalMudou("a paginação do SAPL não traz total_entries")
        return t

    # ------------------------------------------------------------ descobrir
    def _corte_anterior(self) -> str | None:
        r = self.con.execute("SELECT valor FROM totais_oficiais WHERE fonte=? AND escopo='janela' AND metrica='corte'",
                             (self.id,)).fetchone()
        return r[0] if r else None

    async def descobrir(self) -> Descoberta:
        de = self.ent.de
        # a data de corte fica: a coleta longa anda dias sem mudar as páginas já pedidas
        corte = os.environ.get("RPA_SAPL_CORTE") or self._corte_anterior() or agora()[:10]
        itens: list[ItemInventario] = []
        totais: list[TotalOficial] = []

        def total(escopo: str, metrica: str, valor, texto: str, proc: Procedencia) -> None:
            totais.append(TotalOficial(fonte=self.id, escopo=escopo, metrica=metrica, valor=str(valor), texto_original=texto,
                                       procedencia=proc))

        # tipos de sessão e de justificativa: tabelas pequenas, vão nos parâmetros dos itens
        j, proc = await self._pedir(self._url("sessao/tiposessaoplenaria/", page_size=POR_PAGINA), REUSO_H)
        tipos_sessao = {str(t["id"]): t.get("nome") or t.get("__str__") for t in j["results"]}
        j, proc = await self._pedir(self._url("sessao/tipojustificativa/", page_size=POR_PAGINA), REUSO_H)
        tipos_just = {str(t["id"]): t.get("descricao") or t.get("__str__") for t in j["results"]}

        # sessões da janela: a lista inteira vem já na descoberta (são poucas páginas),
        # e cada página vira um item que grava o que esta descoberta leu
        sessoes: list[dict] = []
        pagina = 1
        while True:
            url = self._url("sessao/sessaoplenaria/", data_inicio__gte=de, data_inicio__lte=corte, o="id",
                            page_size=POR_PAGINA, page=pagina)
            j, proc = await self._pedir(url, REUSO_H)
            conferir_campos("sessaoplenaria", j["results"])
            if pagina == 1:
                n_sessoes = self._total(j)
                total("sessoes", "registros", n_sessoes, f"total_entries = {n_sessoes}", proc)
            regs = [{"id": s["id"], "data": s["data_inicio"], "nome": s["__str__"], "tipo": tipos_sessao.get(str(s["tipo"]), str(s["tipo"])),
                     "numero": s.get("numero")} for s in j["results"]]
            sessoes += regs
            itens.append(ItemInventario(chave=f"1-sessoes-p{pagina:03d}", descricao=f"Sessões da janela, página {pagina}",
                                        periodo=f"{de}/{corte}", parametros={"url": url, "hash": proc.hash_original,
                                                                            "coletado_em": proc.coletado_em, "sessoes": regs}))
            if not j["pagination"].get("next_page"):
                break
            pagina += 1
        if len(sessoes) != n_sessoes:
            raise PortalMudou(f"a lista de sessões diz {n_sessoes} e as páginas trouxeram {len(sessoes)}")

        # parlamentares (todos: a câmara tem poucas centenas, e o voto antigo cita quem já saiu)
        j, proc = await self._pedir(self._url("parlamentares/parlamentar/", o="id", page_size=1), REUSO_H)
        n_parl = self._total(j)
        total("parlamentares", "registros", n_parl, f"total_entries = {n_parl}", proc)
        for p in range(1, math.ceil(n_parl / POR_PAGINA) + 1):
            itens.append(ItemInventario(chave=f"0-parlamentares-p{p:03d}", descricao=f"Parlamentares, página {p}", periodo="todos",
                                        parametros={"url": self._url("parlamentares/parlamentar/", o="id", page_size=POR_PAGINA, page=p)}))

        # presença: por lotes de sessões que cabem numa página
        lote = self.ent.lote_presenca
        for k in range(0, len(sessoes), lote):
            grupo = sessoes[k:k + lote]
            ids = ",".join(str(s["id"]) for s in grupo)
            itens.append(ItemInventario(
                chave=f"2-presenca-l{k // lote + 1:03d}", descricao=f"Presença em {len(grupo)} sessões ({grupo[0]['data']} a {grupo[-1]['data']})",
                periodo=f"{grupo[0]['data']}/{grupo[-1]['data']}",
                parametros={"url": self._url("sessao/sessaoplenariapresenca/", sessao_plenaria__in=ids, o="id", page_size=POR_PAGINA),
                            "sessoes": {str(s["id"]): s["data"] for s in grupo}}))

        # ausências justificadas, pela data da ausência
        j, proc = await self._pedir(self._url("sessao/justificativaausencia/", data__gte=de, data__lte=corte, o="id", page_size=1), REUSO_H)
        n_just = self._total(j)
        total("ausencias", "registros", n_just, f"total_entries = {n_just}", proc)
        for p in range(1, math.ceil(n_just / POR_PAGINA) + 1):
            itens.append(ItemInventario(
                chave=f"3-ausencias-p{p:03d}", descricao=f"Ausências justificadas, página {p}", periodo=f"{de}/{corte}",
                parametros={"url": self._url("sessao/justificativaausencia/", data__gte=de, data__lte=corte, o="id",
                                             page_size=POR_PAGINA, page=p), "tipos": tipos_just}))

        # votos nominais: registrados desde o início da janela, até o maior id visto na primeira descoberta
        maior_ant = self.con.execute("SELECT valor FROM totais_oficiais WHERE fonte=? AND escopo='votos' AND metrica='maior_id'",
                                     (self.id,)).fetchone()
        if maior_ant is None:
            j, proc = await self._pedir(self._url("sessao/votoparlamentar/", data_hora__gte=de, o="-id", page_size=1), REUSO_H)
            maior = j["results"][0]["id"] if j["results"] else 0
            total("votos", "maior_id", maior, "id do voto mais recente na descoberta", proc)
        else:
            maior = int(maior_ant[0])
        filtro_votos = {"data_hora__gte": de, "id__lte": maior, "o": "id"}
        j, proc = await self._pedir(self._url("sessao/votoparlamentar/", **filtro_votos, page_size=1), REUSO_H)
        n_votos = self._total(j) if maior else 0
        total("votos", "registros", n_votos, f"total_entries = {n_votos} (votos registrados desde {de}, até o id {maior})", proc)
        for p in range(1, math.ceil(n_votos / POR_PAGINA) + 1):
            itens.append(ItemInventario(chave=f"4-votos-p{p:04d}", descricao=f"Votos nominais, página {p}", periodo=f"{de}/{corte}",
                                        parametros={"url": self._url("sessao/votoparlamentar/", **filtro_votos, page_size=POR_PAGINA, page=p)}))

        total("janela", "de", de, f"início da janela de coleta ({de})", proc)
        total("janela", "corte", corte, f"data de corte da coleta ({corte})", proc)
        total("janela", "pedidos", len(itens), "páginas no inventário (um pedido por minuto, pelo Crawl-delay de 60 s)", proc)
        return Descoberta(itens=itens, totais=totais)

    # ------------------------------------------------------------ coletar
    async def coletar_item(self, item: ItemInventario) -> Resultado:
        tipo = item.chave.split("-")[1]
        if tipo == "sessoes":
            return self._sessoes(item)
        j, proc = await self._pedir(item.parametros["url"], REUSO_ITEM_H)
        if tipo == "parlamentares":
            return self._parlamentares(item, j, proc)
        if tipo == "presenca":
            return await self._presenca(item, j, proc)
        if tipo == "ausencias":
            return self._ausencias(item, j, proc)
        if tipo == "votos":
            return self._votos(item, j, proc)
        raise PortalMudou(f"item desconhecido no inventário do SAPL: {item.chave}")

    def _competencia(self, d: str) -> str:
        return d[:7]

    def _sessoes(self, item: ItemInventario) -> Resultado:
        p = item.parametros
        proc = Procedencia(fonte=self.id, url=p["url"], hash_original=p["hash"], coletado_em=p["coletado_em"])
        res = Resultado()
        for s in p["sessoes"]:
            res.atividades.append(Atividade(
                chave=f"{self.id}:sessao:{s['id']}", fonte=self.id, casa=self.ent.casa, tipo="sessao", ref_sessao=str(s["id"]),
                data=date.fromisoformat(s["data"]), competencia=self._competencia(s["data"]), rotulo=s["tipo"],
                procedencia=proc.model_copy(update={"localizador": f"sessão {s['id']}"}), extra={"nome": s["nome"], "numero": s["numero"]}))
        return res

    def _parlamentares(self, item: ItemInventario, j: dict, proc: Procedencia) -> Resultado:
        conferir_campos("parlamentar", j["results"])
        res = Resultado()
        for p in j["results"]:
            nome = (p.get("nome_completo") or "").strip()
            apelido = (p.get("nome_parlamentar") or "").strip() or None
            if not nome and not apelido:
                continue
            res.pessoas.append(PessoaFonte(
                fonte=self.id, ref=f"sapl:{p['id']}", periodo="sapl", nome=nome or apelido or "", nome_parlamentar=apelido,
                casa=self.ent.casa, extra={"ativo": p.get("ativo")}, procedencia=proc.model_copy(update={"localizador": f"parlamentar {p['id']}"})))
        return res

    async def _presenca(self, item: ItemInventario, j: dict, proc: Procedencia) -> Resultado:
        datas: dict[str, str] = item.parametros["sessoes"]
        n_api = self._total(j)
        regs = list(j["results"])
        procs = [proc] * len(regs)
        url = item.parametros["url"]
        pagina = 1
        while j["pagination"].get("next_page"):  # lote maior que uma página (raro): segue pedindo
            pagina += 1
            j, proc_n = await self._pedir(f"{url}&page={pagina}", REUSO_ITEM_H)
            regs += j["results"]
            procs += [proc_n] * len(j["results"])
        conferir_campos("sessaoplenariapresenca", regs)
        if len(regs) != n_api:
            raise PortalMudou(f"a presença diz {n_api} registros e as páginas trouxeram {len(regs)}")
        res = Resultado(totais=[TotalOficial(fonte=self.id, escopo=item.chave, metrica="registros", valor=str(n_api),
                                             texto_original=f"total_entries = {n_api}", procedencia=proc)])
        for r, pr in zip(regs, procs, strict=True):
            sid = str(r["sessao_plenaria"])
            if sid not in datas:
                raise PortalMudou(f"a presença {r['id']} veio de uma sessão fora do filtro ({sid})")
            res.atividades.append(Atividade(
                chave=f"{self.id}:presenca:{r['id']}", fonte=self.id, casa=self.ent.casa, tipo="presenca",
                ref_parlamentar=f"sapl:{r['parlamentar']}", ref_sessao=sid, data=date.fromisoformat(datas[sid]),
                competencia=self._competencia(datas[sid]), procedencia=pr.model_copy(update={"localizador": f"presença {r['id']}"})))
        return res

    def _ausencias(self, item: ItemInventario, j: dict, proc: Procedencia) -> Resultado:
        conferir_campos("justificativaausencia", j["results"])
        tipos: dict[str, str] = item.parametros["tipos"]
        res = Resultado(totais=[TotalOficial(fonte=self.id, escopo=item.chave, metrica="registros", valor=str(len(j["results"])),
                                             texto_original=f"{len(j['results'])} justificativas na página", procedencia=proc)])
        for r in j["results"]:
            motivo = tipos.get(str(r["tipo_ausencia"]))
            loc = f"justificativa de ausência {r['id']}"
            if r.get("parlamentar") is None or not r.get("data"):
                res.pendencias.append(Pendencia(fonte=self.id, chave=f"{self.id}:ausencia:{r['id']}", motivo="ausência sem parlamentar ou sem data",
                                                texto_original=json.dumps(r, ensure_ascii=False)[:400],
                                                procedencia=proc.model_copy(update={"localizador": loc})))
                continue
            res.atividades.append(Atividade(
                chave=f"{self.id}:ausencia:{r['id']}", fonte=self.id, casa=self.ent.casa, tipo="ausencia",
                ref_parlamentar=f"sapl:{r['parlamentar']}", ref_sessao=str(r["sessao_plenaria"]) if r.get("sessao_plenaria") else None,
                data=date.fromisoformat(r["data"]), competencia=self._competencia(r["data"]),
                rotulo=motivo or "motivo não informado",
                procedencia=proc.model_copy(update={"localizador": loc}),
                extra={"ausencia": TIPO_DE_AUSENCIA.get(r.get("ausencia"), str(r.get("ausencia"))),
                       **({"observacao": r["observacao"][:200]} if r.get("observacao") else {})}))
        return res

    def _votos(self, item: ItemInventario, j: dict, proc: Procedencia) -> Resultado:
        conferir_campos("votoparlamentar", j["results"])
        # as sessões da janela já estão no banco (itens "1-sessoes", que vêm antes na ordem do inventário)
        nomes = {r[0]: r[1] for r in self.con.execute(
            "SELECT json_extract(extra, '$.nome'), ref_sessao FROM atividades WHERE fonte=? AND tipo='sessao'", (self.id,))}
        datas = {r[0]: r[1] for r in self.con.execute("SELECT ref_sessao, data FROM atividades WHERE fonte=? AND tipo='sessao'", (self.id,))}
        if not nomes:
            raise RuntimeError("as sessões da janela ainda não estão no banco: colete os itens 1-sessoes antes dos votos")
        res = Resultado()
        fora = 0
        for v in j["results"]:
            loc = f"voto {v['id']}"
            sid = sessao_do_voto(v["__str__"] or "", nomes)
            if sid is None:
                fora += 1  # voto registrado na janela, de sessão fora dela (dado antigo migrado), ou nome de sessão que não fecha
                continue
            if not v.get("voto") or v.get("parlamentar") is None:
                res.pendencias.append(Pendencia(fonte=self.id, chave=f"{self.id}:voto:{v['id']}", motivo="voto sem parlamentar ou sem valor",
                                                texto_original=(v["__str__"] or "")[:400], procedencia=proc.model_copy(update={"localizador": loc})))
                continue
            res.atividades.append(Atividade(
                chave=f"{self.id}:voto:{v['id']}", fonte=self.id, casa=self.ent.casa, tipo="voto", ref_parlamentar=f"sapl:{v['parlamentar']}",
                ref_sessao=sid, data=date.fromisoformat(datas[sid]), competencia=self._competencia(datas[sid]), rotulo=v["voto"].strip(),
                procedencia=proc.model_copy(update={"localizador": loc}),
                extra={"votacao": v.get("votacao")}))
        res.totais.append(TotalOficial(fonte=self.id, escopo=item.chave, metrica="registros", valor=str(len(j["results"])),
                                       texto_original=f"{len(j['results'])} votos na página", procedencia=proc))
        res.totais.append(TotalOficial(fonte=self.id, escopo=item.chave, metrica="fora_da_janela", valor=str(fora),
                                       texto_original="votos de sessão fora da janela", procedencia=proc))
        return res
