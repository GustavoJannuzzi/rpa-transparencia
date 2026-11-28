"""Um portal Govbr Pronim falso, local, para testar o robô sem rede.

Imita o que o robô enfrenta no portal de verdade (Pato Branco, 26/11/2026): um
formulário único, o ano com valor de chave interna, a entidade que vem por AJAX
depois do ano, o período que vem preenchido com o mês corrente e tem máscara por
tecla, o tipo de despesa que carrega os desdobramentos por AJAX, o "Gerar" que
chama `validarReCaptcha()` e envia o formulário, e a resposta com "Filtros
Utilizados" e a tabela por credor.

**A tabela mostra o CPF sem máscara**, nos três jeitos vistos: formatado, os 11
dígitos colados e sem o zero à esquerda (10 dígitos). Os números são inventados,
mas fecham os dígitos verificadores, para as travas poderem pegá-los. Nomes
inventados.
"""

from __future__ import annotations

import html
import json
import threading
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .equiplano_falso import cpf_valido

MUNICIPIO = "Vila Exemplo"
CAMINHO = "/pronimtb_cm/index.asp"
ANOS = {"2026": "2026|DW_LC131_FC_13|", "2025": "2025|DW_LC131_FC_12|", "2024": "2024|DW_LC131_FC_11|"}
AGENTES = "3.3.90.14.14.03.00"

VEREADORA = "Fulana de Exemplo"
SERVIDOR = "Beltrano Servidor Ficticio"
COLABORADORA = "Sicrana Colaboradora Ficticia"
CPF_VEREADORA = cpf_valido("314159265")                                   # formatado
CPF_SERVIDOR = cpf_valido("271828182").replace(".", "").replace("-", "")  # 11 dígitos colados
PREFEITURA = "Secretario da Prefeitura Ficticio"
CPF_PREFEITURA = cpf_valido("173205080")
CPF_COLABORADORA = cpf_valido("014142135").replace(".", "").replace("-", "").lstrip("0")  # sem o zero à esquerda

# (credor, documento como a tela mostra, desdobramento, mês) -> (empenhado, anulado)
LANCAMENTOS = [
    (VEREADORA, CPF_VEREADORA, AGENTES, 2, Decimal("1694.49"), Decimal("0")),
    (VEREADORA, CPF_VEREADORA, AGENTES, 5, Decimal("968.28"), Decimal("484.14")),
    (SERVIDOR, CPF_SERVIDOR, "3.3.90.14.14.02.00", 2, Decimal("484.14"), Decimal("0")),
    (SERVIDOR, CPF_SERVIDOR, "3.3.90.14.14.02.00", 9, Decimal("242.07"), Decimal("242.07")),
    (COLABORADORA, CPF_COLABORADORA, "3.3.90.14.99.00.00", 11, Decimal("121.04"), Decimal("0")),
]


def _br(v: Decimal) -> str:
    inteiro, _, cent = f"{v:.2f}".partition(".")
    grupos: list[str] = []
    while inteiro:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    return f"R$ {'.'.join(grupos)},{cent}"


def _tabela(ano: int, ini: str, fim: str, desd: list[str]) -> list[tuple[str, str, Decimal, Decimal]]:
    d0 = tuple(int(x) for x in reversed(ini.split("/")))
    d1 = tuple(int(x) for x in reversed(fim.split("/")))
    soma: dict[tuple[str, str], list[Decimal]] = {}
    for nome, doc, ds, mes, emp, anul in LANCAMENTOS:
        if desd and ds not in desd:
            continue
        if not (d0 <= (ano, mes, 1) and (ano, mes, 1) <= d1):
            continue
        s = soma.setdefault((nome, doc), [Decimal(0), Decimal(0)])
        s[0] += emp
        s[1] += anul
    return [(n, d, e, a) for (n, d), (e, a) in sorted(soma.items())]


PAGINA = """<!DOCTYPE html><html><head><meta charset="iso-8859-1"><title>TransparênciaBR</title>
<script>
function consultarDados() {{ fetch('acao.asp?acao=ConsultarUnidadeCP&ano=' + encodeURIComponent(document.getElementById('cmbAno').value)).then(r => r.json()).then(j => {{
  var s = document.getElementById('cmbUnidadeCP'); s.innerHTML = ''; var o = document.createElement('option'); o.value = j.valor; o.text = j.texto; s.add(o); }}); }}
function formataData(c) {{ var d = c.value.replace(/\\D/g, '').slice(0, 8); var v = d; if (d.length > 4) v = d.slice(0,2) + '/' + d.slice(2,4) + '/' + d.slice(4); else if (d.length > 2) v = d.slice(0,2) + '/' + d.slice(2); c.value = v; }}
function preencheNaturezaDespesa() {{ var s = document.getElementById('cmbDesdobramentoDespesa');
  fetch('acao.asp?acao=BuscaTipoDespesas').then(r => r.json()).then(j => {{ s.innerHTML = ''; for (const d of j) {{ var o = document.createElement('option'); o.value = d[0]; o.text = d[1]; s.add(o); }} s.disabled = false; }}); }}
async function validarReCaptcha() {{ document.getElementById('confirma').click(); }}
</script></head><body>
<form name="frmFormulario" id="frmFormulario" method="post" action="">
<input type="hidden" name="hndAcao" id="hndAcao" value="3"><input type="hidden" name="hndItem" id="hndItem" value="15">
<select name="cmbAno" id="cmbAno" onchange="consultarDados();">{anos}</select>
<select name="cmbUnidadeCP" id="cmbUnidadeCP"></select>
<input type="text" name="txtDataInicial" id="txtDataInicial" maxlength="10" value="01/11/2026" onkeyup="formataData(this);">
<input type="text" name="txtDataFinal" id="txtDataFinal" maxlength="10" value="30/11/2026" onkeyup="formataData(this);">
<select name="cmbUnidadeGestora" id="cmbUnidadeGestora"><option value="-1">CONSOLIDADA</option><option value="1">CÂMARA MUNICIPAL</option>
  <option value="0">PREFEITURA MUNICIPAL</option></select>
<select name="cmbDiariasPassagens" id="cmbDiariasPassagens" onchange="preencheNaturezaDespesa();">
  <option value="0">SELECIONE</option><option value="1">DIÁRIAS</option><option value="2">PASSAGENS E DESPESAS COM LOCOMOÇÃO</option></select>
<select name="cmbDesdobramentoDespesa" id="cmbDesdobramentoDespesa" multiple="true" disabled="true"></select>
<input type="button" value="Gerar" class="clsbutton" onclick="validarReCaptcha()" />
<input type="submit" name="confirma" id="confirma" value="" style="display:none">
</form>
{resultado}
</body></html>"""


