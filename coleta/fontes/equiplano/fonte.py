"""Equiplano (`<cidade>pr.equiplano.com.br:<porta>`): robô de navegador para
qualquer câmara que usa o portal.

O formulário "Empenhos de Diárias Concedidas" é Java/Tomcat com jQuery, e cada
passo depende do anterior, como para uma pessoa:

1. **Entidade.** A instalação é do município (Prefeitura, Câmara, autarquias, na
   mesma porta). Escolher a Câmara dispara um AJAX que preenche o select de
   exercícios; o robô espera essa resposta, não um tempo fixo.
2. **Exercício.** Escolher o ano recarrega a página inteira (POST). Depois da
   recarga o robô confere que a entidade e o ano continuam escolhidos.
3. **Período.** Obrigatório, e a tela não avisa: sem ele, "Visualizar" devolve
   "Período de Empenho inválido" depois de recarregar. O campo tem máscara que
   reage à tecla (`onkeypress`), então o robô digita a data como uma pessoa e
   confere o valor que ficou.
4. **Visualizar.** O POST devolve o arquivo como anexo, e a página fica esperando
   o cookie `fileDownload`. O robô intercepta a resposta, tira CPF e RG na memória
   (`relatorio.limpar`) e só então deixa o navegador receber e grava o original.
   Ano sem diária responde "Não houve concessão de diárias para o período
   selecionado": isso é resultado (zero), não erro.
5. **O relatório.** O "CSV" é o relatório impresso (`relatorio.ler`). A
   conferência é a do próprio papel: a soma dos empenhos líquidos tem de dar o
   "TOTAL DE EMPENHOS LÍQUIDOS DE DIÁRIAS DO PERÍODO", e o número de blocos
   "Empenho" lidos tem de dar o que está no arquivo.

Quem é vereador: a natureza da despesa do empenho ("3.3.90.14.14.03 AGENTES
POLÍTICOS", do plano de contas do TCE-PR). Em algumas câmaras a descrição também
traz "CARGO/FUNÇÃO: ..."; quando as duas não batem, o nome é descartado e a
linha vai para revisão. Servidor nunca tem nome gravado. A descrição e o objetivo
da viagem são texto livre e podem citar servidor: só o destino é publicado.

O servidor do Equiplano não manda o certificado intermediário da cadeia TLS. O
navegador completa a cadeia sozinho (como para qualquer pessoa); o robots.txt,
que o robô lê antes, vem pelo navegador também (`Educacao`, `buscar`).
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from ... import config
from ...entidades import EntidadeEquiplano
from ...modelo import Descoberta, Despesa, ItemInventario, Pendencia, PessoaFonte, Resultado, SistemaOrigem, TotalOficial
from ...nucleo.banco import agora
from ...nucleo.erros import FalhaTransitoria, PortalMudou
from ...nucleo.evidencia import guardar_original
from ...nucleo.texto import ValorIlegivel, chave_hash, dinheiro_br, normalizar_nome
from ..base import FonteComCpfNaTela
from . import relatorio as rel

if TYPE_CHECKING:  # pragma: no cover
    from playwright.async_api import Download

SEL_ENTIDADE = "#formulario\\.codEntidade"
SEL_EXERCICIO = "#formulario\\.exercicio"
SEL_INICIO = "#formulario\\.periodo\\.dtInicio"
SEL_FIM = "#formulario\\.periodo\\.dtFinal"
SEL_CSV = "#tpFormatoExterno_CSV"
SEL_VISUALIZAR = "input[type=button][value='Visualizar']"
SEL_MENSAGEM = "#mensagem"
# A natureza da despesa de quem tem mandato (subelemento 3.3.90.14.14.03 do TCE-PR)
NATUREZA_PARLAMENTAR = "AGENTES POLITICOS"
PALAVRAS_SEM_PESO = {"DE", "DA", "DO", "DAS", "DOS", "D"}


def _tokens(nome: str) -> set[str]:
    return set(normalizar_nome(nome).split()) - PALAVRAS_SEM_PESO


def eh_a_camara(texto_opcao: str, municipio: str) -> bool:
    """A opção é a Câmara deste município: "Câmara Municipal de Piên", "Santo Antônio
    Sudoeste Camara Municipal", "Camara Municipal de Rio Bonito do Iguacu", "CM CIDADE
    GAUCHA", "Câmara Municipal de Itapejara DOeste" (o apóstrofo sumiu e colou as palavras)."""
    t = _tokens(texto_opcao)
    if not ({"CAMARA", "LEGISLATIVO", "CM"} & t):
        return False
    junto = normalizar_nome(municipio).replace(" ", "")
    return _tokens(municipio) <= t or junto in normalizar_nome(texto_opcao).replace(" ", "")


