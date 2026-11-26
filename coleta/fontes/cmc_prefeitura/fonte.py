"""Câmara de Curitiba no portal da Prefeitura (2024 em diante): robô de navegador.

É o link "Diárias anteriores a 2026" do Betha. Página ASP.NET WebForms: cada
filtro e cada página da tabela é um postback (`__doPostBack`). Não há total
publicado.

Visto em 26/11/2026: paginar o ano inteiro não é reproduzível. Duas leituras da
mesma consulta trouxeram conjuntos diferentes de linhas (a ordem da tabela muda
entre um postback e outro, e páginas repetem ou pulam linhas). Por isso o robô
consulta mês a mês (cada mês cabe numa página, quase sempre), e todo mês que
ainda precisa de paginação é lido duas vezes: se as duas leituras não forem
iguais, o item é refeito. Uma linha que aparece em duas páginas também derruba
a leitura.
"""

from __future__ import annotations

import re

from ... import config
from ...de_para import eh_cargo_parlamentar
from ...modelo import Descoberta, Despesa, ItemInventario, Pendencia, PessoaFonte, Resultado, SistemaOrigem, TotalOficial
from ...nucleo.erros import FalhaTransitoria, PortalMudou
from ...nucleo.evidencia import guardar_original
from ...nucleo.texto import ValorIlegivel, chave_hash, data_br, dinheiro_br, normalizar_nome
from ..base import FonteNavegador

URL = "https://www.transparencia.curitiba.pr.gov.br/sgp/despesasviagemadiantamento.aspx"
ORGAO = "01"
ORGAO_NOME = "CÂMARA MUNICIPAL DE CURITIBA"
TIPO_DIARIAS = "1"
ANO_INICIAL = 2024  # antes disso a Câmara estava no Elotech (Etapa 0: 2022 e 2023 vazios aqui)
SEL = {
    "ano": "#cphMasterPrincipal_ddlAno",
    "mes": "#cphMasterPrincipal_ddlMes",
    "orgao": "#cphMasterPrincipal_ddlOrgao",
    "tipo": "#cphMasterPrincipal_ddlTipo",
    "pesquisar": "#cphMasterPrincipal_lnbPesquisar",
    "grade": "#cphMasterPrincipal_gdvAdiantamentosViagens",
}
COLUNAS = {
    "ORGAO": "orgao", "DOC": "doc", "SOLICITANTE": "solicitante", "MATR": "matricula", "CARGO": "cargo",
    "OBJETIVO DA VIAGEM": "objetivo", "INICIO": "inicio", "FIM": "fim", "DESTINO": "destino",
    "TRANSPORTE": "transporte", "DIARIAS": "qtde", "VALOR UN": "valor_un", "VALOR DIARIAS": "valor",
    "DEVOLVIDO": "devolvido",
}
OBRIGATORIAS = {"doc", "solicitante", "cargo", "inicio", "valor", "orgao"}
SIGLA_ORGAO = "CMC"


def conferir_orgao(dados: list[list[str]], mapa: dict[str, int], pagina: int) -> None:
    """Toda linha tem de ser da Câmara. Visto em 26/11/2026: a primeira página às vezes
    é lida antes de o filtro do órgão valer e traz secretarias da Prefeitura. Isso é
    falha de leitura, não dado: a página é refeita, nunca gravada."""
    fora = [c[mapa["orgao"]] for c in dados if not c[mapa["orgao"]].strip().endswith(SIGLA_ORGAO)]
    if fora:
        raise FalhaTransitoria(f"página {pagina} veio com {len(fora)} linha(s) de outro órgão (filtro ainda não aplicado)")


