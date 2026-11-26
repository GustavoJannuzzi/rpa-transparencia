# rpa-transparencia

A Câmara Municipal de Curitiba trocou de sistema três vezes. O histórico das diárias
está em quatro lugares, de quatro fornecedores, e só um deles tem API: um portal
antigo que só gera PDF, o Elotech, o portal da Prefeitura e o Betha.

Este projeto junta tudo isso num modelo único, ao lado da cota dos deputados
federais, que vem pela API e pelos arquivos anuais da Câmara dos Deputados. Robô de
navegador (Python + Playwright) onde não há API; API e arquivo onde há. Cada número
passa por conferência contra o que a própria fonte diz de si, tem a procedência
anotada, e o que não fecha vai para uma fila de revisão em vez de ser chutado.

Uma plataforma estática (Next.js) mostra o resultado num grafo: deputados ligados
por fornecedor em comum e vereadores ligados aos seus partidos, com a ficha de
procedência de cada valor a um clique.

## O que cada fonte exigiu

| Fonte | Anos | Como | O que tinha de difícil |
|---|---|---|---|
| Portal legado da Câmara de Curitiba | 2013–2016 | robô + PDF | Aplicação React em que subpágina não abre direto: o robô navega pelo menu, clica no botão e captura o download. O PDF é uma planilha exportada: leitura pela grade da tabela, layout que muda de 11 para 15 colunas no meio da série, quatro formatos de período, valores compostos ("02 diárias + 02 refeições"). |
| Elotech | 2017–2023 | API | O próprio portal publica a API, então não há navegador. De 2017 a 2020 a diária vem sem nome, só com a matrícula (em 2018, às vezes dentro do campo cargo: "Vereador/1083"); o nome sai do quadro de pessoal do mesmo ano. |
| Portal da Prefeitura | 2024–2025 | robô | ASP.NET WebForms: cada filtro e cada página da tabela é um postback. A paginação não é reproduzível (a ordem muda entre postbacks), então o robô consulta mês a mês, lê duas vezes o mês que pagina, confere que toda linha é do órgão filtrado e compara com a consulta do ano inteiro. |
| Betha | 2026 | robô | Aplicação Vue. O robô lê a tabela da tela e confere cada linha com a resposta que a própria tela recebeu. Devolve 403 para User-Agent com "HeadlessChrome". |
| Câmara dos Deputados | 2023–2026 | API + arquivo | API para a lista de deputados e para conferência por amostra; arquivo anual para a carga. |
| TSE | eleições 2012–2024 | arquivo | Partido de cada vereador na eleição do mandato (nenhum sistema da Câmara traz partido). |

O levantamento que decidiu cada uma dessas escolhas, feito antes de escrever o
código, está em [`docs/etapa-0.md`](docs/etapa-0.md).

## O resultado da última rodada (coleta de 25 e 26/11/2026)

O [relatório de conferência](relatorio/conferencia.html) é gerado a cada rodada. Para
cada fonte, **origem = coletado + revisão**, e nenhum item com erro em aberto:

| Fonte | Linhas na origem | Coletadas | Em revisão |
|---|---:|---:|---:|
| Câmara dos Deputados (arquivos anuais, 57ª legislatura) | 790.635 | 659.576 | 131.059 |
| Legado de Curitiba (PDFs) | 193 | 180 | 13 |
| Elotech | 117 | 114 | 3 |
| Portal da Prefeitura | 121 | 40 | 81 |
| Betha | 54 | 54 | 0 |

"Coletadas" inclui as linhas que a própria fonte marca como canceladas ou devolvidas
(publicadas, mas fora da soma) e as de 2026 da Prefeitura, que servem para conferir
o Betha na fronteira entre os dois sistemas. As 81 da Prefeitura em revisão são 2024
e 2025 inteiros (ver o achado abaixo).

## O que a conferência achou

Achados reais, todos visíveis no relatório e na fila de revisão:

- **Um portal sem total e com paginação que muda.** No portal da Prefeitura, duas
  leituras da mesma consulta trouxeram conjuntos diferentes de linhas. O robô passou
  a ler cada ano por dois caminhos independentes (mês a mês e ano inteiro). Em 2026
  os dois deram o mesmo conjunto; em 2024 e 2025 não, e sem total publicado não há
  como desempatar: esses anos ficam inteiros em revisão, com o motivo, em vez de
  aparecer na plataforma com um número que pode estar incompleto.
- **O total do mês do PDF só fecha sem a linha devolvida.** Abril de 2016 soma R$ 340,00
  nas linhas e o PDF diz R$ 140,00; a diferença é uma diária marcada "Devolvido". A
  conferência tenta a soma com e sem as linhas marcadas e só aceita a que bate com a
  fonte.
- **Linhas em que quantidade × unitário não dá o total** (por exemplo, 1 diária de
  R$ 290 + 1 refeição de R$ 200 com total de R$ 390) vão para revisão, mesmo quando o
  total do mês confere.
- **O arquivo anual da Câmara arredonda alguns valores**: R$ 39.800,25 na API aparece
  como 39800.3 no CSV e no JSON anuais. Na amostra, o arquivo também traz menos
  passagens aéreas do SIGEPA que a API em 2024–2026. Essas categorias e anos ficam em
  revisão, fora dos totais.