def _data(texto: str | None) -> date | None:
    if not texto:
        return None
    m = rel.RE_DATA.match(texto)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _parece_vereador(cargo: str | None) -> bool:
    from ...de_para import RE_PARECE_PARLAMENTAR, eh_cargo_parlamentar

    return eh_cargo_parlamentar(cargo) or bool(RE_PARECE_PARLAMENTAR.search(normalizar_nome(cargo)))


class Equiplano(FonteComCpfNaTela):
    grupo = "equiplano"
    ua = config.UA_ROBO
    pausa = 2.0

    def __init__(self, ent: EntidadeEquiplano) -> None:
        self.ent = ent
        self.id = ent.fonte
        self.sistema = SistemaOrigem(
            fonte=ent.fonte, casa=ent.casa, sistema="Portal da Transparência Equiplano", fornecedor="Equiplano", modo="robo",
            cobre_de=ent.de, cobre_ate=ent.ate, endereco=ent.tela,
            o_que_tem=(f"Empenhos de diárias da Câmara de {ent.municipio}, ano a ano, pelo relatório que o formulário do portal "
                       "gera; quem é vereador sai da natureza da despesa (agentes políticos)."),
        )
        super().__init__()

    # ------------------------------------------------------------------ passos do formulário
    async def _abrir_formulario(self) -> None:
        assert self.pagina is not None
        await self.ir(self.ent.tela, wait_until="networkidle")
        if await self.pagina.locator(SEL_ENTIDADE).count() == 0:
            raise PortalMudou("o formulário de diárias não tem mais o select de entidade")

    async def _opcao_da_camara(self) -> str:
        assert self.pagina is not None
        opcoes = await self.pagina.eval_on_selector(SEL_ENTIDADE, "s => Array.from(s.options).map(o => [o.value, o.text.trim()])")
        texto = next((t for v, t in opcoes if v == str(self.ent.entidade)), None)
        if texto is None:
            raise PortalMudou(f"a entidade {self.ent.entidade} não está mais no formulário de {self.ent.host}")
        if not eh_a_camara(texto, self.ent.municipio):
            raise PortalMudou(f"a entidade {self.ent.entidade} de {self.ent.host} é '{texto}', não a Câmara de {self.ent.municipio}; "
                              "a configuração aponta para a entidade errada")
        return texto

    async def _escolher_entidade(self) -> list[str]:
        """Escolhe a Câmara e espera o AJAX que carrega os exercícios. Devolve os anos."""
        assert self.pagina is not None
        async with self.educacao.vez(self.ent.host):
            try:
                async with self.pagina.expect_response(lambda r: "loadAjaxExercicios" in r.url, timeout=45000) as resp:
                    await self.pagina.select_option(SEL_ENTIDADE, str(self.ent.entidade))
                r = await resp.value
            except Exception as e:
                raise FalhaTransitoria("o AJAX dos exercícios não respondeu") from e
        if r.status >= 500:
            raise FalhaTransitoria(f"HTTP {r.status} no AJAX dos exercícios")
        try:
            j = await r.json()
            anos = [str(o["valor"]) for o in j["opcoesParaSelect"] if str(o.get("valor", "")).isdigit()]
        except Exception as e:
            raise PortalMudou("a resposta dos exercícios veio em outro formato") from e
        # o select é preenchido pela própria página com a resposta: espera ela terminar
        await self.pagina.wait_for_function(
            "n => document.getElementById('formulario.exercicio').options.length >= n", arg=len(anos), timeout=15000)
        return anos

    async def _escolher_exercicio(self, ano: int) -> None:
        """Escolher o ano recarrega a página (POST): espera a recarga e confere o que ficou."""
        assert self.pagina is not None
        async with self.educacao.vez(self.ent.host):
            try:
                async with self.pagina.expect_navigation(timeout=60000):
                    await self.pagina.select_option(SEL_EXERCICIO, str(ano))
            except Exception as e:
                raise FalhaTransitoria("a recarga da página depois do exercício não terminou") from e
        await self.pagina.wait_for_load_state("networkidle")
        ficou = await self.pagina.evaluate(
            "() => [document.getElementById('formulario.codEntidade').value, document.getElementById('formulario.exercicio').value]")
        if ficou != [str(self.ent.entidade), str(ano)]:
            raise FalhaTransitoria(f"a recarga não guardou a entidade e o ano (ficou {ficou})")

    async def _digitar_periodo(self, ano: int) -> None:
        """O período é obrigatório e tem máscara por tecla: digita como uma pessoa e confere."""
        assert self.pagina is not None
        for seletor, digitos, esperado in ((SEL_INICIO, f"0101{ano}", f"01/01/{ano}"), (SEL_FIM, f"3112{ano}", f"31/12/{ano}")):
            campo = self.pagina.locator(seletor)
            await campo.click()
            await campo.press("Control+A")
            await campo.press("Delete")
            await campo.press_sequentially(digitos, delay=40)
            await self.pagina.keyboard.press("Tab")
            valor = await campo.input_value()
            if valor != esperado:
                raise PortalMudou(f"o campo de período ficou '{valor}' depois de digitar {esperado}: a máscara mudou")

    async def _gerar(self) -> bytes | None:
        """Clica em Visualizar com o formato CSV. Devolve o relatório já sem CPF e RG, ou
        None quando a tela diz que não houve diária no período."""
        assert self.pagina is not None
        await self.pagina.check(SEL_CSV)
        recebido: dict[str, str] = {}
        relatorio: list[bytes] = []

        async def interceptar(route):
            # o arquivo é limpo aqui, na memória, antes de o navegador recebê-lo
            try:
                resp = await route.fetch(max_redirects=0)
            except Exception as e:
                recebido["erro"] = f"{type(e).__name__}: {str(e)[:200]}"
                await route.abort()
                return
            disp = (resp.headers.get("content-disposition") or "").lower()
            if resp.status == 200 and "attachment" in disp:
                try:
                    limpo = rel.limpar(await resp.body())
                except ValueError as e:
                    recebido["erro"] = str(e)
                    await route.abort()
                    return
                relatorio.append(limpo)
                recebido["relatorio"] = "ok"
                await route.fulfill(response=resp, body=limpo)
            else:
                recebido["sem_arquivo"] = str(resp.status)
                await route.fulfill(response=resp)

        baixados: list[Download] = []

        def ao_baixar(d: Download) -> None:
            baixados.append(d)

        self.pagina.on("download", ao_baixar)
        await self.pagina.route("**/empenhosDiariasConcedidas/process*", interceptar)
        try:
            async with self.educacao.vez(self.ent.host):
                await self.pagina.click(SEL_VISUALIZAR)
                mensagem = ""
                for _ in range(360):  # até 3 minutos: o relatório de um ano cheio demora
                    if "relatorio" in recebido or "erro" in recebido:
                        break
                    if "sem_arquivo" in recebido:
                        try:
                            await self.pagina.wait_for_load_state("networkidle", timeout=5000)
                            mensagem = (await self.pagina.locator(SEL_MENSAGEM).inner_text()).strip()
                        except Exception:
                            mensagem = ""
                        if mensagem:
                            break
                    await asyncio.sleep(0.5)
        finally:
            await self.pagina.unroute("**/empenhosDiariasConcedidas/process*")
            self.pagina.remove_listener("download", ao_baixar)
            for d in baixados:  # o arquivo que o navegador baixou já é o limpo; não fica
                try:
                    await d.delete()
                except Exception:
                    pass
        if "erro" in recebido:
            raise FalhaTransitoria(f"o relatório não veio: {recebido['erro']}")
        if relatorio:
            return relatorio[0]
        m = normalizar_nome(mensagem)
        if rel.SEM_DIARIAS in m:
            return None
        if "PERIODO" in m and "INVALIDO" in m:
            raise PortalMudou("a tela recusou o período digitado ('Período de Empenho inválido')")
        if mensagem:
            raise PortalMudou(f"a tela respondeu sem relatório: {mensagem[:200]!r}")
        raise FalhaTransitoria("o relatório não veio em 3 minutos")

    # ------------------------------------------------------------------ descobrir e coletar
    async def descobrir(self) -> Descoberta:
        await self._abrir_formulario()
        texto = await self._opcao_da_camara()
        anos = await self._escolher_entidade()
        teto = min(self.ent.ate, int(agora()[:4]))  # o exercício do ano seguinte às vezes já está aberto
        alvo = sorted(int(a) for a in anos if self.ent.de <= int(a) <= teto)
        assert self.pagina is not None
        proc = self.procedencia(self.ent.tela, guardar_original(self.con, self.id, (await self.pagina.content()).encode("utf-8"),
                                                                 self.ent.tela, "html"), "select de entidade e exercícios")
        totais = [TotalOficial(fonte=self.id, escopo="entidade", metrica="entidade", valor=texto,
                               texto_original=f"código {self.ent.entidade}; exercícios {', '.join(sorted(anos))}", procedencia=proc)]
        itens = [ItemInventario(chave=f"diarias-{a}", descricao=f"Empenhos de diárias {a}", periodo=str(a), parametros={"ano": a})
                 for a in alvo]
        return Descoberta(itens=itens, totais=totais)

    async def coletar_item(self, item: ItemInventario) -> Resultado:
        assert self.pagina is not None
        ano = int(item.parametros["ano"])
        await self._abrir_formulario()
        await self._opcao_da_camara()
        anos = await self._escolher_entidade()
        if str(ano) not in anos:
            raise PortalMudou(f"o exercício {ano} sumiu do formulário")
        await self._escolher_exercicio(ano)
        await self._digitar_periodo(ano)
        corpo = await self._gerar()
        url = f"{self.ent.host}/transparencia/empenhosDiariasConcedidas/process (entidade {self.ent.entidade}, {ano}, CSV)"
        if corpo is None:
            h = guardar_original(self.con, self.id, (await self.pagina.content()).encode("utf-8"), url, "html")
            proc = self.procedencia(url, h, "mensagem da tela")
            return Resultado(totais=[
                TotalOficial(fonte=self.id, escopo=item.chave, metrica="registros", valor="0",
                             texto_original="Não houve concessão de diárias para o período selecionado.", procedencia=proc),
                TotalOficial(fonte=self.id, escopo=item.chave, metrica="total_liquido", valor="0", procedencia=proc)])
        h = guardar_original(self.con, self.id, corpo, url, "csv")
        r = rel.ler(corpo.decode(rel.CODIFICACAO, errors="replace"))
        self._conferir_cabecalho(r, ano)
        return self._resultado(item, ano, r, url, h)

    def _conferir_cabecalho(self, r: rel.Relatorio, ano: int) -> None:
        if not eh_a_camara(r.entidade, self.ent.municipio):
            raise PortalMudou(f"o relatório veio com o cabeçalho de outra entidade: '{r.entidade}'")
        if (r.inicio, r.fim) != (f"01/01/{ano}", f"31/12/{ano}"):
            raise PortalMudou(f"o relatório é do período {r.inicio} a {r.fim}, não do ano {ano} pedido")
        if r.total_liquido is None:
            raise PortalMudou("o relatório não trouxe o total de empenhos líquidos do período")

    def _resultado(self, item: ItemInventario, ano: int, r: rel.Relatorio, url: str, h: str) -> Resultado:
        proc0 = self.procedencia(url, h, "rodapé do relatório")
        res = Resultado(totais=[
            TotalOficial(fonte=self.id, escopo=item.chave, metrica="registros", valor=str(r.empenhos_no_arquivo),
                         texto_original="blocos 'Empenho' no arquivo", procedencia=proc0),
            TotalOficial(fonte=self.id, escopo=item.chave, metrica="total_liquido", valor=str(r.total_liquido),
                         texto_original=r.total_texto, procedencia=proc0),
        ])
        if r.atualizado_em:
            res.totais.append(TotalOficial(fonte=self.id, escopo=item.chave, metrica="atualizado_em", valor=r.atualizado_em,
                                           texto_original=f"atualizados até {r.atualizado_em}", procedencia=proc0))
        for p in r.problemas:
            res.pendencias.append(Pendencia(fonte=self.id, chave=chave_hash(self.id, ano, "problema", p.linha), motivo=p.motivo,
                                            texto_original=p.texto, procedencia=self.procedencia(url, h, f"linha {p.linha + 1} do arquivo")))
        vistos: dict[str, int] = {}
        for e in r.empenhos:
            proc = self.procedencia(url, h, f"empenho {e.numero}, linha {e.linha + 1} do arquivo")
            base = chave_hash(self.id, ano, e.numero)
            n = vistos.get(base, 0)
            vistos[base] = n + 1
            res.despesas.append(self._despesa(item, ano, e, chave_hash(base, n) if n else base, proc))
            d = res.despesas[-1]
            if d.beneficiario_tipo == "parlamentar" and d.ref_parlamentar:
                res.pessoas.append(PessoaFonte(fonte=self.id, ref=d.ref_parlamentar, periodo=str(ano), nome=d.nome_beneficiario or "",
                                               matricula=e.codigo_credor, casa=self.ent.casa, procedencia=proc))
        return res

    def _despesa(self, item: ItemInventario, ano: int, e: rel.EmpenhoLido, chave: str, proc) -> Despesa:
        parlamentar = normalizar_nome(e.natureza) == NATUREZA_PARLAMENTAR
        nota_cargo = None
        if e.cargo_na_descricao is not None and parlamentar != _parece_vereador(e.cargo_na_descricao):
            # a natureza e o cargo escrito na descrição dizem coisas diferentes: sem nome
            nota_cargo = (f"natureza '{e.natureza}' e cargo na descrição '{e.cargo_na_descricao}' não batem")
            parlamentar = False
        itens = sum(e.itens, Decimal(0)) if e.itens else None
        total_diarias = None
        if e.valor_total_diarias:
            try:
                total_diarias = dinheiro_br(e.valor_total_diarias)
            except ValorIlegivel:
                total_diarias = None
        dif = [abs(x - e.valor) for x in (itens, total_diarias) if x is not None]
        if e.problemas:
            consistencia = "diverge: " + "; ".join(e.problemas)
        elif any(d > Decimal("0.01") for d in dif):
            consistencia = f"diverge: empenhado {e.valor}, itens {itens}, valor total das diárias {total_diarias}"
        elif any(d for d in dif):
            consistencia = "ok (diferença de R$ 0,01 de arredondamento entre o item e o empenho)"
        else:
            consistencia = "ok"
        marcas = []
        if e.estornos and e.estornado == e.valor:
            marcas.append("cancelada")
        elif e.estornos:
            marcas.append("cancelada_parcialmente")
        empenho = _data(e.data)
        inicio = _data(e.data_inicial)
        competencia = f"{ano}-{empenho.month:02d}" if empenho and empenho.year == ano else f"{ano}-01"
        ref = (f"mat:{e.codigo_credor}" if e.codigo_credor else f"nome:{normalizar_nome(e.nome_credor)}") if parlamentar else None
        return Despesa(
            chave=chave, fonte=self.id, item=item.chave, tipo="diaria_municipal", casa=self.ent.casa, ref_parlamentar=ref,
            beneficiario_tipo="parlamentar" if parlamentar else "servidor",
            nome_beneficiario=e.nome_credor if parlamentar else None, cargo_original=e.natureza,
            data=inicio or empenho, competencia=competencia, ano=ano, categoria_original="Diária", valor=e.liquido,
            documento_url=self.ent.tela, descricao=e.destino, procedencia=proc,
            extra={"empenho": e.numero, "data_empenho": e.data, "natureza": f"{e.natureza_codigo} {e.natureza}".strip(),
                   "valor_empenho": str(e.valor), "valor_anulado": str(e.estornado),
                   "estornos": [{"numero": m.numero, "data": m.data, "valor": str(m.valor)} for m in e.estornos],
                   "liquidado": str(sum((m.valor for m in e.liquidacoes), Decimal(0))),
                   "pago": str(sum((m.valor for m in e.pagamentos), Decimal(0)) - sum((m.valor for m in e.estornos_pagamento), Decimal(0))),
                   "itens": str(itens) if itens is not None else None, "quantidade": e.numero_diarias, "valor_diaria": e.valor_diaria,
                   "data_final": e.data_final, "marcas": marcas, "consistencia": consistencia,
                   "cargo_na_descricao": e.cargo_na_descricao if (parlamentar or nota_cargo) else None,
                   "nota_cargo": nota_cargo, "codigo_credor": e.codigo_credor if parlamentar else None},
        )
