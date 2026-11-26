"""Câmara Legislativa do DF: verba indenizatória nos dados abertos (CKAN). Sem navegador.

O conjunto tem um recurso por ano, mas não do mesmo jeito em todos os anos (visto
em 26/11/2026):
- 2023 vem em CSV e em XLSX; 2024 e 2025, completos, só em XLSX; 2024 tem também
  um CSV "até maio"; 2026, um CSV "até outubro";
- o cabeçalho muda (NOME_PARLAMENTAR num ano, "Nome do(a) Deputado(a)" no outro);
- a data vem como "2023-05-02 00:00:00", "02/01/2026", "1/16/2025" (mês primeiro)
  ou número de série do Excel;
- o valor, como "500.0", "173,07", "R$ 5.600,00" ou número da planilha;
- o deputado aparece como "Deputado Fulano", "Dep. FULANO" ou pelo nome civil;
- a classificação é texto livre ("Combustível", "Combustíveis e lubrificantes ",
  "VIII - Divulgação de atividade parlamentar").

O robô lê o arquivo principal de cada ano (o do ano inteiro; CSV quando há os dois)
e confere os outros recursos do mesmo ano contra ele: toda nota do arquivo parcial
tem de estar no principal. As colunas de CPF (do deputado e do fornecedor pessoa
física) só servem, na memória, para ligar as grafias do nome do mesmo deputado; o
CPF não é gravado em lugar nenhum, e o fornecedor pessoa física fica com o CPF
mascarado, como na cota federal.
"""

from __future__ import annotations

import csv
import io
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from html import unescape
from pathlib import Path

from ... import config
from ...modelo import Descoberta, ItemInventario, Pendencia, PessoaFonte, Resultado, TotalOficial
from ...nucleo.erros import PortalMudou
from ...nucleo.planilha import data_serial, ler_xlsx
from ...nucleo.texto import ValorIlegivel, chave_hash, decimal_ponto, dinheiro_br, documento_de_numero, normalizar_nome, sem_acento, so_digitos
from ..arquivos import baixar_arquivo
from ..assembleia import FonteAssembleia

RE_RECURSO = re.compile(r'<a class="heading" href="(/dataset/[^"]+/resource/([0-9a-f-]{36}))" title="([^"]+)"')
RE_DOWNLOAD = re.compile(r'href="(https?://[^"]+/resource/([0-9a-f-]{36})/download/[^"]+)"')
RE_ANO = re.compile(r"\b(20\d\d)\b")
RE_PREFIXO_DEPUTADO = re.compile(r"^(DEPUTADO|DEPUTADA|DEP)\s+")
RE_DATA_BR = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")

# cabeçalho (normalizado) -> campo; a ordem importa: o primeiro que casa decide
CAMPOS = (
    ("id", lambda h: "ID" in h.split() or h.startswith("ID ")),
    ("data", lambda h: "DATA" in h),
    ("valor", lambda h: "VALOR" in h),
    ("categoria", lambda h: "CLASSIFICA" in h),
    ("obs", lambda h: "OBSERVA" in h),
    ("cpf_parlamentar", lambda h: "CPF" in h and ("PARLAMENTAR" in h or "DEPUTAD" in h)),
    ("parlamentar", lambda h: "NOME" in h and ("PARLAMENTAR" in h or "DEPUTAD" in h)),
    ("fornecedor", lambda h: "NOME" in h),
    ("cnpj", lambda h: "CNPJ" in h),
    ("cpf_fornecedor", lambda h: "CPF" in h),
    ("numero", lambda h: "COMPROVANTE" in h or "RECIBO" in h or "NOTA" in h),
)
OBRIGATORIOS = {"data", "valor", "categoria", "parlamentar", "cpf_parlamentar", "fornecedor", "cnpj", "numero"}


def mapear_cabecalho(cabecalho: list[str]) -> dict[str, str]:
    """Coluna da fonte -> campo do robô, pelo texto do cabeçalho."""
    out: dict[str, str] = {}
    usados: set[str] = set()
    for col in cabecalho:
        h = normalizar_nome(col)
        for campo, casa in CAMPOS:
            if campo not in usados and casa(h):
                out[col] = campo
                usados.add(campo)
                break
    faltam = OBRIGATORIOS - usados
    if faltam:
        raise PortalMudou(f"arquivo da CLDF sem as colunas {sorted(faltam)} (cabeçalho: {cabecalho})")
    return out


