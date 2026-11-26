"""Assembleia de São Paulo: despesas de gabinete nos dados abertos. Sem navegador.

Um arquivo JSON só traz a série inteira, de 2002 até hoje (~160 MB em 26/11/2026).
O robô:
- pergunta antes (HEAD) a data e a etiqueta do arquivo, e só baixa de novo quando
  elas mudam; o arquivo fica no cache já comprimido;
- lê em fluxo, um registro por vez, sem carregar o arquivo inteiro na memória, e
  com os valores em Decimal exato desde a leitura do JSON;
- guarda só o período da coleta.

**Granularidade:** a ALESP publica a despesa já somada por fornecedor × tipo × mês
("agrupadas por tipo, por ano e por mês de despesa", diz a página do conjunto).
Cada linha é um agregado, não uma nota: não tem data nem número de documento, e a
plataforma mostra isso. O campo `cpf` (fornecedor pessoa física) não é gravado: o
documento fica mascarado, como na cota federal.
"""

from __future__ import annotations

import gzip
import io
import json
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

from ... import config
from ...modelo import Descoberta, ItemInventario, Pendencia, PessoaFonte, Resultado, TotalOficial
from ...nucleo.erros import PortalMudou
from ...nucleo.texto import ValorIlegivel, chave_hash, decimal_ponto
from ..arquivos import baixar_comprimido
from ..assembleia import FonteAssembleia

CAMPOS = {"id", "ano", "mes", "matricula", "deputado", "tipo", "fornecedor", "cnpj", "cpf", "valor"}


def registros(texto: io.TextIOBase, chave: str = "despesas") -> Iterator[dict]:
    """Os objetos da lista `chave` de um JSON grande, um por vez. O decodificador
    anda por um índice dentro de um buffer de ~1 MB, sem recortar a string a cada
    registro."""
    dec = json.JSONDecoder(parse_float=Decimal)
    buf = texto.read(1 << 20)
    marca = f'"{chave}"'
    i = buf.find(marca)
    if i < 0:
        raise PortalMudou(f"o arquivo não começa pela lista '{chave}'")
    pos = buf.index("[", i) + 1
    fim_arquivo = False
    while True:
        while pos < len(buf) and buf[pos] in " \r\n\t,":
            pos += 1
        if len(buf) - pos < (1 << 16) and not fim_arquivo:
            mais = texto.read(1 << 20)
            fim_arquivo = not mais
            buf = buf[pos:] + mais
            pos = 0
            continue
        if pos >= len(buf):
            raise PortalMudou("o arquivo terminou antes de fechar a lista")
        if buf[pos] == "]":
            return
        try:
            obj, pos = dec.raw_decode(buf, pos)
        except json.JSONDecodeError:
            if fim_arquivo:
                raise PortalMudou("registro truncado no fim do arquivo") from None
            mais = texto.read(1 << 20)
            fim_arquivo = not mais
            buf = buf[pos:] + mais
            pos = 0
            continue
        yield obj


def nome_exibivel(nome: str) -> str:
    """'ADALBERTO FREITAS' -> 'Adalberto Freitas'; nome já em caixa mista fica como veio."""
    if not nome.isupper():
        return nome
    minusculas = {"da", "de", "do", "das", "dos", "e"}
    return " ".join(p.lower() if i and p.lower() in minusculas else p[:1] + p[1:].lower() for i, p in enumerate(nome.split()))