class Portal:
    """O estado do servidor e as falhas a injetar, uma por pedido de "Gerar", na ordem."""

    def __init__(self, falhas: list[str] | None = None):
        self.falhas = list(falhas or [])
        self.gerados = 0
        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.base = f"http://127.0.0.1:{self.servidor.server_address[1]}/pronimtb_cm"
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()

    def fechar(self) -> None:
        self.servidor.shutdown()

    def pagina(self, resultado: str = "") -> bytes:
        anos = "".join(f'<option value="{v}">{a}</option>' for a, v in ANOS.items())
        return PAGINA.format(anos=anos, resultado=resultado).encode("latin-1", "xmlcharrefreplace")

    def gerar(self, dados: dict[str, list[str]]) -> bytes:
        self.gerados += 1
        falha = self.falhas.pop(0) if self.falhas else ""
        ano_val = dados.get("cmbAno", [""])[0]
        ano = int(ano_val.split("|")[0]) if ano_val else 0
        ini, fim = dados.get("txtDataInicial", [""])[0], dados.get("txtDataFinal", [""])[0]
        tipo = dados.get("cmbDiariasPassagens", ["0"])[0]
        desd = dados.get("cmbDesdobramentoDespesa", [])
        periodo = f"{ini} a {fim}" if falha != "periodo_errado" else "01/11/2026 a 30/11/2026"
        ug = dados.get("cmbUnidadeGestora", ["-1"])[0]
        ug_txt = {"-1": "CONSOLIDADA", "1": "CÂMARA MUNICIPAL", "0": "PREFEITURA MUNICIPAL"}.get(ug, "?")
        filtros = (f'<table><tr><td>Filtros Utilizados</td></tr><tr><td>Exercício</td><td>{ano}</td><td>Período</td><td>{periodo}</td></tr>'
                   f'<tr><td>Unidade Gestora</td><td>{ug_txt}</td><td>Tipo de Despesa</td><td>{"DIÁRIAS" if tipo == "1" else "?"}</td></tr></table>')
        linhas = _tabela(ano, ini, fim, desd)
        if ug != "1" and linhas:  # o consolidado e a Prefeitura trazem credor de fora da Câmara
            linhas = sorted(linhas + [(PREFEITURA, CPF_PREFEITURA, Decimal("999.99"), Decimal("0"))])
        if not linhas:
            corpo = filtros + "<p>Não há informações de empenho para o filtro selecionado.</p>"
        else:
            tr = "".join(f"<tr><td>{html.escape(n)}</td><td>{d}</td><td>{_br(e)}</td><td>R$ 0,00</td><td>{_br(e - a)}</td>"
                         f"<td>{_br(e - a)}</td><td>{_br(a)}</td></tr>" for n, d, e, a in linhas)
            corpo = (filtros + '<table><tr><td>Diárias/Passagens/Adiantamento de Viagem/Reembolsos</td></tr>'
                     '<tr><th>Nome</th><th>CNPJ/CPF</th><th>Valor Empenhado</th><th>Valor Em Liquidação</th><th>Valor Liquidado</th>'
                     f'<th>Valor Pago</th><th>Valor Anulado</th></tr>{tr}</table>')
        return self.pagina(corpo)

    def _handler(self):
        portal = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _envia(self, status: int, corpo: bytes, tipo: str):
                self.send_response(status)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            def do_GET(self):
                u = urlsplit(self.path)
                q = parse_qs(u.query)
                if u.path == CAMINHO:
                    return self._envia(200, portal.pagina(), "text/html; charset=iso-8859-1")
                if u.path.endswith("/acao.asp") and q.get("acao") == ["ConsultarUnidadeCP"]:
                    return self._envia(200, json.dumps({"valor": q.get("ano", [""])[0], "texto": f"CÂMARA MUNICIPAL DE {MUNICIPIO.upper()}"}).encode(),
                                       "application/json")
                if u.path.endswith("/acao.asp") and q.get("acao") == ["BuscaTipoDespesas"]:
                    lista = [[AGENTES, "AGENTES POLÍTICOS(3.3.90.14.14.03.00)"], ["3.3.90.14.14.02.00", "SERVIDORES COMISSIONADOS(3.3.90.14.14.02.00)"],
                             ["3.3.90.14.99.00.00", "OUTROS COLABORADORES(3.3.90.14.99.00.00)"]]
                    return self._envia(200, json.dumps(lista).encode(), "application/json")
                self._envia(404, b"", "text/html")

            def do_POST(self):
                tam = int(self.headers.get("Content-Length") or 0)
                dados = parse_qs(self.rfile.read(tam).decode("latin-1"))
                if urlsplit(self.path).path == CAMINHO:
                    return self._envia(200, portal.gerar(dados), "text/html; charset=iso-8859-1")
                self._envia(404, b"", "text/html")

        return H

