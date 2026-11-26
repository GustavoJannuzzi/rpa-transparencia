"""TSE, dados abertos: partido de cada vereador, na eleição que deu o mandato, em
cada município que a coleta cobre (Curitiba e as câmaras de `entidades.toml`).
Arquivo em lote, sem navegador.

Nenhum dos sistemas da Câmara traz partido. O que se publica é o partido NA
ELEIÇÃO; troca de partido durante o mandato não está nesta fonte, e a
plataforma diz isso.
"""

from __future__ import annotations

import csv
import io
import zipfile

from ... import config, entidades
from ...modelo import Candidatura, Descoberta, ItemInventario, Resultado, SistemaOrigem, TotalOficial
from ...nucleo.erros import PortalMudou
from ...nucleo.texto import normalizar_nome
from ..arquivos import baixar_arquivo
from ..base import Fonte

URL = "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_{ano}.zip"
ELEICOES = [2012, 2016, 2020, 2024]  # mandatos de 2013 a 2028

def municipios() -> dict[str, str]:
    """Nome normalizado do município (como o TSE escreve em NM_UE) -> nome para exibir."""
    return {normalizar_nome(e.municipio): e.municipio for e in entidades.elotech()} | {"CURITIBA": "Curitiba"}

COLUNAS = {"ANO_ELEICAO", "NM_TIPO_ELEICAO", "SG_UE", "NM_UE", "DS_CARGO", "SQ_CANDIDATO", "NM_CANDIDATO",
           "NM_URNA_CANDIDATO", "SG_PARTIDO", "DS_SIT_TOT_TURNO"}


def ler_candidaturas(linhas, ano: int, proc_fn, alvo: dict[str, str] | None = None) -> tuple[list[Candidatura], dict[str, int]]:
    """Candidaturas a vereador nos municípios de `alvo`; devolve também os eleitos por município."""
    alvo = alvo or {"CURITIBA": "Curitiba"}
    leitor = csv.DictReader(linhas, delimiter=";")
    faltam = COLUNAS - set(leitor.fieldnames or [])
    if faltam:
        raise PortalMudou(f"arquivo do TSE {ano} sem as colunas {sorted(faltam)}")
    out: list[Candidatura] = []
    eleitos: dict[str, int] = {}
    for i, l in enumerate(leitor, start=2):
        municipio = alvo.get(normalizar_nome(l["NM_UE"]))
        if municipio is None or normalizar_nome(l["DS_CARGO"]) != "VEREADOR":
            continue
        if "ORDINARIA" not in normalizar_nome(l["NM_TIPO_ELEICAO"]):
            continue
        sit = (l["DS_SIT_TOT_TURNO"] or "").strip()
        if normalizar_nome(sit).startswith("ELEITO"):
            eleitos[municipio] = eleitos.get(municipio, 0) + 1
        out.append(Candidatura(
            ano_eleicao=ano, municipio=normalizar_nome(municipio), cargo="VEREADOR", sq_candidato=l["SQ_CANDIDATO"],
            nome=l["NM_CANDIDATO"].strip(), nome_norm=normalizar_nome(l["NM_CANDIDATO"]),
            nome_urna=(l["NM_URNA_CANDIDATO"] or "").strip() or None, partido=l["SG_PARTIDO"].strip(),
            situacao=sit, procedencia=proc_fn(f"linha {i} do CSV do PR"),
        ))
    return out, eleitos


class Tse(Fonte):
    id = "tse"
    ua = config.UA_ROBO
    sistema = SistemaOrigem(
        fonte="tse", casa="cmc", sistema="TSE — dados abertos de candidaturas", fornecedor="Tribunal Superior Eleitoral",
        modo="arquivo", cobre_de=2012, cobre_ate=2024, endereco="https://dadosabertos.tse.jus.br/",
        o_que_tem="Partido de cada candidato a vereador nos municípios cobertos, nas eleições de 2012, 2016, 2020 e 2024.",
    )

    async def descobrir(self) -> Descoberta:
        alvo = sorted(municipios())
        return Descoberta(itens=[ItemInventario(chave=f"candidaturas-{a}", descricao=f"Candidaturas {a} (vereador, {len(alvo)} municípios do PR)",
                                                periodo=str(a), parametros={"ano": a, "municipios": alvo}) for a in ELEICOES])

    async def coletar_item(self, item: ItemInventario) -> Resultado:
        ano = int(item.parametros["ano"])
        url = URL.format(ano=ano)
        # arquivo de eleição passada muda raramente: cache de 30 dias
        caminho, h, _ = await baixar_arquivo(self, url, config.cache() / "tse" / f"consulta_cand_{ano}.zip", validade_h=24 * 30)
        with zipfile.ZipFile(caminho) as z:
            nome = next((n for n in z.namelist() if n.endswith(f"_{ano}_PR.csv")), None)
            if not nome:
                raise PortalMudou(f"zip do TSE {ano} sem o CSV do Paraná: {z.namelist()[:5]}")
            with z.open(nome) as f:
                cands, eleitos = ler_candidaturas(io.TextIOWrapper(f, encoding="latin-1", newline=""), ano,
                                                  lambda loc: self.procedencia(url, h, f"{nome}, {loc}"), municipios())
        if not any(c.municipio == "CURITIBA" for c in cands):
            raise PortalMudou(f"nenhuma candidatura a vereador em Curitiba no arquivo de {ano}")
        proc = self.procedencia(url, h, nome)
        totais = [TotalOficial(fonte=self.id, escopo=str(ano), metrica="candidaturas", valor=str(sum(1 for c in cands if c.municipio == "CURITIBA")),
                               procedencia=proc),
                  TotalOficial(fonte=self.id, escopo=str(ano), metrica="eleitos", valor=str(eleitos.get("Curitiba", 0)),
                               texto_original="DS_SIT_TOT_TURNO começando por ELEITO", procedencia=proc)]
        # os outros municípios: escopo "ano:município" (o de Curitiba fica como era)
        for mun, n in sorted(eleitos.items()):
            if mun != "Curitiba":
                totais.append(TotalOficial(fonte=self.id, escopo=f"{ano}:{mun}", metrica="eleitos", valor=str(n),
                                           texto_original="DS_SIT_TOT_TURNO começando por ELEITO", procedencia=proc))
        return Resultado(candidaturas=cands, totais=totais)