class Alesp(FonteAssembleia):
    o_que_tem = ("Despesas de gabinete de cada deputado estadual, somadas pela própria fonte por fornecedor, tipo e mês, "
                 "com o CNPJ do fornecedor.")

    @property
    def arquivo(self) -> str:
        return self.ent.extra["arquivo"]

    def _cache(self) -> Path:
        return config.cache() / "alesp" / "despesas.json.gz"

    async def descobrir(self) -> Descoberta:
        assert self.http is not None
        url = self.arquivo
        await self.educacao.verificar_robots(url, self.http)
        async with self.educacao.vez(url):
            r = await self.http.head(url)
        r.raise_for_status()
        versao = {"last_modified": r.headers.get("last-modified"), "etag": r.headers.get("etag"),
                  "tamanho": r.headers.get("content-length")}
        proc = self.procedencia(url, "", "cabeçalho HTTP (HEAD)")
        totais = [TotalOficial(fonte=self.id, escopo="arquivo", metrica="versao_do_arquivo", valor=versao["last_modified"] or "?",
                               texto_original=f"ETag {versao['etag']}", procedencia=proc)]
        return Descoberta(itens=[ItemInventario(chave="despesas", descricao=f"Despesas de gabinete {self.de}–{self.ate}",
                                                periodo=f"{self.de}-{self.ate}", parametros={"versao": versao})], totais=totais)

    async def _baixar(self, versao: dict) -> tuple[Path, str]:
        destino = self._cache()
        meta = destino.with_suffix(".meta.json")
        if destino.exists() and meta.exists():
            m = json.loads(meta.read_text(encoding="utf-8"))
            if m.get("versao") == versao:
                from ...nucleo.evidencia import registrar_original_arquivo

                registrar_original_arquivo(self.con, self.id, destino, self.arquivo, "json.gz", m["sha256"])
                return destino, m["sha256"]
        caminho, h = await baixar_comprimido(self, self.arquivo, destino)
        meta.write_text(json.dumps({"versao": versao, "sha256": h}, ensure_ascii=False), encoding="utf-8")
        return caminho, h

    async def _deputados(self) -> tuple[dict[str, dict], str, str]:
        """Matrícula -> partido e nome, da lista de deputados em exercício."""
        url = self.ent.extra["deputados"]
        r, h = await self.baixar(url)
        j = r.json()
        lista = j.get("deputados") if isinstance(j, dict) else None
        if not isinstance(lista, list):
            raise PortalMudou("lista de deputados da ALESP em outro formato")
        return {str(d.get("matricula")): {"partido": d.get("siglaPartido"), "nome": (d.get("nomeDeputado") or "").strip()}
                for d in lista if d.get("matricula")}, url, h

    async def coletar_item(self, item: ItemInventario) -> Resultado:
        deputados, url_dep, h_dep = await self._deputados()
        caminho, h = await self._baixar(item.parametros["versao"])
        res = Resultado()
        no_arquivo = no_periodo = 0
        nomes: dict[str, str] = {}
        anos_vistos: set[int] = set()
        with gzip.open(caminho, "rb") as bruto:
            texto = io.TextIOWrapper(bruto, encoding="utf-8")
            for x in registros(texto):
                no_arquivo += 1
                faltam = CAMPOS - set(x)
                if faltam:
                    raise PortalMudou(f"registro da ALESP sem os campos {sorted(faltam)}")
                try:
                    ano, mes = int(x["ano"]), int(x["mes"])
                except (TypeError, ValueError):
                    ano = mes = 0
                if not self.de <= ano <= self.ate:
                    continue
                anos_vistos.add(ano)
                no_periodo += 1
                proc = self.procedencia(self.arquivo, h, f"id {x.get('id')}")
                chave = chave_hash(self.id, x.get("id"))
                texto_original = f"{x.get('deputado')}, {mes:02d}/{ano}, {x.get('tipo')}, valor {x.get('valor')!r}"
                if not x.get("matricula"):
                    res.pendencias.append(Pendencia(fonte=self.id, chave=chave, motivo="registro sem matrícula do deputado",
                                                    texto_original=texto_original, procedencia=proc))
                    continue
                if not 1 <= mes <= 12:
                    res.pendencias.append(Pendencia(fonte=self.id, chave=chave, motivo="mês ilegível",
                                                    texto_original=texto_original, procedencia=proc))
                    continue
                try:
                    valor = decimal_ponto(x["valor"])
                except ValorIlegivel as e:
                    res.pendencias.append(Pendencia(fonte=self.id, chave=chave, motivo="valor ilegível",
                                                    texto_original=f"{texto_original} ({e})", procedencia=proc))
                    continue
                mat = str(x["matricula"])
                nomes.setdefault(mat, (x.get("deputado") or "").strip())
                documento = x.get("cnpj") or x.get("cpf")
                res.despesas.append(self.nota(
                    chave=chave, item=item.chave, ref=f"mat:{mat}", nome=(x.get("deputado") or "").strip(), data=None,
                    competencia=f"{ano}-{mes:02d}", categoria=(x.get("tipo") or "").strip(), documento=documento,
                    fornecedor=x.get("fornecedor"), valor=valor, proc=proc, granularidade="agregado",
                    extra={"id": x.get("id"), "tipo_fornecedor": x.get("tipoFornecedor")}))
        if not no_arquivo:
            raise PortalMudou("o arquivo de despesas da ALESP veio sem nenhum registro")
        proc = self.procedencia(self.arquivo, h, "arquivo inteiro")
        res.totais += [
            TotalOficial(fonte=self.id, escopo="arquivo", metrica="registros_no_arquivo", valor=str(no_arquivo), procedencia=proc),
            TotalOficial(fonte=self.id, escopo=f"despesas-{self.de}-{self.ate}", metrica="linhas_na_origem", valor=str(no_periodo),
                         texto_original=f"registros com ano de {self.de} a {self.ate}", procedencia=proc),
        ]
        proc_dep = self.procedencia(url_dep, h_dep, "lista de deputados")
        for mat, nome in sorted(nomes.items()):
            d = deputados.get(mat, {})
            res.pessoas.append(PessoaFonte(
                fonte=self.id, ref=f"mat:{mat}", periodo=f"{self.de}-{self.ate}", nome=d.get("nome") or nome_exibivel(nome),
                matricula=mat, uf="SP", partido=d.get("partido"), casa=self.ent.casa,
                extra={"partido_de": "lista de deputados em exercício da ALESP" if d else None, "nome_no_arquivo": nome},
                procedencia=proc_dep))
        return res
