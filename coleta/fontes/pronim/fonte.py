"""Govbr Pronim (`webapp1-<cidade>.cidade360.cloud/pronimtb_cm`): robô de navegador
para qualquer câmara que usa o portal.

ASP clássico (`index.asp?acao=3&item=15`), ISO-8859-1, jQuery 1.4. Um formulário
único, com os campos de todas as consultas; o JavaScript mostra os da consulta
aberta, e cada escolha dispara um AJAX que prepara a seguinte:

1. **Ano.** O valor da opção é uma chave interna ("2025|DW_LC131_FC_12|"): o robô
   escolhe pelo texto. A escolha carrega, por AJAX, a entidade do ano; o robô
   confere que é a Câmara do município.
2. **Período.** Vem preenchido com o mês corrente (armadilha: o "ano" pedido vira
   um mês). O campo tem máscara por tecla; o robô digita e confere o que ficou.
3. **Unidade gestora.** "CONSOLIDADA" é o padrão, e em alguns portais é o
   município inteiro (Salto do Lontra: Câmara, Prefeitura e Fundo de Saúde). O robô
   escolhe a "CÂMARA MUNICIPAL" e confere nos "Filtros Utilizados".
4. **Tipo de despesa e desdobramento.** Escolher "DIÁRIAS" carrega os
   desdobramentos da despesa; um deles é "AGENTES POLÍTICOS (3.3.90.14.14.03)".
5. **Gerar.** O botão chama `validarReCaptcha()`, que em `cidade360.cloud` só envia
   o formulário (o reCAPTCHA só existe em `govbr.cloud`, e lá só numa consulta de
   pessoal). Se a página carregar o reCAPTCHA, o robô para: captcha nunca se
   contorna. A resposta é a página de novo, com "Filtros Utilizados" (que o robô
   confere contra o que pediu) e a tabela por credor.

**A tela mostra o CPF sem máscara.** O robô lê a coluna de documento só na
memória: ela liga a mesma pessoa entre as consultas (anual, mês a mês e a dos
agentes políticos) e acusa homônimo. Antes de gravar qualquer coisa, a página é
mascarada no próprio navegador e de novo no texto (`JS_MASCARAR_DOCUMENTO`,
`mascarar_cpf`), e só então vira original com hash. Nada que sai daqui leva o
documento: nem a despesa, nem a pendência, nem a mensagem de erro, nem a
evidência (sem rastro do Playwright, sem vídeo; ver `FonteComCpfNaTela`).

**O que se publica.** A tela soma as diárias por credor no período: cada linha é
um agregado (credor × mês), nunca uma diária. O robô consulta o ano inteiro e mês
a mês; a soma dos meses de cada credor tem de dar o ano inteiro (dois caminhos
independentes da própria tela; não há total publicado). A tabela para perto de
100 credores: consulta que chega lá para, em vez de publicar uma lista cortada (foi
assim que o consolidado de Salto do Lontra apareceu). Quem é vereador sai da
consulta filtrada pelo desdobramento "AGENTES POLÍTICOS"; o resto é servidor ou
colaborador, e entra só na soma, sem nome.
"""

from __future__ import annotations

import calendar
import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from ... import config
from ...entidades import EntidadePronim
from ...modelo import Descoberta, Despesa, ItemInventario, PessoaFonte, Resultado, SistemaOrigem, TotalOficial
from ...nucleo.banco import agora
from ...nucleo.erros import FalhaTransitoria, PortalMudou
from ...nucleo.evidencia import guardar_original
from ...nucleo.texto import ValorIlegivel, chave_hash, cpfs_expostos, dinheiro_br, mascarar_cpf, normalizar_nome
from ..base import JS_MASCARAR_CPF, FonteComCpfNaTela
from ..equiplano.fonte import eh_a_camara

