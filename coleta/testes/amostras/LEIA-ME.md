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
