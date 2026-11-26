# Etapa 0: o que as fontes têm de verdade

Levantamento feito em 25/11/2026, antes de escrever o código, abrindo cada fonte
ao vivo. Cada achado diz de onde veio. As amostras que os testes usam estão em
`coleta/testes/amostras/`, gravadas pelo próprio robô na primeira rodada.

## 1. Sistema legado da Câmara de Curitiba: os PDFs trazem dado por vereador

O portal legado (`transparencia-legada.cmc.pr.gov.br`) é uma aplicação React em
que cada relatório é um botão. O botão chama
`GET https://transparencia-legada.cmc.pr.gov.br:3000/api/download/<arquivo>` e o
navegador baixa um PDF. O código da aplicação lista **1.331 botões**. Sem captcha,
sem login; `robots.txt` não existe nos dois endereços (404).

Abri um PDF de cada relatório:

| Relatório | Anos | O que tem | Por vereador? |
|---|---|---|---|
| **Relatório de Diárias de Custo** (`Diarias_AAAA.pdf`) | 2013–2016 | Uma linha por diária: portaria, beneficiário, matrícula (2015–2016), cargo, destino, evento, período, quantidade, valor unitário, valor total; de 2015 em diante também hospedagem, meio e valor do transporte. 2015 e 2016 trazem **total por mês e total anual** | **Sim**: 48 linhas de vereador em 2013, 18 em 2014, 15 em 2015, 7 em 2016 |
| Relatório de Despesas Pagas / Empenhadas / Liquidadas | 2010–2016 | Uma ficha por empenho: processo, credor, CNPJ, objeto, valores (249 páginas em 2016) | Não: o credor é empresa ou órgão |
| Resumo do Desdobramento da Despesa | 2010–2016 | Totais por natureza de despesa (Crystal Reports) | Não |
| Servidores Comissionados: Remuneração dos Cargos em Comissão, Vereadores e Presidente | 2015–2016 | Tabela de salário por cargo (CC-1 a CC-6) | Não; sem lotação por gabinete |
| Material de consumo, Bens permanentes, Demonstrativos fiscais, extratos bancários, atos | vários | Contabilidade e atos | Não |

**Decisão (a que o plano manda para este caso):** as diárias do legado entram na
despesa do vereador, como as do Elotech e do Betha. Os relatórios de despesa
geral ficam para a fase 2, como a série "despesas da Câmara 2010–2016".

**O que torna esse PDF difícil**, e por isso ele é o teste de verdade do robô:
- é uma planilha do LibreOffice exportada para PDF, uma página paisagem de 842 pt
  com 6 mil caracteres em corpo 3,8; a extração de texto simples embaralha as
  células de duas linhas (o período "05/12/2016 a 08/12/2016" sai como
  `0 0 5 8 /1 /1 2 2 /2 /2 0 0 1 1 6 6 a`). Só a leitura por grade da tabela sai
  limpa;
- o layout muda no meio da série: 11 colunas em 2013–2014, 15 em 2015–2016;
- o período vem em quatro formatos ("16/12/2013", "26/02 a 03/03",
  "10 a 12/03/2015", "05/12/2016 a 08/12/2016");