def ler_grade(linhas: list[list[str]]) -> tuple[dict[str, int], list[list[str]]]:
    """Primeira linha é o cabeçalho. Devolve (mapa coluna->índice, linhas de dado)."""
    if not linhas:
        raise PortalMudou("tabela de diárias sem linhas (nem cabeçalho)")
    # O cabeçalho traz uma dica escondida antes do rótulo ("Número do empenho da
    # despesa.Doc."): vale o último pedaço entre pontos.
    cab = [normalizar_nome(([p for p in c.split(".") if p.strip()] or [""])[-1]) for c in linhas[0]]
    mapa = {}
    for i, c in enumerate(cab):
        if c in COLUNAS:
            mapa[COLUNAS[c]] = i
    faltam = OBRIGATORIAS - set(mapa)
    if faltam:
        raise PortalMudou(f"tabela de diárias sem as colunas {sorted(faltam)}; cabeçalho: {linhas[0]}")
    return mapa, [l for l in linhas[1:] if len(l) == len(cab)]


class CmcPrefeitura(FonteNavegador):
    id = "cmc_prefeitura"
    # O ASP.NET só emite o script de postback para User-Agent de navegador.
    ua = config.UA_NAVEGADOR_ROBO
    sistema = SistemaOrigem(
        fonte="cmc_prefeitura", casa="cmc", sistema="Portal da Transparência da Prefeitura de Curitiba",
        fornecedor="Prefeitura de Curitiba (ICI)", modo="robo", cobre_de=2024, cobre_ate=2025, endereco=URL,
        o_que_tem="Diárias da Câmara a partir de 2024, no portal do município (órgão 01).",
    )

    async def _postback(self, acao) -> None:
        assert self.pagina is not None
        try:
            async with self.pagina.expect_response(
                lambda r: r.request.method == "POST" and r.url.split("#")[0] == URL, timeout=60000
            ) as info:
                await acao()
            resp = await info.value
        except Exception as e:
            raise FalhaTransitoria(f"postback não respondeu: {type(e).__name__}") from e
        if resp.status >= 500:
            raise FalhaTransitoria(f"postback devolveu HTTP {resp.status}")
        await self.pagina.wait_for_load_state("networkidle")

    async def _pesquisar(self, ano: int, mes: int | None = None) -> None:
        assert self.pagina is not None
        await self.ir(URL, wait_until="networkidle")
        if await self.pagina.locator(SEL["orgao"]).count() == 0:
            raise PortalMudou("o filtro de órgão sumiu da página")
        if not await self.pagina.evaluate("typeof __doPostBack === 'function'"):
            raise PortalMudou("a página veio sem o script de postback (User-Agent recusado?)")
        orgaos = await self.pagina.eval_on_selector(SEL["orgao"], "e => Array.from(e.options).map(o => [o.value, o.text])")
        if not any(v == ORGAO and normalizar_nome(t) == normalizar_nome(ORGAO_NOME) for v, t in orgaos):
            raise PortalMudou(f"o órgão {ORGAO} não é mais a Câmara: {orgaos[:3]}")
        async with self.educacao.vez(URL):
            await self._postback(lambda: self.pagina.select_option(SEL["ano"], str(ano)))
        # o postback recarrega a página: espera o documento novo estar de pé
        await self.pagina.wait_for_load_state("load")
        await self.pagina.wait_for_function("([s, v]) => document.querySelector(s)?.value === v", arg=[SEL["ano"], str(ano)])
        await self.pagina.wait_for_timeout(500)
        # Depois do postback do exercício o portal pré-seleciona o mês corrente:
        # o robô sempre escolhe o mês explicitamente (ou ":: Mês ::" pelo índice).
        valores: list[str] = []
        esperado = [str(ano), str(mes) if mes else "", ORGAO, TIPO_DIARIAS]
        for _ in range(3):
            if mes:
                await self.pagina.select_option(SEL["mes"], str(mes))
            else:
                await self.pagina.select_option(SEL["mes"], index=0)
            await self.pagina.select_option(SEL["orgao"], ORGAO)
            await self.pagina.select_option(SEL["tipo"], TIPO_DIARIAS)
            valores = [await self.pagina.eval_on_selector(SEL[k], "e => e.value") for k in ("ano", "mes", "orgao", "tipo")]
            if valores == esperado:
                break
            await self.pagina.wait_for_timeout(1000)
        if valores != esperado:
            raise FalhaTransitoria(f"os filtros não ficaram como pedido: {valores}")
        async with self.educacao.vez(URL):
            await self._postback(lambda: self.pagina.click(SEL["pesquisar"]))
        await self.pagina.wait_for_load_state("load")
        # espera a tabela mostrar o resultado filtrado (ou nenhuma linha) antes de ler
        try:
            await self.pagina.wait_for_function(
                """([s, sigla]) => { const t = document.querySelector(s); if (!t) return true;
                     const r = Array.from(t.rows).filter(x => x.classList.contains('grid_Row') || x.classList.contains('grid_AlternatingRow'));
                     return r.length === 0 || r.every(x => x.cells[0].innerText.trim().endsWith(sigla)); }""",
                arg=[SEL["grade"], SIGLA_ORGAO], timeout=20000)
        except Exception as e:
            raise FalhaTransitoria("a tabela não mostrou o resultado filtrado a tempo") from e

    async def _ler_pagina_da_grade(self) -> tuple[list[list[str]], list[str]]:
        assert self.pagina is not None
        grade = self.pagina.locator(SEL["grade"])
        if await grade.count() == 0:
            return [], []
        linhas = await grade.evaluate(
            """t => Array.from(t.rows)
                 .filter(r => !r.classList.contains('grid_Pager'))
                 .map(r => Array.from(r.cells).map(c => c.innerText.trim()))"""
        )
        paginador = await grade.evaluate(
            """t => { const p = Array.from(t.rows).find(r => r.classList.contains('grid_Pager'));
                     return p ? Array.from(p.querySelectorAll('a, span')).map(e => e.innerText.trim()) : []; }"""
        )
        return linhas, paginador

    async def descobrir(self) -> Descoberta:
        assert self.pagina is not None
        await self.ir(URL, wait_until="networkidle")
        anos = await self.pagina.eval_on_selector(SEL["ano"], "e => Array.from(e.options).map(o => o.value)")
        anos = sorted(int(a) for a in anos if a.isdigit() and int(a) >= ANO_INICIAL)
        if not anos:
            raise PortalMudou("nenhum exercício a partir de 2024 no filtro")
        h = guardar_original(self.con, self.id, (await self.pagina.content()).encode("utf-8"), URL, "html")
        itens = [ItemInventario(chave=f"diarias-{a}", descricao=f"Diárias da Câmara {a}", periodo=str(a), parametros={"ano": a})
                 for a in anos]
        # Guarda da fronteira: o ano anterior tem de seguir vazio aqui (ele é do Elotech).
        await self._pesquisar(ANO_INICIAL - 1)
        linhas, _ = await self._ler_pagina_da_grade()
        n_antes = max(0, len(linhas) - 1)
        totais = [TotalOficial(fonte=self.id, escopo=f"fronteira-{ANO_INICIAL - 1}", metrica="registros", valor=str(n_antes),
                               texto_original=f"órgão {ORGAO}, tipo Diárias, exercício {ANO_INICIAL - 1}",
                               procedencia=self.procedencia(URL, h, "filtro de exercícios"))]
        return Descoberta(itens=itens, totais=totais)

    async def _ler_consulta(self, ano: int, mes: int | None) -> tuple[list[tuple[list[str], dict, str, int]], int]:
        """Lê todas as páginas de um mês. Devolve [(células, mapa, hash da página, nº da página)] e o nº de páginas."""
        assert self.pagina is not None
        await self._pesquisar(ano, mes)
        lidas: list[tuple[list[str], dict, str, int]] = []
        pagina_atual = 1
        while True:
            linhas, paginador = await self._ler_pagina_da_grade()
            if not linhas:
                break
            # mês sem diária: a tabela vira uma linha só, "Não há fato gerador para esse período."
            if len(linhas) == 1 and len(linhas[0]) == 1 and "NAO HA" in normalizar_nome(linhas[0][0]):
                break
            mapa, dados = ler_grade(linhas)
            if not dados:
                break
            conferir_orgao(dados, mapa, pagina_atual)
            html = await self.pagina.content()
            h = guardar_original(self.con, self.id, html.encode("utf-8"),
                                 f"{URL}#exercicio={ano}&mes={mes}&pagina={pagina_atual}", "html")
            lidas += [(c, mapa, h, pagina_atual) for c in dados]
            proxima = str(pagina_atual + 1)
            if proxima in paginador:
                alvo = self.pagina.locator(SEL["grade"]).locator("tr.grid_Pager a", has_text=re.compile(rf"^{proxima}$"))
            elif "..." in paginador and paginador.index("...") > (paginador.index(str(pagina_atual)) if str(pagina_atual) in paginador else -1):
                alvo = self.pagina.locator(SEL["grade"]).locator("tr.grid_Pager a", has_text="...").last
            else:
                break
            async with self.educacao.vez(URL):
                await self._postback(lambda alvo=alvo: alvo.first.click())
            pagina_atual += 1
            if pagina_atual > 200:
                raise PortalMudou("paginação não termina (mais de 200 páginas num mês)")
        # a mesma linha em duas páginas: a paginação repetiu e algo ficou de fora
        por_pagina: dict[tuple, set] = {}
        for c, _m, _h, pg in lidas:
            por_pagina.setdefault(tuple(c), set()).add(pg)
        if any(len(pgs) > 1 for pgs in por_pagina.values()):
            rotulo = f"{mes:02d}/{ano}" if mes else f"o ano {ano} inteiro"
            raise FalhaTransitoria(f"{rotulo}: a mesma linha apareceu em duas páginas (paginação instável)")
        return lidas, pagina_atual

    async def coletar_item(self, item: ItemInventario) -> Resultado:
        assert self.pagina is not None
        ano = int(item.parametros["ano"])
        res = Resultado()
        vistos: dict[str, int] = {}
        paginas_lidas = 0
        meses_com_paginacao = 0
        todas_mes: list = []
        for mes in range(1, 13):
            lidas, paginas = await self._ler_consulta(ano, mes)
            todas_mes.extend(lidas)
            if paginas > 1:
                # paginação dentro do mês: lê de novo e exige o mesmo resultado
                meses_com_paginacao += 1
                de_novo, _ = await self._ler_consulta(ano, mes)
                if sorted(tuple(c) for c, *_ in lidas) != sorted(tuple(c) for c, *_ in de_novo):
                    raise FalhaTransitoria(f"{mes:02d}/{ano}: duas leituras do mesmo mês deram linhas diferentes")
            paginas_lidas += paginas if lidas else 0
            for i, (cel, mapa, h, pg) in enumerate(lidas, start=1):
                proc = self.procedencia(URL, h, f"exercício {ano}, mês {mes:02d}, página {pg}, linha {i}")
                d = self._linha(cel, mapa, ano, item, vistos, proc)
                if isinstance(d, Despesa):
                    res.despesas.append(d)
                    if d.beneficiario_tipo == "parlamentar":
                        res.pessoas.append(PessoaFonte(fonte=self.id, ref=d.ref_parlamentar, periodo=str(ano),
                                                       nome=d.nome_beneficiario or "", matricula=d.extra.get("matricula"),
                                                       casa="cmc", procedencia=proc))
                else:
                    res.pendencias.append(d)
        n = len(res.despesas) + len(res.pendencias)
        proc_ano = self.procedencia(URL, res.despesas[0].procedencia.hash_original if res.despesas else "", "todas as consultas do ano")
        res.totais.append(TotalOficial(
            fonte=self.id, escopo=f"diarias-{ano}", metrica="registros_lidos", valor=str(n),
            texto_original=f"12 consultas mês a mês, {paginas_lidas} página(s); {meses_com_paginacao} mês(es) com paginação lidos duas vezes",
            procedencia=proc_ano))
        # Segundo caminho, independente: a consulta do ano inteiro. Sem total publicado,
        # é a única forma de saber se o mês a mês está completo. Se os dois caminhos
        # não trouxerem o mesmo conjunto de linhas, o ano inteiro vai para a revisão.
        por_mes = sorted(tuple(c) for c, *_ in todas_mes)
        try:
            ano_inteiro, _ = await self._ler_consulta(ano, None)
        except FalhaTransitoria as e:
            # a própria consulta do ano é instável (repete linha entre páginas): diverge, com o motivo
            res.totais.append(TotalOficial(
                fonte=self.id, escopo=f"diarias-{ano}", metrica="ano_inteiro_x_mes_a_mes", valor="diverge",
                texto_original=f"mês a mês: {len(por_mes)} linhas; consulta do ano inteiro instável: {e}", procedencia=proc_ano))
            return res
        por_ano = sorted(tuple(c) for c, *_ in ano_inteiro)
        so_mes = len(por_mes) - sum(min(por_mes.count(t), por_ano.count(t)) for t in set(por_mes))
        so_ano = len(por_ano) - sum(min(por_mes.count(t), por_ano.count(t)) for t in set(por_ano))
        res.totais.append(TotalOficial(
            fonte=self.id, escopo=f"diarias-{ano}", metrica="ano_inteiro_x_mes_a_mes",
            valor="confere" if so_mes == 0 and so_ano == 0 else "diverge",
            texto_original=(f"consulta do ano inteiro: {len(por_ano)} linhas; mês a mês: {len(por_mes)}; "
                            f"{so_mes} só no mês a mês, {so_ano} só no ano inteiro"),
            procedencia=proc_ano))
        return res

    def _linha(self, cel: list[str], mapa: dict[str, int], ano: int, item: ItemInventario, vistos: dict, proc):
        g = lambda k: (cel[mapa[k]].strip() if k in mapa else "")  # noqa: E731
        cargo = g("cargo")
        parlamentar = eh_cargo_parlamentar(cargo)
        base = chave_hash(self.id, ano, g("doc"), g("matricula"), g("inicio"), g("fim"), g("valor"))
        n = vistos.get(base, 0)
        vistos[base] = n + 1
        chave = chave_hash(base, n)
        try:
            valor = dinheiro_br(g("valor"))
        except ValorIlegivel:
            return Pendencia(fonte=self.id, chave=chave, motivo=f"valor ilegível: '{g('valor')}'",
                             texto_original=f"doc {g('doc')}, cargo '{cargo}'", procedencia=proc)
        try:
            inicio = data_br(g("inicio"))
        except Exception:
            return Pendencia(fonte=self.id, chave=chave, motivo=f"data de início ilegível: '{g('inicio')}'",
                             texto_original=f"doc {g('doc')}, cargo '{cargo}'", procedencia=proc)
        try:
            devolvido = dinheiro_br(g("devolvido")) if g("devolvido") else None
        except ValorIlegivel:
            devolvido = None
        nome = g("solicitante") if parlamentar else None
        mat = (g("matricula") if parlamentar else None) or None
        ref = (f"mat:{mat}" if mat else f"nome:{normalizar_nome(nome)}") if parlamentar else None
        return Despesa(
            chave=chave, fonte=self.id, item=item.chave, tipo="diaria_municipal", ref_parlamentar=ref,
            beneficiario_tipo="parlamentar" if parlamentar else "servidor", nome_beneficiario=nome,
            cargo_original=cargo, data=inicio, competencia=f"{inicio.year}-{inicio.month:02d}", ano=ano,
            categoria_original="Diárias", valor=valor, documento_url=URL,
            # o texto do objetivo cita o nome de quem viajou: só fica no caso de parlamentar
            descricao=((g("destino") + " — " + g("objetivo")) if parlamentar else g("destino")) or None,
            procedencia=proc,
            extra={"doc": g("doc"), "matricula": mat, "fim": g("fim"), "transporte": g("transporte") or None,
                   "qtde": g("qtde"), "valor_un": g("valor_un"),
                   "devolvido": str(devolvido) if devolvido is not None else None,
                   "marcas": ["devolvida"] if devolvido else []},
        )