def ler_arquivo(caminho: Path, formato: str) -> list[dict[str, str | None]]:
    """Linhas com os campos do robô. A coluna de CPF do deputado fica na memória."""
    if formato == "xlsx":
        brutas = ler_xlsx(caminho)
        cab = list(brutas[0].keys()) if brutas else []
    else:
        texto = caminho.read_bytes().decode("utf-8-sig")
        leitor = csv.DictReader(io.StringIO(texto), delimiter=";")
        brutas = list(leitor)
        cab = list(leitor.fieldnames or [])
    mapa = mapear_cabecalho(cab)
    linhas = [{campo: (l.get(col) or "").strip() or None for col, campo in mapa.items()} for l in brutas]
    for l in linhas:
        notas = []
        for campo in ("cnpj", "cpf_fornecedor", "cpf_parlamentar"):
            doc, nota = documento_de_numero(l.get(campo))
            l[campo] = doc
            if nota and campo != "cpf_parlamentar":
                notas.append(nota)
        l["nota_documento"] = "; ".join(notas) or None
    return linhas


MESES = {m: i for i, m in enumerate(["JANEIRO", "FEVEREIRO", "MARCO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO", "SETEMBRO",
                                       "OUTUBRO", "NOVEMBRO", "DEZEMBRO"], start=1)}
RE_DATA_EXTENSO = re.compile(r"^(\d{1,2}) DE ([A-Z]+) DE (\d{4})$")


def formato_do_arquivo(textos: list[str]) -> str:
    """O que o arquivo prova sobre a ordem dia/mês: uma data com o primeiro número
    acima de 12 prova dia/mês; com o segundo acima de 12, mês/dia. As duas provas
    no mesmo arquivo (visto em 2025) = "misto"."""
    dia_primeiro = mes_primeiro = False
    for t in textos:
        m = RE_DATA_BR.match((t or "").strip())
        if m:
            dia_primeiro |= int(m.group(1)) > 12
            mes_primeiro |= int(m.group(2)) > 12
    if dia_primeiro and mes_primeiro:
        return "misto"
    return "dia_mes" if dia_primeiro else ("mes_dia" if mes_primeiro else "sem_prova")


def ler_data(texto: str | None, formato: str = "sem_prova") -> date:
    """Data em qualquer dos formatos vistos, só quando ela é inequívoca.

    Cada data se resolve sozinha quando um dos dois números passa de 12. Quando os
    dois vão até 12, vale a ordem que o próprio arquivo prova; se o arquivo não
    prova nenhuma, ou prova as duas, a linha vai para revisão.
    """
    t = (texto or "").strip()
    if not t:
        raise ValueError("data vazia na fonte")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?", t):
        return datetime.fromisoformat(t).date()
    if re.fullmatch(r"\d{5}(\.0+)?", t):
        return data_serial(t)
    m = RE_DATA_BR.match(t)
    if m:
        a, b, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a > 12 or (a <= 12 and b <= 12 and formato == "dia_mes") or a == b:
            return date(ano, b, a)
        if b > 12 or formato == "mes_dia":
            return date(ano, a, b)
        raise ValueError(f"data ambígua ({t}): " + ("a planilha mistura dia/mês e mês/dia" if formato == "misto"
                                                    else "o arquivo não prova se é dia/mês ou mês/dia"))
    m = RE_DATA_EXTENSO.match(" ".join(sem_acento(t).upper().split()))
    if m and m.group(2) in MESES:
        return date(int(m.group(3)), MESES[m.group(2)], int(m.group(1)))
    raise ValueError(f"data em formato desconhecido: {t}")


def linha_deslocada(l: dict) -> bool:
    """Visto em 2025: o número do comprovante na coluna da data (um número de série de
    data do Excel), o valor na coluna da data e a classificação na coluna do valor."""
    return (bool(re.fullmatch(r"4\d{4}(\.0+)?", l.get("numero") or "")) and bool(re.fullmatch(r"-?[\d.]+", l.get("data") or ""))
            and not re.fullmatch(r"\d{5}(\.0+)?", l.get("data") or "") and bool(re.search(r"[A-Za-z]{3}", l.get("valor") or ""))
            and not l.get("categoria"))