- **A API devolve o valor líquido com o sinal trocado** em 3.060 das 4.925 linhas da
  amostra (`valorLiquido = −valorDocumento`); a conferência compara pelo valor do
  documento, e é por ele que se vê onde arquivo e API batem centavo a centavo.
- **Valor negativo com documento maior que zero** (complementação do auxílio-moradia) não
  tem explicação na fonte e vai para revisão; passagem com valor e documento negativos
  é compensação de bilhete e entra.
- **A matrícula do vereador muda de um mandato para outro**: a identidade é montada
  ligando matrículas, nomes civis e o nome de urna do TSE, não pela matrícula sozinha.
- **Um erro de digitação da fonte ("Veradora")** passa pela guarda de privacidade como
  servidora (o nome é descartado na leitura) e cai na revisão porque a tabela de-para
  sabe que é vereadora.

## Como rodar

Python 3.11+ e Node 22.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # no Linux/macOS: .venv/bin/python
.venv/Scripts/python -m playwright install chromium
```

```bash
.venv/Scripts/python -m coleta tudo
```

`tudo` roda, em sequência: `descobrir` (inventário de cada fonte e os totais que ela
mostra), `coletar` (percorre o inventário; rodar de novo só pega o que falta),
`conferir`, `publicar` (os JSON da plataforma, só com o que passou) e `relatorio`.
Cada comando também roda sozinho, e `--fonte` limita a uma fonte. `coletar
--gravar-video` grava o navegador em `dados/evidencias/videos/`.

A primeira rodada completa baixa ~430 MB de arquivos do TSE e da Câmara dos Deputados
para `dados/cache/` e leva alguns minutos; a coleta é educada (uma requisição por vez
em cada portal, com pausa, respeitando o robots.txt).

Plataforma:

```bash
cd plataforma
npm ci
npm run build
npm test
```

`npm run build` gera o site estático em `plataforma/out/`; `npm test` confere que todo
valor em reais nas páginas tem procedência.

## Testes

```bash
.venv/Scripts/python -m pytest
```

- **Parser:** PDFs, páginas e respostas reais, gravados pelo robô em 25/11/2026, em
  [`coleta/testes/amostras/`](coleta/testes/amostras/) (com nome de servidor tarjado).
- **Resiliência:** o Playwright serve o portal legado a partir das amostras, sem rede,
  e injeta erro 500, lentidão e queda de sessão; o resultado tem de ser igual ao da
  rodada limpa. O mesmo para a API do Elotech, com 503 e timeout.
- **Retomada:** a coleta é interrompida no meio, retomada, e não duplica nada.
- **Conferência:** casos montados (total que não fecha, categoria sem de-para, mesmo
  registro em dois sistemas na fronteira, cargo fora da guarda de privacidade).
- **Contrato:** um teste por fonte contra o portal de verdade, separado dos outros,
  avisa quando o layout mudou: `python -m pytest -m contrato`.

## Como está organizado

```
coleta/
  nucleo/      inventário, retomada, repetição com espera, evidência no erro,
               coleta educada, conferência (não sabe de fonte nenhuma)
  fontes/      uma pasta por fonte: camara_deputados, cmc_legado, cmc_elotech,
               cmc_prefeitura, cmc_betha, tse
  modelo.py    o modelo único (pydantic, dinheiro em Decimal exato)
  de_para/     cargos, categorias e regras de valor negativo: o que não tem linha
               aqui vai para revisão
  destinos/    JSON da plataforma, CSV, relatório HTML, layout do grafo
  testes/
plataforma/    Next.js estático: grafo (sigma.js), partido, parlamentar,
               "Como os dados chegam aqui", Sobre
docs/          o levantamento das fontes (etapa 0)
relatorio/     o relatório de conferência da última rodada
```

Fonte nova é uma pasta nova em `coleta/fontes/` e linhas novas em `coleta/de_para/`;
o núcleo não muda.

## Regras do projeto

- **Captcha nunca se contorna.** Portal com captcha ou login fica de fora (por isso a
  Assembleia Legislativa do Paraná e as câmaras do IPM Atende.net não estão aqui).
- O robots.txt de cada portal é respeitado; o User-Agent diz que é um robô.
- Assessor e servidor aparecem só em totais, sem nome. O nome é descartado já na
  leitura, antes de qualquer gravação; os originais com nome ficam só na máquina que
  coleta (`dados/`, fora do repositório).
- Fornecedor pessoa física aparece com o CPF mascarado e não entra no grafo.
- Nenhum número inventado ou arredondado; só vai para o ar o que passou na
  conferência.
- A plataforma é independente e não imita site oficial.

## Limites conhecidos

- Partido de vereador é o da eleição do mandato; troca de partido durante o mandato
  não está em nenhuma das fontes.
- O custo de gabinete é um retrato da data da coleta (Betha e Elotech conferidos um
  contra o outro). Nenhuma fonte publica a folha mês a mês por gabinete para anos
  passados; a série cresce a cada coleta.
- Os JSON publicados somam ~49 MB, quase tudo despesa federal linha a linha.
