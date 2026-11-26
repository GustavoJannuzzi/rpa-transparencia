# Amostras dos testes

Gravadas pelo próprio robô em 2026-11-25 e geradas por `python -m coleta.testes.gerar_amostras`.

São as respostas reais dos portais, com estas trocas antes de entrar no repositório:

- nome e matrícula de servidor: tarjados nos PDFs; nos JSON e HTML, o nome vira `SERVIDOR(A) n` e a matrícula, 0 ou 9000nn;
- texto de finalidade que cita servidor: omitido no Elotech; na Prefeitura e no Betha, fica com o nome trocado;
- CPF de pessoa física (fornecedor ou deputado) e nome de passageiro: apagados;
- HTML: só a tabela e o contador da página (o resto é o menu do portal).

Parlamentar mantém o nome, que é o dado público que a plataforma mostra.