TIPO_DIARIAS = "1"
DESDOBRAMENTO_PARLAMENTAR = "3.3.90.14.14.03.00"
# como o cargo vai para o banco: o texto do desdobramento, ou o que sobra dele
CARGO_PARLAMENTAR = "AGENTES POLÍTICOS"
CARGO_OUTROS = "OUTROS DESDOBRAMENTOS DE DIÁRIAS"
SEM_EMPENHO = "NAO HA INFORMACOES DE EMPENHO"
# A tabela da tela para perto de 100 credores (Salto do Lontra, consolidado: 99 e 100
# no ano inteiro contra 197 somando os meses). O robô não lê página seguinte: a
# consulta que chega aqui para, em vez de publicar uma lista cortada.
LIMITE_DA_TELA = 99
COLUNAS = {"NOME": "nome", "CNPJ CPF": "documento", "VALOR EMPENHADO": "empenhado", "VALOR EM LIQUIDACAO": "em_liquidacao",
           "VALOR LIQUIDADO": "liquidado", "VALOR PAGO": "pago", "VALOR ANULADO": "anulado"}
VALORES = ("empenhado", "em_liquidacao", "liquidado", "pago", "anulado")

# Lê a página do resultado: os filtros que a tela diz ter aplicado e a tabela por
# credor (cabeçalho pelo texto, não pela posição). O documento volta para a memória
# do robô e é a única coisa lida da coluna.
JS_LER = r"""() => {
  const txt = c => (c.innerText || '').replace(/\s+/g, ' ').trim();
  const out = {filtros: {}, cabecalho: null, linhas: [], mensagem: null, recaptcha: typeof grecaptcha !== 'undefined'};
  for (const t of document.querySelectorAll('table')) {
    const r0 = t.rows[0] ? Array.from(t.rows[0].cells).map(txt) : [];
    if (r0[0] === 'Filtros Utilizados') {
      for (const r of Array.from(t.rows).slice(1)) {
        const c = Array.from(r.cells).map(txt);
        for (let i = 0; i + 1 < c.length; i += 2) if (c[i]) out.filtros[c[i]] = c[i + 1];
      }
    }
  }
  for (const t of document.querySelectorAll('table')) {
    let cab = null;
    for (const r of t.rows) {
      const c = Array.from(r.cells).map(txt);
      if (!cab && c[0] === 'Nome' && c.some(x => x.indexOf('CPF') >= 0)) { cab = c; out.cabecalho = c; continue; }
      if (cab && c.length >= cab.length && c[0]) out.linhas.push(c.slice(0, cab.length));
    }
    if (cab) break;
  }
  const m = document.body.innerText.match(/N[ãa]o h[áa] informa[çc][õo]es de empenho[^.]*/i);
  out.mensagem = m ? m[0] : null;
  return out;
}"""

# Mascara, no próprio navegador, a coluna de documento da tabela por credor (CPF
# com ou sem pontos, com ou sem o zero à esquerda) e qualquer CPF que sobre na página.
JS_MASCARAR_DOCUMENTO = r"""() => {
  for (const t of document.querySelectorAll('table')) {
    let col = -1;
    for (const r of t.rows) {
      const c = Array.from(r.cells);
      if (col < 0) { col = c.findIndex(x => (x.innerText || '').indexOf('CNPJ/CPF') >= 0); if (col >= 0) continue; }
      if (col >= 0 && c[col]) {
        const d = (c[col].innerText || '').replace(/\D/g, '');
        if (d.length <= 11) c[col].innerText = '[omitido pelo robô]';
      }
    }
  }
}"""


@dataclass
class Credor:
    nome: str
    valores: dict[str, Decimal]
    documento: str = field(repr=False)  # só na memória


@dataclass
class Consulta:
    credores: list[Credor]
    filtros: dict[str, str]
    url: str
    hash_original: str


def _dinheiro(t: str) -> Decimal:
    return dinheiro_br(t)


def ler_linhas(cabecalho: list[str], linhas: list[list[str]]) -> list[Credor]:
    mapa = {}
    for i, rotulo in enumerate(cabecalho):
        chave = COLUNAS.get(normalizar_nome(rotulo))
        if chave:
            mapa[chave] = i
    faltam = set(COLUNAS.values()) - set(mapa)
    if faltam:
        raise PortalMudou(f"a tabela de diárias por credor mudou: faltam as colunas {sorted(faltam)}")
    out = []
    for c in linhas:
        try:
            valores = {k: _dinheiro(c[mapa[k]]) for k in VALORES}
        except ValorIlegivel as e:
            raise PortalMudou(f"valor ilegível na tabela por credor ({e})") from None
        out.append(Credor(nome=c[mapa["nome"]].strip(), valores=valores, documento=re.sub(r"\D", "", c[mapa["documento"]])))
    return out


