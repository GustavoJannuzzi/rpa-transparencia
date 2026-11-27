"""Um portal Equiplano falso, local, para testar o robô sem rede.

Imita o que o robô enfrenta no portal de verdade (visto em 26/11/2026): o select
de entidade que carrega os exercícios por AJAX, a recarga da página ao escolher o
exercício (o servidor guarda a escolha na sessão), o campo de período com máscara
por tecla, o período obrigatório ("Período de Empenho inválido", depois de
recarregar), o "Visualizar" que devolve o CSV como anexo e o ano sem diária.

O relatório é o "CSV" impresso, com cabeçalho de página repetido, rótulo cortado
("Estorno de "), data cortada e descrição em várias linhas, e traz **CPF e RG
inteiros**, como em Santo Antônio do Sudoeste: os números são inventados, mas
fecham os dígitos verificadores, para a trava de CPF poder pegá-los. Nomes
inventados.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

ENTIDADE = 77
MUNICIPIO = "Vila Exemplo"
FORM = "/transparencia/empenhosDiariasConcedidas"


def cpf_valido(base9: str) -> str:
    """Completa 9 dígitos com os verificadores de CPF (número inventado que fecha)."""
    d = [int(c) for c in base9]
    for tam in (9, 10):
        s = sum(d[i] * (tam + 1 - i) for i in range(tam))
        d.append((s * 10) % 11 % 10)
    t = "".join(map(str, d))
    return f"{t[:3]}.{t[3:6]}.{t[6:9]}-{t[9:]}"


CPF_VEREADORA = cpf_valido("314159265")
CPF_SERVIDORA = cpf_valido("271828182")
CPF_SOLTO = cpf_valido("161803398").replace(".", "").replace("-", "")  # 11 dígitos colados, no texto livre
NOME_VEREADORA = "FULANA DE EXEMPLO"
NOME_SERVIDORA = "BELTRANA SERVIDORA FICTICIA"

CAB = [
    ";;;;;;;CÂMARA MUNICIPAL DE VILA EXEMPLO - PR;;;;;;;;;;;;",
    ";;;;;;;;;;;;;Empenhos de Diárias Concedidas;;;;;;",
    ";;;;;;;;;;;;;;;;Período de Empenho: 01/01/{ano} a 31/12/{ano};;;;;;",
    ";;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;Página: {pagina};;;",
]


def relatorio(ano: int) -> bytes:
    def cab(p: int) -> list[str]:
        return [c.format(ano=ano, pagina=p) for c in CAB] + [""]

    linhas = cab(1) + [
        # 1) vereadora: agentes políticos, cargo também na descrição, CPF e RG inteiros
        "Empenho;;;;Data:;;;;;;Funcional:;;;;;;;;Conta:;;;Recurso:;;Natureza de ;;;;;;;;Valor:",
        f"16/{ano};;;;13/01/{ano};;;;;;01.001.01.031.0001.2.0;;;;;;;;50;;;1;;3.3.90.14.14.03  AGENTES POLÍTICOS;;;;;;;;1694,49;;",
        f"Servidor:;;;439091-1 {NOME_VEREADORA} CPF: {CPF_VEREADORA} RG: 12345678 PR   ;;;;;;",
        ";;;;;Descrição:;;;;;;",
        ";;;;;Produto;;;;;;;;Marca;;;;UN;;;;Valor;;;Quantidade;;;Valor total;",
        ";;;;;DIARIAS PARA MUNICIPIO FORA DO ESTADO;;;;;;;;;;;DIÁRIAS;;;484,14;;;3,50;;;1694,49;;",
        f';;;;;"REQUISITANTE: Fulana de Exemplo\n\nCARGO/FUNÇÃO: Vereadora\n\nCPF da requisitante: {CPF_SOLTO}\nDESTINO: Curitiba – PR.";;;;',
        "Liquidação;;;;;Data:;;;;;;;;;Valor:;;;;",
        f"10/{ano};;;;;13/01/{str(ano)[:3]};;;;1694,49;;;;",  # o relatório corta a data
        "Lei/ato autorização:;;;;Lei ordinária 1/2016;;;;;;;;Lei/ato concessão:;;;Portaria 2;;;;",
        f"Data inicial:;;;13/01/{ano};;;;;Data final:;;;;16/01/{ano};;;;;;;Número de diárias:;;;3,5;;;Valor diária:;484,14;;;;Valor total diárias:;;;1694,49;;",
        "Destino:;;Curitiba - PR;;;;;;;;;;Tipo objetivo:;;Outros;;;;",
        "Meio de transporte ;;;;;;Frota do Município;;;;",
        f'"Visita com a servidora {NOME_SERVIDORA}";;;;',
        "Pagamento;;;;;;;;;;;Data:;;;;;;Valor:;;;;",
        f"10/{ano};;;;;;;;;;;13/01/{ano};;;;1694,49;;;;",
    ] + cab(2) + [
        # 2) servidora comissionada: nome nunca gravado; estorno parcial
        "Empenho;;;;Data:;;;;;;Funcional:;;;;;;;;Conta:;;;Recurso:;;Natureza de ;;;;;;;;Valor:",
        f"17/{ano};;;;20/02/{ano};;;;;;01.001.01.031.0001.2.0;;;;;;;;50;;;1;;3.3.90.14.14.02  SERVIDORES COMISSIONADOS;;;;;;;;968,28;;",
        f"Servidor:;;;544456-0 {NOME_SERVIDORA} CPF: {CPF_SERVIDORA} RG: 9.876.543-2 PR   ;;;;;;",
        ";;;;;Descrição:;;;;;;",
        ";;;;;Produto;;;;;;;;Marca;;;;UN;;;;Valor;;;Quantidade;;;Valor total;",
        ";;;;;DIARIAS PARA MUNICIPIO NO ESTADO;;;;;;;;;;;DIÁRIAS;;;484,14;;;2,00;;;968,28;;",
        ';;;;;"REQUISITANTE: Beltrana\n\nCARGO/FUNÇÃO: Assessora Legislativa";;;;',
        "Estorno de empenho;;;;Data:;;;;Valor:;;;Motivo:;;;",
        f"4/{ano};;;;06/03/{ano};;;;484,14;;;voltou antes;;;",
        "Liquidação;;;;;Data:;;;;;;;;;Valor:;;;;",
        f"11/{ano};;;;;20/02/{ano};;;;968,28;;;;",
        "Estorno de ;;;;;Data:;;;;Valor:;;;;",  # "Estorno de liquidação", cortado
        f"2/{ano};;;;;06/03/{ano};;;;484,14;;;;",
        f"Data inicial:;;;21/02/{ano};;;;;Data final:;;;;22/02/{ano};;;;;;;Número de diárias:;;;2;;;Valor diária:;484,14;;;;Valor total diárias:;;;968,28;;",
        "Destino:;;Ponta Grossa - PR;;;;;;;;;;Tipo objetivo:;;Cursos;;;;",
        # 3) a servidora de novo, empenho estornado inteiro (viagem cancelada)
        "Empenho;;;;Data:;;;;;;Funcional:;;;;;;;;Conta:;;;Recurso:;;Natureza de ;;;;;;;;Valor:",
        f"18/{ano};;;;01/04/{ano};;;;;;01.001.01.031.0001.2.0;;;;;;;;50;;;1;;3.3.90.14.14.01  SERVIDORES EFETIVOS;;;;;;;;484,14;;",
        f"Servidor:;;;544456-0 {NOME_SERVIDORA} CPF: {CPF_SERVIDORA} RG: 9.876.543-2 PR   ;;;;;;",
        ";;;;;Produto;;;;;;;;Marca;;;;UN;;;;Valor;;;Quantidade;;;Valor total;",
        ";;;;;DIARIAS PARA MUNICIPIO NO ESTADO;;;;;;;;;;;DIÁRIAS;;;484,14;;;1,00;;;484,14;;",
        "Estorno de empenho;;;;Data:;;;;Valor:;;;Motivo:;;;",
        f"7/{ano};;;;05/04/{ano};;;;484,14;;;viagem cancelada;;;",
        # o total do período: 1694,49 + (968,28 − 484,14) + (484,14 − 484,14)
        "TOTAL DE EMPENHOS LÍQUIDOS DE DIÁRIAS DO PERÍODO: ;;;;;;;;R$ 2.178,63;;",
        "Conjunto de informações em tempo real, atualizados até 26/11/2026 21:59;;;;",
    ]
    return "\r\n".join(linhas).encode("cp1252")


PAGINA = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><title>Empenhos de Diárias Concedidas</title>
<script>
var contexto = "/transparencia";
function carregaOpcoesViaAjax(url, destino, parametros) {{
  var s = document.getElementById(destino); s.innerHTML = '<option value="0">Carregando...</option>';
  fetch(url + "?" + parametros, {{method: "POST"}}).then(r => r.json()).then(j => {{
    s.innerHTML = ""; for (const o of j.opcoesParaSelect) {{ var e = document.createElement("option"); e.value = o.valor; e.text = o.texto; s.add(e); }}
  }});
}}
function submiti(obj, action) {{ document.forms[0].action = action; document.forms[0].submit(); }}
function envia(obj, action) {{ submiti(obj, action); }}
function DataUtil() {{
  this.formata = function(ev, campo) {{
    var k = ev.which; if ("0123456789".search(String.fromCharCode(k)) != -1 && campo.value.length < 10) {{
      if (campo.value.length == 2) campo.value += "/"; if (campo.value.length == 5) campo.value += "/"; }}
  }};
  this.valida = function(o) {{ if (o.value && !/^\\d\\d\\/\\d\\d\\/\\d{{4}}$/.test(o.value)) o.value = ""; }};
}}
var dataUtil = new DataUtil();
</script></head><body>
<div id="mensagem">{mensagem}</div>
<form action="#" method="post">
<select onchange="carregaOpcoesViaAjax('empenhosDiariasConcedidas/loadAjaxExercicios', 'formulario.exercicio', 'formulario.codEntidade=' + this.value);"
  name="formulario.codEntidade" id="formulario.codEntidade"><option value=""></option>{entidades}</select>
<select onchange="submiti(null,'/transparencia/empenhosDiariasConcedidas');" name="formulario.exercicio" id="formulario.exercicio">{exercicios}</select>
<input type="text" id="formulario.periodo.dtInicio" name="formulario.periodo.dtInicio" maxlength="10" value="" onkeypress="dataUtil.formata(event, this);" onchange="dataUtil.valida(this);">
<input type="text" id="formulario.periodo.dtFinal" name="formulario.periodo.dtFinal" maxlength="10" value="" onkeypress="dataUtil.formata(event, this);" onchange="dataUtil.valida(this);">
<input type="radio" id="tpFormatoExterno_PDF" name="formulario.tpFormatoExterno" value="PDF" checked>
<input type="radio" id="tpFormatoExterno_CSV" name="formulario.tpFormatoExterno" value="CSV">
<input class="botaoImprimir" value="Visualizar" onclick="envia(this,'empenhosDiariasConcedidas/process')" type="button">
</form></body></html>"""

