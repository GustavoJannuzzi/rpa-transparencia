# Amostras dos testes

Gravadas pelo próprio robô em 2026-11-25 e geradas por `python -m coleta.testes.gerar_amostras`.

São as respostas reais dos portais, com estas trocas antes de entrar no repositório:

- nome e matrícula de servidor: tarjados nos PDFs; nos JSON e HTML, o nome vira `SERVIDOR(A) n` e a matrícula, 0 ou 9000nn;
- texto de finalidade que cita servidor: omitido no Elotech; na Prefeitura e no Betha, fica com o nome trocado;
- CPF de pessoa física (fornecedor ou deputado) e nome de passageiro: apagados;
- HTML: só a tabela e o contador da página (o resto é o menu do portal).

Parlamentar mantém o nome, que é o dado público que a plataforma mostra.

## Fontes novas (2026-11-26)

`elotech/`, `cldf/`, `almg/` e `alesp/` vêm de `python -m coleta.testes.gerar_amostras_casas`, a partir dos
originais da coleta de 26/11/2026, com estas trocas:

- Elotech (Câmara de Maringá): o nome de quem não é vereador vira `SERVIDOR TARJADO n`, e a matrícula sai; o motivo
  da viagem (texto livre) é omitido; o cadastro de pessoal fica só com os vereadores e um servidor tarjado;
- CLDF: o CPF do deputado e o do fornecedor pessoa física viram números de dígitos repetidos (`111.111.111-11`),
  que não fecham o dígito verificador; o nome do fornecedor pessoa física é tarjado; a planilha XLSX é escrita de
  novo, só com as linhas escolhidas (datas nos dois formatos e duas linhas com as colunas deslocadas);
- ALMG e ALESP: o mesmo para o emitente ou fornecedor pessoa física.

## Assembleias lidas pela tela (2026-11-26)

`alap/`, `alece/`, `aleto/`, `alba/`, `alego/`, `alepe/` e `alrn/` são originais da coleta de 26/11/2026 no
navegador, escolhidos para os testes dos leitores:

- AP: o bloco do resultado do POST (sem menu, scripts e gráfico), um iframe de detalhe e a resposta AJAX dos
  gabinetes como veio (UTF-8 codificado duas vezes);
- CE: a página 1 da lista (só a tabela e a paginação), um detalhe e as linhas do mesmo deputado no CSV do mês; o
  CPF do próprio deputado, que a casa põe na coluna "CNPJ" do reembolso, virou `11111111111` (não fecha o dígito
  verificador) e o nome civil dele, `DEPUTADO (NOME CIVIL TARJADO)`;
- TO: as palavras com coordenadas de um PDF mensal (o que o robô guarda do PDF), com a data escrita errado e o
  item 13 que a planilha da casa pula; e mais sete PDFs da coleta de 27/11/2026, um para cada forma da planilha
  (os rótulos de 2023 com o saldo negativo entre parênteses, o transporte do mês anterior, o número que o PDF
  parte em dois, a nota sem item, o valor com uma casa decimal, a coluna de saldo que não fecha e a cota
  proporcional sem saldo atual); o emitente pessoa física vira `TARJADO` e o CPF dele, `111.111.111-11`;
- BA: o trecho da tabela de uma página da lista e de dois detalhes (o original que o robô guarda), um deles
  com glosa;
- GO: a resposta do detalhe de um deputado num mês (sem foto, e-mail e redes) e a linha dele no dado aberto;
- PE: um pedido, as notas dele e as rubricas do ano;
- RN: seis linhas da resposta da pesquisa, com a contagem, a soma e os totais por categoria recalculados.