def ler_valor(texto: str | None) -> tuple[Decimal, str | None]:
    """Valor exato e, quando houver, a nota sobre como foi lido."""
    t = (texto or "").strip()
    if "," in t or "R$" in t:
        return dinheiro_br(t), None
    if re.fullmatch(r"-?\d+\.\d{3,}", t):
        # número da planilha em ponto flutuante: a forma curta exata é a que a planilha mostra
        v = decimal_ponto(float(t))
        if v.as_tuple().exponent < -2:  # type: ignore[operator]
            raise ValorIlegivel(f"valor com mais de duas casas: {t}")
        return v, "número de ponto flutuante da planilha, lido pela forma curta"
    return decimal_ponto(t), None


def nome_sem_cargo(nome: str) -> str:
    return RE_PREFIXO_DEPUTADO.sub("", normalizar_nome(nome)).strip()


RE_PREFIXO_ORIGINAL = re.compile(r"^\s*(deputad[oa]|dep\.?)\s+", re.I)


def exibir(nome: str) -> str:
    """'Deputado João Cardoso ' -> 'João Cardoso'; 'CHICO VIGILANTE' -> 'Chico Vigilante'."""
    n = RE_PREFIXO_ORIGINAL.sub("", nome).strip()
    return titulo(n) if n.isupper() or n.islower() else " ".join(p[:1].upper() + p[1:] if i == 0 or len(p) > 3 else p for i, p in enumerate(n.split()))


def titulo(nome: str) -> str:
    minusculas = {"da", "de", "do", "das", "dos", "e"}
    partes = nome.strip().split()
    return " ".join(p.lower() if i and p.lower() in minusculas else p[:1].upper() + p[1:].lower() for i, p in enumerate(partes))