- a quantidade às vezes é número ("02") e às vezes texto ("02 diárias + 02
  refeições", "1+1 refeição"), com o valor unitário composto ("R$ 290,00 +
  R$ 100,00");
- linhas canceladas ("CANCELADA PELA PORTARIA 49") e devolvidas ("Devolvido")
  ficam na mesma tabela;
- 2013 e 2014 não trazem total nenhum; a conferência desses anos é só a
  consistência de cada linha (quantidade × unitário = total), e o relatório diz
  isso.

## 2. A fonte de 2024–2025 existe: o portal da Prefeitura

O cartão "Diárias anteriores a 2026" do Betha é um link (tipo `LINK` no menu que
a própria tela carrega) para o portal de transparência da **Prefeitura de
Curitiba**: `https://www.transparencia.curitiba.pr.gov.br/sgp/despesasviagemadiantamento.aspx`.

- É uma página ASP.NET WebForms: filtros de exercício, mês, órgão e tipo, botão
  Pesquisar e paginação por `__doPostBack`. O órgão **"01 – CÂMARA MUNICIPAL DE
  CURITIBA"** existe no filtro.
- Com órgão Câmara e tipo Diárias, há registros **de 2024, 2025 e 2026**; 2022 e
  2023 vêm vazios (a Câmara ainda estava no Elotech). Colunas: órgão, documento,
  solicitante, matrícula, cargo (aparece "Vereadora"), objetivo, início, fim,
  destino, transporte, diárias, valor unitário, valor das diárias, devolvido.
- "Conjunto de informações atualizadas em 25/11/2026 com dados até 24/11/2026".
- Sem captcha, sem login; `robots.txt` não existe (a URL devolve a página de erro).
- Pegadinha: com um User-Agent que o ASP.NET não reconhece como navegador, a
  página sai sem o script de `__doPostBack` e nenhum filtro funciona. O robô usa
  o User-Agent do próprio Chromium com a identificação do robô no fim.

**Decisão:** o buraco de 2024–2025 se fecha com esta fonte, que vira o quarto
sistema da linha do tempo. 2026 aparece nela e no Betha ao mesmo tempo: a
conferência usa isso para comparar os dois sistemas na fronteira.

## 3. O Elotech de Curitiba tem API

`cmcuritiba.eloweb.net` publica o mesmo serviço "Web Services" do Elotech de Ponta
Grossa: `GET /portaltransparencia-api/v3/api-docs` devolve um OpenAPI 3.0.1 sem
esquema de segurança, cujo texto diz que as APIs são "para consumo automatizado a
partir de sistemas externos".

- **Servidores**: `GET /api/servidores` está documentado (cabeçalhos `entidade` e
  `exercicio`). Devolve nome, matrícula, cargo, lotação ("GAB. VER. <nome civil>
  (<nome parlamentar>)"), natureza ("Vereador", "Comissionado"...), situação,
  admissão e remuneração. Atualizado em 25/11/2026: o Elotech segue vivo para
  pessoal, não só para 2017–2023.
- **Diárias**: `GET /api/diarias` não está no Swagger, mas é o mesmo serviço, e a
  própria tela de diárias o chama. Devolve JSON paginado com `totalElements`.
  2017 = 15 registros, 2019 = 31, 2021 = 10, 2023 = 40, **2024 = 0**.
- Pegadinha: de 2017 a 2020 a diária **não traz o nome**, só matrícula e cargo. O
  nome sai da lista de servidores do mesmo exercício (natureza "Vereador"), pela
  matrícula. Matrícula que não se resolve vai para revisão.

**Decisão (a que o plano manda):** o coletor do Elotech usa a API, sem navegador.
Navegador onde não há API; API onde há.

## 4. Betha (2026)

- `transparencia.betha.cloud`, aplicação Vue, sem captcha, sem `robots.txt`
  próprio. "Diárias 2026" (consulta 324825): 54 registros, 20 por página, total
  de registros na tela, "Última atualização dos dados em 20/11/2026 04:31".
- "Servidores Públicos – Ativos" (consulta 360082): a coluna Organograma traz o
  gabinete ("GAB. VER. <nome>") e a coluna Remuneração contratual, o valor.
- Pegadinha: com um User-Agent que contém "HeadlessChrome", o Betha devolve
  **403**; com o User-Agent próprio do robô, abre normalmente. Cada fonte tem o
  seu User-Agent, todos dizendo que é um robô.

## 5. Partido dos vereadores

Nenhum dos quatro sistemas traz partido. Vem dos dados abertos do TSE
(`cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_AAAA.zip`,
eleições de 2012, 2016, 2020 e 2024): o partido **na eleição** que deu o mandato.
O cruzamento é pelo nome civil; o que não fecha vai para revisão.

## 6. Federal: arquivo anual da CEAP

- O arquivo anual em CSV (`Ano-AAAA.csv.zip`) traz `ideCadastro`, que é o `id` do
  deputado na API. Em 2025: 209.097 linhas, todas da legislatura 57.
- **8.039 linhas de 2025 têm valor líquido negativo**. 7.204 são passagem aérea
  (SIGEPA e RPA) com o documento também negativo: compensação de bilhete, que a
  de-para conhece e aceita. As outras 835 (834 de "complementação do
  auxílio-moradia" e 1 de passagem em missão oficial) têm o líquido negativo e o
  documento **maior que zero**; a fonte não explica o sinal, então essas vão para a
  fila de revisão em vez de entrar na soma.
- Uma linha de 2025 vem sem fornecedor; 1.848 têm CPF de pessoa física no lugar
  do CNPJ (a plataforma mostra o CPF mascarado).
- O CNPJ vem formatado errado em parte das linhas (`381.942.120/0012-0` em vez de
  `38.194.212/0001-20`): o robô normaliza pelos dígitos.
- O código do documento (`ideDocumento`) se repete entre linhas diferentes; a
  chave de cada despesa é o conjunto dos campos, não o código.
- Há linhas de liderança de partido (`LID.GOV-CD`), sem deputado: entram no total
  conferido, mas não em parlamentar nenhum.

## O que mudou no plano

1. O buraco de 2024–2025 deixou de existir: são **quatro** sistemas na linha do
   tempo de Curitiba, não três.
2. O Elotech sai do navegador e vai para a API.
3. O custo de gabinete vem do Betha, conferido com o Elotech, como retrato da
   folha na data da coleta. Nenhuma das fontes publica a folha mês a mês por
   gabinete para anos passados, e somar remuneração de hoje sobre meses antigos
   seria inventar número. A série mensal cresce a cada coleta.

## Depois da Etapa 0: a paginação do portal da Prefeitura não é reproduzível

Achado na Fase 1 (26/11/2026), ao gravar o vídeo do robô: duas leituras da mesma
consulta (exercício, órgão Câmara, tipo Diárias) trouxeram conjuntos diferentes de
linhas. A ordem da tabela muda entre um postback e outro, e a paginação repete ou
pula linhas; numa das leituras, a primeira página ainda veio antes de o filtro do
órgão valer, com secretarias da Prefeitura.

O que o robô faz agora:
- confere que toda linha lida é do órgão filtrado (senão a página é refeita);
- consulta **mês a mês** (cada mês quase sempre cabe numa página) e lê duas vezes
  todo mês que ainda pagina, exigindo o mesmo resultado;
- lê também o **ano inteiro**, como segundo caminho, e compara os dois conjuntos.

O portal não publica total, então não há como desempatar quando os dois caminhos
discordam. Na rodada de 26/11, **2026 bateu** (40 = 40, mesmo conjunto) e **2024 e
2025 não bateram**: esses dois anos ficam inteiros na fila de revisão, com o motivo,
e a linha do tempo da plataforma diz isso.