def unidade_da_camara(opcoes: list[tuple[str, str]]) -> tuple[str, str]:
    """A unidade gestora a consultar: a da Câmara. Com uma opção só (Cidade Gaúcha em
    2026: só "CONSOLIDADA"), não há o que consolidar além da própria entidade, que a
    consulta já conferiu ser a Câmara. Com mais de uma, tem de haver exatamente uma da
    Câmara; a consolidada, aí, pode ser o município inteiro."""
    if len(opcoes) == 1:
        return opcoes[0]
    camara = [(v, t) for v, t in opcoes if "CAMARA" in normalizar_nome(t) or "LEGISLATIV" in normalizar_nome(t)]
    if len(camara) != 1:
        raise PortalMudou(f"a unidade gestora da Câmara não está na lista (ou há mais de uma): {[t for _, t in opcoes]}")
    return camara[0]


class Pronim(FonteComCpfNaTela):
    grupo = "pronim"
    ua = config.UA_ROBO
    pausa = 2.0

    def __init__(self, ent: EntidadePronim) -> None:
        self.ent = ent
        self.id = ent.fonte
        self.sistema = SistemaOrigem(
            fonte=ent.fonte, casa=ent.casa, sistema="Portal da Transparência Govbr (Pronim)", fornecedor="Govbr", modo="robo",
            cobre_de=ent.de, cobre_ate=ent.ate, endereco=ent.tela,
            o_que_tem=(f"Diárias da Câmara de {ent.municipio}, somadas por credor e mês pela própria tela; quem é vereador sai do "
                       "desdobramento \"agentes políticos\"."),
        )
        super().__init__()

    # ------------------------------------------------------------------ o formulário
    async def _abrir(self) -> None:
        assert self.pagina is not None
        if "govbr.cloud" in self.ent.base:
            raise PortalMudou("o portal está em govbr.cloud, onde o Gerar pode pedir reCAPTCHA; captcha não se contorna")
        await self.ir(self.ent.tela, wait_until="networkidle")
        if await self.pagina.evaluate("typeof grecaptcha !== 'undefined'"):
            raise PortalMudou("a página passou a carregar o reCAPTCHA; captcha não se contorna")
        if await self.pagina.locator("select[name=cmbAno]").count() == 0:
            raise PortalMudou("a consulta de diárias não tem mais o select de ano")

    async def _anos(self) -> dict[str, str]:
        assert self.pagina is not None
        ops = await self.pagina.eval_on_selector("select[name=cmbAno]", "s => Array.from(s.options).map(o => [o.text.trim(), o.value])")
        return {t: v for t, v in ops if t.isdigit()}

    async def _escolher_ano(self, ano: int) -> None:
        assert self.pagina is not None
        anos = await self._anos()
        if str(ano) not in anos:
            raise PortalMudou(f"o ano {ano} sumiu da consulta")
        async with self.educacao.vez(self.ent.base):
            await self.pagina.select_option("select[name=cmbAno]", anos[str(ano)])
            await self.pagina.wait_for_load_state("networkidle")
        entidade = ""
        for _ in range(20):
            entidade = await self.pagina.eval_on_selector(
                "select[name=cmbUnidadeCP]", "s => s.selectedIndex >= 0 ? s.options[s.selectedIndex].text.trim() : ''")
            if entidade:
                break
            await self.pagina.wait_for_timeout(500)
        if not eh_a_camara(entidade, self.ent.municipio):
            raise PortalMudou(f"a entidade do portal em {ano} é '{entidade}', não a Câmara de {self.ent.municipio}")

    async def _digitar(self, nome: str, valor: str) -> None:
        assert self.pagina is not None
        campo = self.pagina.locator(f"input[name={nome}]")
        await campo.click()
        await campo.press("Control+A")
        await campo.press("Delete")
        await campo.press_sequentially(valor, delay=30)
        await self.pagina.keyboard.press("Tab")
        await self.pagina.wait_for_load_state("networkidle")
        ficou = await campo.input_value()
        if ficou != valor:
            raise PortalMudou(f"o campo {nome} ficou '{ficou}' depois de digitar {valor}: a máscara mudou")

    async def _escolher_unidade_da_camara(self) -> str:
        """A unidade gestora "CONSOLIDADA" é a do município inteiro em alguns portais
        (Salto do Lontra: Câmara, Prefeitura e Fundo de Saúde). O robô escolhe a da Câmara."""
        assert self.pagina is not None
        opcoes: list[list[str]] = []
        for _ in range(20):
            opcoes = await self.pagina.eval_on_selector(
                "select[name=cmbUnidadeGestora]", "s => Array.from(s.options).map(o => [o.value, o.text.trim()])")
            if opcoes and (len(opcoes) == 1 or any("CAMARA" in normalizar_nome(t) for _, t in opcoes)):
                break
            await self.pagina.wait_for_timeout(500)
        valor, texto = unidade_da_camara([(v, t) for v, t in opcoes])
        await self.pagina.select_option("select[name=cmbUnidadeGestora]", valor)
        return texto

    async def _consultar(self, ano: int, inicio: str, fim: str, desdobramento: str | None = None) -> Consulta:
        """Uma consulta inteira, do formulário limpo à tabela: o portal volta o
        formulário ao padrão (ano e mês correntes) depois de cada uma."""
        assert self.pagina is not None
        await self._abrir()
        await self._escolher_ano(ano)
        await self._digitar("txtDataInicial", inicio)
        await self._digitar("txtDataFinal", fim)
        unidade = await self._escolher_unidade_da_camara()
        async with self.educacao.vez(self.ent.base):
            await self.pagina.select_option("select[name=cmbDiariasPassagens]", TIPO_DIARIAS)
            await self.pagina.wait_for_load_state("networkidle")
        if desdobramento:
            try:
                await self.pagina.wait_for_function(
                    "v => Array.from(document.querySelector('select[name=cmbDesdobramentoDespesa]').options).some(o => o.value === v)",
                    arg=desdobramento, timeout=20000)
            except Exception as e:
                raise PortalMudou(f"o desdobramento {desdobramento} não apareceu na lista") from e
            await self.pagina.select_option("select[name=cmbDesdobramentoDespesa]", [desdobramento])
        async with self.educacao.vez(self.ent.base):
            try:
                async with self.pagina.expect_navigation(timeout=120000):
                    await self.pagina.click("input[type=button][value=Gerar]")
            except Exception as e:
                raise FalhaTransitoria(f"o Gerar não respondeu ({type(e).__name__})") from e
            await self.pagina.wait_for_load_state("networkidle")
        lido = await self.pagina.evaluate(JS_LER)
        # daqui em diante a página só existe mascarada
        await self.pagina.evaluate(JS_MASCARAR_DOCUMENTO)
        await self.pagina.evaluate(JS_MASCARAR_CPF)
        html = mascarar_cpf(await self.pagina.content())
        if cpfs_expostos(html):
            raise PortalMudou("sobrou CPF na página depois da máscara; o original não foi gravado")
        url = f"{self.ent.tela} (Gerar: {inicio} a {fim}{', ' + desdobramento if desdobramento else ''})"
        h = guardar_original(self.con, self.id, html.encode("utf-8"), url, "html")
        if lido["recaptcha"]:
            raise PortalMudou("a resposta carregou o reCAPTCHA; captcha não se contorna")
        f = lido["filtros"]
        if (f.get("Exercício") != str(ano) or f.get("Período") != f"{inicio} a {fim}" or normalizar_nome(f.get("Tipo de Despesa")) != "DIARIAS"
                or normalizar_nome(f.get("Unidade Gestora")) != normalizar_nome(unidade)):
            raise PortalMudou(f"a tela aplicou outros filtros: exercício {f.get('Exercício')!r}, período {f.get('Período')!r}, "
                              f"tipo {f.get('Tipo de Despesa')!r}, unidade gestora {f.get('Unidade Gestora')!r}")
        if lido["cabecalho"] is None:
            if lido["mensagem"] and SEM_EMPENHO in normalizar_nome(lido["mensagem"]):
                return Consulta(credores=[], filtros=f, url=url, hash_original=h)
            raise FalhaTransitoria("a tabela por credor não veio, nem o aviso de que não há empenho")
        if len(lido["linhas"]) >= LIMITE_DA_TELA:
            raise PortalMudou(f"a tabela por credor chegou a {len(lido['linhas'])} linhas, perto de onde a tela corta; "
                              "o robô não lê página seguinte e não publica lista cortada")
        return Consulta(credores=ler_linhas(lido["cabecalho"], lido["linhas"]), filtros=f, url=url, hash_original=h)

    # ------------------------------------------------------------------ descobrir e coletar
    async def descobrir(self) -> Descoberta:
        await self._abrir()
        anos = sorted(int(a) for a in await self._anos())
        teto = min(self.ent.ate, int(agora()[:4]))
        alvo = [a for a in anos if self.ent.de <= a <= teto]
        if not alvo:
            raise PortalMudou(f"nenhum ano entre {self.ent.de} e {teto} na consulta (tem {anos[:1]}–{anos[-1:]})")
        await self._escolher_ano(alvo[-1])  # confere a entidade
        assert self.pagina is not None
        h = guardar_original(self.con, self.id, mascarar_cpf(await self.pagina.content()).encode("utf-8"), self.ent.tela, "html")
        totais = [TotalOficial(fonte=self.id, escopo="entidade", metrica="anos_na_consulta", valor=f"{anos[0]}-{anos[-1]}",
                               procedencia=self.procedencia(self.ent.tela, h, "select de ano"))]
        return Descoberta(itens=[ItemInventario(chave=f"diarias-{a}", descricao=f"Diárias {a}, ano inteiro e mês a mês", periodo=str(a),
                                                parametros={"ano": a}) for a in alvo], totais=totais)

    async def coletar_item(self, item: ItemInventario) -> Resultado:
        ano = int(item.parametros["ano"])
        hoje = agora()[:10]
        ultimo_mes = int(hoje[5:7]) if ano == int(hoje[:4]) else 12
        anual = await self._consultar(ano, f"01/01/{ano}", f"31/12/{ano}")
        agentes = await self._consultar(ano, f"01/01/{ano}", f"31/12/{ano}", DESDOBRAMENTO_PARLAMENTAR)
        meses: dict[int, Consulta] = {}
        for m in range(1, ultimo_mes + 1):
            fim = calendar.monthrange(ano, m)[1]
            meses[m] = await self._consultar(ano, f"01/{m:02d}/{ano}", f"{fim:02d}/{m:02d}/{ano}")
        return self._resultado(item, ano, anual, agentes, meses)

    def _resultado(self, item: ItemInventario, ano: int, anual: Consulta, agentes: Consulta, meses: dict[int, Consulta]) -> Resultado:
        # tudo que liga uma consulta à outra é o documento, na memória; nada dele sai daqui
        def chave_pessoa(c: Credor) -> str:
            return c.documento or f"nome:{normalizar_nome(c.nome)}"

        soma_meses: dict[str, dict[str, Decimal]] = defaultdict(lambda: dict.fromkeys(VALORES, Decimal(0)))
        nomes_por_documento: dict[str, set[str]] = defaultdict(set)
        documentos_por_nome: dict[str, set[str]] = defaultdict(set)
        for c in [*anual.credores, *agentes.credores, *(c for q in meses.values() for c in q.credores)]:
            nomes_por_documento[chave_pessoa(c)].add(normalizar_nome(c.nome))
            documentos_por_nome[normalizar_nome(c.nome)].add(chave_pessoa(c))
        for q in meses.values():
            for c in q.credores:
                for k in VALORES:
                    soma_meses[chave_pessoa(c)][k] += c.valores[k]
        no_ano = {chave_pessoa(c): c for c in anual.credores}
        vereadores = {chave_pessoa(c): c for c in agentes.credores}

        # dois caminhos independentes da tela: o ano inteiro e a soma dos meses, credor a credor
        diferentes = [p for p in set(no_ano) | set(soma_meses)
                      if p not in no_ano or p not in soma_meses or any(no_ano[p].valores[k] != soma_meses[p][k] for k in VALORES)]
        total_ano = sum((c.valores["empenhado"] for c in anual.credores), Decimal(0))
        total_meses = sum((v["empenhado"] for v in soma_meses.values()), Decimal(0))
        confere = not diferentes
        # sem "R$": o texto vai para a página como detalhe da conferência, e todo valor em reais
        # na plataforma precisa da ficha de procedência
        detalhe = (f"{len(no_ano)} credores no ano inteiro, {len(soma_meses)} somando os meses; empenhado {total_ano} × {total_meses}"
                   + ("" if confere else f"; {len(diferentes)} credor(es) com valores diferentes nos dois caminhos"))
        # vereador: está na consulta dos agentes políticos, com o mesmo valor do ano inteiro
        parciais = {p for p, c in vereadores.items() if p not in no_ano or no_ano[p].valores["empenhado"] != c.valores["empenhado"]}
        homonimos = {p for nome, docs in documentos_por_nome.items() if len(docs) > 1 for p in docs}
        varios_nomes = {p for p, nomes in nomes_por_documento.items() if len(nomes) > 1}

        proc0 = self.procedencia(anual.url, anual.hash_original, "Filtros Utilizados e tabela por credor")
        n_linhas = sum(len(q.credores) for q in meses.values())
        res = Resultado(totais=[
            TotalOficial(fonte=self.id, escopo=item.chave, metrica="registros", valor=str(n_linhas),
                         texto_original="linhas credor × mês nas consultas mês a mês", procedencia=proc0),
            TotalOficial(fonte=self.id, escopo=item.chave, metrica="ano_inteiro_x_mes_a_mes", valor="confere" if confere else "diverge",
                         texto_original=detalhe, procedencia=proc0),
            TotalOficial(fonte=self.id, escopo=item.chave, metrica="empenhado_no_ano", valor=str(total_ano),
                         texto_original=f"soma da coluna Valor Empenhado, {len(no_ano)} credores", procedencia=proc0),
            TotalOficial(fonte=self.id, escopo=item.chave, metrica="vereadores_no_ano", valor=str(len(vereadores)),
                         texto_original="credores no desdobramento agentes políticos (3.3.90.14.14.03)",
                         procedencia=self.procedencia(agentes.url, agentes.hash_original, "tabela por credor")),
        ])
        for mes, q in sorted(meses.items()):
            vistos: dict[str, int] = {}
            for i, c in enumerate(q.credores, start=1):
                p = chave_pessoa(c)
                parlamentar = p in vereadores and p not in parciais and p not in homonimos and p not in varios_nomes
                nome = c.nome if parlamentar else None
                v = c.valores
                if p in vereadores:
                    base = chave_hash(self.id, ano, mes, "vereador", normalizar_nome(c.nome))
                else:  # servidor: a chave não leva nada do nome
                    base = chave_hash(self.id, ano, mes, "servidor", *(v[k] for k in VALORES))
                n = vistos.get(base, 0)
                vistos[base] = n + 1
                notas = []
                if p in parciais:
                    notas.append("parte das diárias do credor está fora do desdobramento agentes políticos")
                if p in homonimos or p in varios_nomes:
                    notas.append("nome e documento não se correspondem um a um entre as consultas (homônimo ou grafia)")
                proc = self.procedencia(q.url, q.hash_original, f"{mes:02d}/{ano}, linha {i} da tabela por credor")
                res.despesas.append(Despesa(
                    chave=chave_hash(base, n) if n else base, fonte=self.id, item=item.chave, tipo="diaria_municipal",
                    casa=self.ent.casa, granularidade="agregado",
                    ref_parlamentar=f"nome:{normalizar_nome(nome)}" if nome else None,
                    beneficiario_tipo="parlamentar" if nome else "servidor", nome_beneficiario=nome,
                    cargo_original=CARGO_PARLAMENTAR if nome else CARGO_OUTROS, data=None, competencia=f"{ano}-{mes:02d}",
                    ano=ano, categoria_original="Diária", valor=v["empenhado"] - v["anulado"], documento_url=self.ent.tela,
                    descricao=None, procedencia=proc,
                    extra={"agregado": "soma das diárias do credor no mês, como a tela mostra", **{k: str(v[k]) for k in VALORES},
                           "notas_identidade": notas, "anulado_inteiro": v["anulado"] == v["empenhado"] and v["empenhado"] > 0},
                ))
                if nome:
                    res.pessoas.append(PessoaFonte(fonte=self.id, ref=f"nome:{normalizar_nome(nome)}", periodo=str(ano), nome=nome,
                                                   casa=self.ent.casa, procedencia=proc))
        return res