class Cldf(FonteAssembleia):
    pausa = None  # o Crawl-delay do CKAN (10 s) vem do robots.txt
    o_que_tem = "Verba indenizatória de cada deputado distrital, nota a nota, com o fornecedor e o CNPJ."

    async def _recursos(self) -> tuple[list[dict], str, str]:
        url = self.ent.extra["conjunto"]
        r, h = await self.baixar(url, tipo="html")
        titulos = {rid: unescape(t) for _, rid, t in RE_RECURSO.findall(r.text)}
        recursos = []
        for link, rid in RE_DOWNLOAD.findall(r.text):
            t = titulos.get(rid)
            if not t:
                continue
            anos = RE_ANO.findall(t)
            fmt = link.rsplit(".", 1)[-1].lower()
            if not anos or fmt not in ("csv", "xlsx"):
                continue
            recursos.append({"id": rid, "titulo": t, "ano": int(anos[0]), "formato": fmt, "url": link,
                             "parcial": "ATE" in sem_acento(t).upper().replace("(", " ").replace(")", " ").split()})
        if not recursos:
            raise PortalMudou("a página do conjunto da CLDF não lista mais os recursos por ano")
        return recursos, url, h

    async def descobrir(self) -> Descoberta:
        recursos, url, h = await self._recursos()
        por_ano: dict[int, list[dict]] = defaultdict(list)
        for x in recursos:
            if self.de <= x["ano"] <= self.ate:
                por_ano[x["ano"]].append(x)
        anos = {}
        for ano, xs in sorted(por_ano.items()):
            inteiros = [x for x in xs if not x["parcial"]] or xs
            principal = sorted(inteiros, key=lambda x: (x["formato"] != "csv", x["titulo"]))[0]
            anos[str(ano)] = {"principal": principal, "conferir": [x for x in xs if x is not principal]}
        totais = [TotalOficial(fonte=self.id, escopo=f"recursos-{a}", metrica="recursos_no_conjunto", valor=str(len(v["conferir"]) + 1),
                               texto_original="; ".join(f"{x['titulo']} ({x['formato']})" for x in [v["principal"], *v["conferir"]]),
                               procedencia=self.procedencia(url, h)) for a, v in anos.items()]
        # um item só: o CPF do deputado liga as grafias do nome entre os anos, e ele
        # existe só na memória durante a leitura
        return Descoberta(itens=[ItemInventario(chave="verbas", descricao=f"Verba indenizatória {self.de}–{self.ate}",
                                                periodo=f"{self.de}-{self.ate}", parametros={"anos": anos})], totais=totais)

    async def _baixar_recurso(self, x: dict) -> tuple[Path, str]:
        destino = config.cache() / "cldf" / f"{x['id']}.{x['formato']}"
        caminho, h, _ = await baixar_arquivo(self, x["url"], destino, validade_h=20)
        return caminho, h

    async def coletar_item(self, item: ItemInventario) -> Resultado:
        res = Resultado()
        # 1. lê os arquivos principais e guarda as linhas com a sua origem
        lidas: list[tuple[int, dict, str, str, int, str]] = []  # (ano, linha, url, hash, nº da linha, formato de data)
        so_no_principal: dict[int, tuple[Counter, str]] = {}  # ano -> notas do principal que o outro arquivo do ano não tem
        for ano_txt, v in sorted(item.parametros["anos"].items()):
            ano = int(ano_txt)
            x = v["principal"]
            caminho, h = await self._baixar_recurso(x)
            linhas = ler_arquivo(caminho, x["formato"])
            fmt = formato_do_arquivo([l.get("data") or "" for l in linhas])
            res.totais.append(TotalOficial(fonte=self.id, escopo=f"verbas-{ano}", metrica="linhas_no_arquivo", valor=str(len(linhas)),
                                           texto_original=f"{x['titulo']} ({x['formato']})", procedencia=self.procedencia(x["url"], h)))
            for i, l in enumerate(linhas, start=2):
                lidas.append((ano, l, x["url"], h, i, fmt))
            # 2. os outros recursos do mesmo ano: cada nota deles tem de estar no principal;
            # e, se o outro também é do ano inteiro, cada nota do principal tem de estar nele
            principal = Counter(self._assinatura(l) for l in linhas)
            for outro in v["conferir"]:
                c2, h2 = await self._baixar_recurso(outro)
                notas = Counter(self._assinatura(l) for l in ler_arquivo(c2, outro["formato"]))
                faltam = sum((notas - principal).values())
                if not outro["parcial"] and not x["parcial"]:
                    so_no_principal[ano] = (principal - notas, f"{outro['titulo']} ({outro['formato']})")
                res.totais.append(TotalOficial(
                    fonte=self.id, escopo=f"verbas-{ano}:{outro['id'][:8]}", metrica="recurso_contido_no_principal",
                    valor="confere" if faltam == 0 else "diverge",
                    texto_original=(f"{sum(notas.values()) - faltam} de {sum(notas.values())} notas de '{outro['titulo']}' "
                                    f"({outro['formato']}) estão em '{x['titulo']}' ({x['formato']})"),
                    procedencia=self.procedencia(outro["url"], h2)))

        # 3. identidade: grafias do nome ligadas pelo CPF do deputado (só na memória)
        grafias: dict[str, Counter] = defaultdict(Counter)  # chave do grupo -> nomes
        grupo_do_cpf: dict[str, str] = {}
        for _, l, *_ in lidas:
            cpf = so_digitos(l.get("cpf_parlamentar"))
            nome = (l.get("parlamentar") or "").strip()
            if cpf and len(cpf) == 11:
                g = grupo_do_cpf.setdefault(cpf, f"g{len(grupo_do_cpf)}")
            elif nome:
                g = "n:" + nome_sem_cargo(nome)
            else:
                continue
            if nome:
                grafias[g][nome] += 1
        ref_do_grupo: dict[str, str] = {}
        for g, nomes in grafias.items():
            por_tamanho = sorted(nomes, key=lambda n: (-len(nome_sem_cargo(n).split()), -len(nome_sem_cargo(n)), n))
            ref_do_grupo[g] = f"nome:{nome_sem_cargo(por_tamanho[0])}"
            # nome parlamentar: a grafia "Deputado Fulano", quando a fonte usa
            parlamentar = next((n for n, _ in nomes.most_common() if RE_PREFIXO_ORIGINAL.match(n)), None)
            res.pessoas.append(PessoaFonte(
                fonte=self.id, ref=ref_do_grupo[g], periodo=f"{self.de}-{self.ate}", nome=exibir(por_tamanho[0]),
                nome_parlamentar=exibir(parlamentar) if parlamentar else None, uf="DF", casa=self.ent.casa,
                extra={"grafias_na_fonte": sorted({n.strip() for n in nomes}),
                       "ligadas_por": "CPF do deputado na própria planilha (o CPF não é gravado)"},
                procedencia=self.procedencia(self.ent.extra["conjunto"], "", "lista de recursos")))

        # 4. as notas
        vistos: dict[str, int] = {}
        for ano, l, url, h, i, fmt in lidas:
            proc = self.procedencia(url, h, f"linha {i}")
            cpf = so_digitos(l.get("cpf_parlamentar"))
            nome = (l.get("parlamentar") or "").strip()
            grupo: str | None = grupo_do_cpf.get(cpf) if cpf and len(cpf) == 11 else ("n:" + nome_sem_cargo(nome) if nome else None)
            base = chave_hash(self.id, ano, l.get("id"), nome_sem_cargo(nome), l.get("numero"), l.get("data"), l.get("valor"),
                              so_digitos(l.get("cnpj")), l.get("categoria"))
            n = vistos.get(base, 0)
            vistos[base] = n + 1
            chave = chave_hash(base, n)
            texto = f"{ano}, linha {i}: {l.get('categoria') or 'sem classificação'} / {l.get('valor')!r} / {l.get('data')!r}"
            if linha_deslocada(l):
                res.pendencias.append(Pendencia(
                    fonte=self.id, chave=chave, texto_original=f"{ano}, linha {i}: comprovante {l.get('numero')!r}, data {l.get('data')!r}, valor {l.get('valor')!r}",
                    motivo="colunas deslocadas na planilha da fonte (o número do comprovante está na coluna da data, e o valor, na da data)",
                    procedencia=proc))
                continue
            if grupo is None or grupo not in ref_do_grupo:
                res.pendencias.append(Pendencia(fonte=self.id, chave=chave, motivo="nota sem deputado (nome e CPF vazios na fonte)",
                                                texto_original=texto, procedencia=proc))
                continue
            try:
                valor, nota_valor = ler_valor(l.get("valor"))
            except ValorIlegivel as e:
                res.pendencias.append(Pendencia(fonte=self.id, chave=chave, motivo="valor ilegível (texto no lugar do número, ou separadores trocados)",
                                                texto_original=f"{texto} ({e})", procedencia=proc))
                continue
            try:
                quando = ler_data(l.get("data"), fmt)
            except ValueError as e:
                motivo = ("data vazia na fonte" if "vazia" in str(e) else
                          "data ambígua: a planilha mistura dia/mês e mês/dia" if "ambígua" in str(e) else
                          "data ilegível (formato desconhecido)")
                res.pendencias.append(Pendencia(fonte=self.id, chave=chave, motivo=motivo, texto_original=f"{texto} ({e})", procedencia=proc))
                continue
            if quando.year != ano:
                res.pendencias.append(Pendencia(fonte=self.id, chave=chave, procedencia=proc,
                                                texto_original=f"{texto} (data {quando.isoformat()}, arquivo de {ano})",
                                                motivo="data do comprovante fora do ano do arquivo"))
                continue
            documento = l.get("cnpj") if so_digitos(l.get("cnpj")) else l.get("cpf_fornecedor")
            fora_do_outro = None
            if ano in so_no_principal:
                faltantes, outro_titulo = so_no_principal[ano]
                sig = self._assinatura(l)
                if faltantes.get(sig, 0) > 0:
                    faltantes[sig] -= 1
                    fora_do_outro = outro_titulo
            res.despesas.append(self.nota(
                chave=chave, item=item.chave, ref=ref_do_grupo[grupo], nome=nome or ref_do_grupo[grupo][5:], data=quando,
                competencia=f"{quando.year}-{quando.month:02d}", categoria=(l.get("categoria") or "").strip(),
                documento=documento, fornecedor=l.get("fornecedor"), valor=valor, proc=proc,
                extra={"numero_comprovante": l.get("numero"), "observacao": (l.get("obs") or "")[:200] or None,
                       "nota_documento": l.get("nota_documento"), "fora_do_outro_arquivo": fora_do_outro,
                       "nota_valor": nota_valor, "ano_arquivo": ano, "ordem_das_datas_no_arquivo": fmt}))
        return res

    @staticmethod
    def _assinatura(l: dict) -> tuple:
        """A mesma nota em dois arquivos: deputado, fornecedor, número, valor e data, como texto normalizado."""
        try:
            valor = str(ler_valor(l.get("valor"))[0].quantize(Decimal("0.01")))
        except (ValorIlegivel, ArithmeticError):
            valor = l.get("valor") or ""
        numero = re.sub(r"\.0+$", "", (l.get("numero") or "").strip()).lstrip("0")
        return (nome_sem_cargo(l.get("parlamentar") or ""), so_digitos(l.get("cnpj")) or so_digitos(l.get("cpf_fornecedor")), numero, valor)