ANOS = ["2026", "2025", "2024", "2023"]


class Portal:
    """O estado do servidor (a sessão) e as falhas a injetar, uma por pedido, na ordem."""

    def __init__(self, falhas: dict[str, list[str]] | None = None):
        self.entidade = ""
        self.ano = ""
        self.mensagem = ""
        self.falhas = {k: list(v) for k, v in (falhas or {}).items()}
        self.pedidos: dict[str, int] = {}
        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.host = f"http://127.0.0.1:{self.servidor.server_address[1]}"
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()

    def fechar(self) -> None:
        self.servidor.shutdown()

    def falha(self, chave: str) -> str | None:
        self.pedidos[chave] = self.pedidos.get(chave, 0) + 1
        fila = self.falhas.get(chave, [])
        return fila.pop(0) if fila else None

    def pagina(self) -> bytes:
        ents = f'<option value="{ENTIDADE}"{" selected" if self.entidade == str(ENTIDADE) else ""}>Câmara Municipal de {MUNICIPIO}' \
               f'<option value="5">Município de {MUNICIPIO}</option>'
        exs = "".join(f'<option value="{a}"{" selected" if a == self.ano else ""}>{a}</option>' for a in ANOS) if self.entidade else ""
        msg, self.mensagem = self.mensagem, ""
        return PAGINA.format(mensagem=msg, entidades=ents, exercicios=exs).encode("utf-8")

    def _handler(self):
        portal = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # silêncio no pytest
                pass

            def _envia(self, status: int, corpo: bytes, tipo: str, extra: dict | None = None):
                self.send_response(status)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(corpo)))
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(corpo)

            def do_GET(self):
                if urlsplit(self.path).path == FORM:
                    return self._envia(200, portal.pagina(), "text/html;charset=UTF-8")
                self._envia(404, b"nao encontrado", "text/html")

            def do_POST(self):
                tam = int(self.headers.get("Content-Length") or 0)
                dados = {k: v[0] for k, v in parse_qs(self.rfile.read(tam).decode("latin-1")).items()}
                u = urlsplit(self.path)
                if u.path.endswith("/loadAjaxExercicios"):
                    if portal.falha("ajax") == "500":
                        return self._envia(500, b"erro", "text/plain")
                    portal.entidade = parse_qs(u.query).get("formulario.codEntidade", [""])[0]
                    corpo = json.dumps({"opcoesParaSelect": [{"valor": "", "texto": ""}] + [{"valor": a, "texto": a} for a in ANOS]})
                    return self._envia(200, corpo.encode(), "application/json;charset=UTF-8")
                if u.path == FORM:  # a recarga ao escolher o exercício
                    portal.entidade = dados.get("formulario.codEntidade", "")
                    portal.ano = dados.get("formulario.exercicio", "")
                    if portal.falha("recarga") == "perde_entidade":
                        portal.entidade = ""
                    return self._envia(200, portal.pagina(), "text/html;charset=UTF-8")
                if u.path.endswith("/process"):
                    ano = dados.get("formulario.exercicio", "")
                    if not dados.get("formulario.periodo.dtInicio") or not dados.get("formulario.periodo.dtFinal"):
                        portal.mensagem = "Período de Empenho inválido."
                    elif ano == "2024":
                        portal.mensagem = "Não houve concessão de diárias para o período selecionado."
                    elif dados.get("formulario.tpFormatoExterno") != "CSV":
                        portal.mensagem = "Formato não suportado neste teste."
                    else:
                        return self._envia(200, relatorio(int(ano)), "text/csv",
                                           {"Content-Disposition": "attachment;filename=EmpenhosDiariasConcedidas.csv",
                                            "Set-Cookie": "fileDownload=true; path=/transparencia"})
                    return self._envia(302, b"", "text/html", {"Location": FORM})
                self._envia(404, b"nao encontrado", "text/html")

        return H
