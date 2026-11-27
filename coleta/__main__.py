"""python -m coleta descobrir | coletar | conferir | publicar | relatorio | tudo"""

from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path

import typer

from .fontes import FONTES, criar, grupo
from .nucleo import execucao
from .nucleo.banco import conectar
from .nucleo.execucao import eco

app = typer.Typer(add_completion=False, help="Robôs de transparência: coleta, conferência e publicação.")

OpcFonte = typer.Option(None, "--fonte", "-f", help="Só estas fontes, ou todas de um fornecedor (elotech, assembleia). Pode repetir.")


def _selecionar(fontes: list[str] | None) -> list[str]:
    ids = [f.id for f in FONTES]
    if not fontes:
        return ids
    grupos = {grupo(f) for f in FONTES}
    desconhecidas = set(fontes) - set(ids) - grupos
    if desconhecidas:
        raise typer.BadParameter(f"fontes desconhecidas: {sorted(desconhecidas)}. Existem: {ids} e os grupos {sorted(grupos - set(ids))}")
    return [f.id for f in FONTES if f.id in fontes or grupo(f) in fontes]


async def _rodar(etapa: str, ids: list[str], refazer: bool, gravar_video: bool) -> dict[str, execucao.Placar | int]:
    from .fontes.base import Contexto

    con = conectar()
    precisa_navegador = any(criar(i).usa_navegador for i in ids)
    resultados: dict = {}
    pw = navegador = None
    try:
        if precisa_navegador:
            from playwright.async_api import async_playwright

            pw = await async_playwright().start()
            navegador = await pw.chromium.launch()
        ctx = Contexto(con=con, navegador=navegador, gravar_video=gravar_video)
        for i in ids:
            fonte = criar(i)
            await fonte.abrir(ctx)
            try:
                if etapa == "descobrir":
                    eco(f"descobrir {i}")
                    try:
                        n = await execucao.descobrir(fonte)
                        eco(f"  {i}: {n} itens no inventário")
                        resultados[i] = n
                    except Exception as e:  # uma fonte fora do ar não derruba as outras
                        eco(f"  {i}: descobrir falhou — {type(e).__name__}: {str(e)[:300]}")
                        resultados[i] = e
                else:
                    eco(f"coletar {i}")
                    resultados[i] = await execucao.coletar(fonte, refazer=refazer)
            finally:
                await fonte.fechar()
    finally:
        if navegador:
            await navegador.close()
        if pw:
            await pw.stop()
        con.close()
    return resultados


@app.command()
def descobrir(fonte: list[str] | None = OpcFonte):
    """Inventário de cada fonte e os totais que a própria fonte mostra."""
    asyncio.run(_rodar("descobrir", _selecionar(fonte), False, False))


@app.command()
def coletar(fonte: list[str] | None = OpcFonte,
            refazer: bool = typer.Option(False, help="Coleta de novo até o que já está ok."),
            gravar_video: bool = typer.Option(False, help="Grava vídeo do navegador em dados/evidencias/videos.")):
    """Percorre o inventário e grava no modelo único. Rodar de novo só pega o que falta."""
    asyncio.run(_rodar("coletar", _selecionar(fonte), refazer, gravar_video))


@app.command()
def conferir():
    """Total oficial × soma coletada, contagens e checagens. O que não fecha vai para revisão."""
    from .nucleo.conferencia import conferir as _conferir

    con = conectar()
    resumo = _conferir(con)
    con.close()
    for linha in resumo:
        eco(linha)


@app.command()
def publicar():
    """Gera os JSON da plataforma, só com o que passou na conferência."""
    from .destinos.json_plataforma import publicar as _publicar

    con = conectar()
    for linha in _publicar(con):
        eco(linha)
    con.close()


OpcDe = typer.Option(..., "--de", help="O estado.db da coleta de trabalho (a pasta dele tem os originais).")
OpcFontes = typer.Option(..., "--fontes", "-f", help="As fontes a importar (separadas por vírgula ou repetindo).")
OpcSessao = typer.Option(..., "--sessao", help="O nome de quem importa, para a trava EM-USO.txt do destino.")


@app.command()
def importar(de: Path = OpcDe, fontes: list[str] = OpcFontes, sessao: str = OpcSessao,
             aceitar_pendentes: bool = typer.Option(False, help="Importa mesmo com itens pendentes ou com erro na origem.")):
    """Leva as linhas de algumas fontes de outro banco para este (o de RPA_DADOS), numa transação só."""
    from .nucleo.importar import ImportacaoRecusada, importar as _importar

    ids = [x.strip() for f in fontes for x in f.split(",") if x.strip()]
    try:
        r = _importar(de, ids, sessao, aceitar_pendentes=aceitar_pendentes)
    except ImportacaoRecusada as e:
        eco(f"importar parou sem mexer nas linhas do destino: {e}")
        raise typer.Exit(1) from e
    for linha in r.linhas():
        eco(linha)


@app.command()
def relatorio():
    """Página HTML da conferência."""
    from .destinos.relatorio_html import gerar

    con = conectar()
    caminho = gerar(con)
    con.close()
    eco(f"relatório em {caminho}")


@app.command()
def tudo(fonte: list[str] | None = OpcFonte,
         refazer: bool = typer.Option(False),
         gravar_video: bool = typer.Option(False)):
    """descobrir, coletar, conferir, publicar e relatorio, em sequência."""
    ids = _selecionar(fonte)
    asyncio.run(_rodar("descobrir", ids, False, False))
    asyncio.run(_rodar("coletar", ids, refazer, gravar_video))
    conferir()
    publicar()
    relatorio()


if __name__ == "__main__":
    if sys.platform == "win32":
        # o console do Windows não é UTF-8 por padrão
        try:
            for saida in (sys.stdout, sys.stderr):
                if isinstance(saida, io.TextIOWrapper):
                    saida.reconfigure(encoding="utf-8")
        except Exception:
            pass
    app()
