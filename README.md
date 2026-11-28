# rpa-transparencia

[![CI](https://github.com/GustavoJannuzzi/rpa-transparencia/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/GustavoJannuzzi/rpa-transparencia/actions/workflows/ci.yml)
[![Contrato com os portais](https://github.com/GustavoJannuzzi/rpa-transparencia/actions/workflows/contrato.yml/badge.svg?branch=main)](https://github.com/GustavoJannuzzi/rpa-transparencia/actions/workflows/contrato.yml)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-blue.svg)](LICENSE)

**Site:** [rpa-transparencia.vercel.app](https://rpa-transparencia.vercel.app) ·
**Arquitetura, padrões e decisões:** [`docs/arquitetura.md`](docs/arquitetura.md) ·
**Relatório de conferência:** [/conferencia/](https://rpa-transparencia.vercel.app/conferencia/)

Cada casa legislativa publica os gastos num sistema diferente, e muitas casas usam o
mesmo fornecedor. Este projeto tem **um adaptador por sistema, configurado por
entidade**: o mesmo robô do Elotech serve 13 câmaras do Paraná, o do Betha serve
14, o do Equiplano serve 10, o do Pronim serve 6, e casa nova num fornecedor que já tem adaptador é um bloco em
[`coleta/entidades.toml`](coleta/entidades.toml), sem código.

Começou pela Câmara Municipal de Curitiba, que trocou de sistema três vezes: o
histórico das diárias está em quatro lugares, de quatro fornecedores (um portal
antigo que só gera PDF, o Elotech, o portal da Prefeitura e o Betha). Hoje junta,
num modelo único, a cota dos deputados federais, as verbas dos deputados de oito
assembleias (DF, MG, SP, AP, CE, GO, RN e PE) e as diárias de 42 câmaras municipais
do PR. Robô de navegador (Python + Playwright) onde não há API; API e arquivo onde há. Cada número passa por
conferência contra o que a própria fonte diz de si, tem a procedência anotada, e o
que não fecha vai para uma fila de revisão em vez de ser chutado.

Uma plataforma estática (Next.js) mostra o resultado num grafo: deputados federais
e estaduais ligados por fornecedor em comum (o CNPJ é a mesma chave nas duas
esferas) e vereadores ligados aos seus partidos, com a ficha de procedência de cada
valor a um clique. A página [Cobertura](https://rpa-transparencia.vercel.app/cobertura/)
mostra quais casas estão coletadas, em qual sistema, e por que as outras ainda não
estão.

![O robô passando pelo portal legado da Câmara, pelo portal da Prefeitura e pelo Betha](docs/robo.gif)

*O robô (Playwright) nos três sistemas que só se leem pelo navegador, gravado pela
própria coleta (`coletar --gravar-video`, 26/11/2026), em trechos escolhidos. As
tabelas que listam servidores aparecem borradas, e a página da Prefeitura está
recortada acima da grade: nome de servidor não é publicado, nem em imagem.*

## O que o projeto demonstra

- **RPA de navegador onde não há API.** Aplicação Vue que troca só o `#` (Betha),
  ASP.NET WebForms em que cada filtro é um postback (Prefeitura de Curitiba), ASP
  clássico com reCAPTCHA no caminho (Govbr Pronim), formulário em cascata com
  máscara por tecla e download do relatório (Equiplano), React que não abre
  subpágina direto (sistema legado de Curitiba), AngularJS, Angular Material,
  modais com iframe e PDFs.
- **A tela conferida contra ela mesma.** O robô lê a tabela que a pessoa vê e a
  compara com a resposta que a página recebeu (`expect_response`,
  `page.on("response")`), com o rodapé do relatório ou com a consulta do ano
  inteiro. Se não bate, para: o portal mudou.
- **Resiliência de coleta longa.** Inventário e retomada sem duplicar, repetição
  com espera exponencial, erros com tipo (transitório, portal mudou, robots.txt,
  captcha), evidência no ponto do erro (print, HTML, rastro do Playwright), troca
  de contexto do navegador e parada antes de o disco acabar.
- **Dado em que se pode confiar.** Modelo único em pydantic com dinheiro em
  `Decimal`, conferência **origem = coletado + revisão** em toda fonte, fila de
  revisão com o motivo em vez de número chutado, original guardado com hash e saída
  que se repete byte a byte.
- **Coleta educada e privacidade.** robots.txt e Crawl-delay respeitados, um pedido
  por vez em cada portal, captcha nunca contornado; CPF lido só na memória e
  mascarado antes de gravar (inclusive interceptando a resposta com `route.fetch`),
  nome de servidor descartado na leitura.
- **Engenharia em volta.** Adaptador por fornecedor e esqueleto de coleta único
  ([padrões e decisões](docs/arquitetura.md)), testes de unidade, contra portal
  falso e de contrato com o portal real, CI com ruff, mypy, pytest, axe, prints de
  referência e Lighthouse.

## Os robôs, por plataforma

| Plataforma | O que cobre | Como | Técnica |
|---|---|---|---|
| **Betha Cloud** (Vue) | Curitiba (2026) e outras câmaras do PR | Playwright | A consulta de diárias é achada pelo texto do item no menu (cada câmara monta o seu); cada linha da tabela da tela é conferida com a resposta JSON que a tela recebeu. User-Agent próprio: o portal devolve 403 para "HeadlessChrome". |
| **Equiplano** | câmaras do PR | Playwright + relatório | Cascata por AJAX com recarga da página, período digitado com máscara (`press_sequentially`), "Visualizar" devolve o relatório como anexo. A resposta é interceptada (`route.fetch`) para tirar CPF e RG antes de o navegador recebê-la. A soma dos empenhos fecha, centavo a centavo, com o rodapé do relatório. |
| **Govbr Pronim** (ASP clássico) | câmaras do PR | Playwright | Formulário único com AJAX; o robô para se o reCAPTCHA aparecer. A tela mostra CPF inteiro: o documento é lido só na memória e a página é mascarada antes de qualquer gravação. A soma dos meses é conferida contra a consulta do ano. |
| **Portal da Prefeitura de Curitiba** (ASP.NET WebForms) | Curitiba, 2024–2025 | Playwright | Cada filtro e cada página é um postback, e a paginação não se repete: o robô lê mês a mês, lê duas vezes o mês que pagina e compara com a consulta do ano inteiro. |
| **Sistema legado da Câmara de Curitiba** (React + PDF) | Curitiba, 2013–2016 | Playwright + PDF | Subpágina não abre direto: o robô navega pelo menu, clica e captura o download (`wait_for_event("download")`), correndo contra o alerta de sessão vencida. O PDF é lido pela grade da tabela (pdfplumber), com layout de 11 e de 15 colunas. |
| **Frequência da Câmara de Curitiba** (Betha + PDF) | Curitiba, 2019–2026 | Playwright + PDF | O PDF só aparece depois de "Ver arquivos", num link S3 que vence em 24 horas: o robô abre, clica, lê a lista que a tela recebe e baixa na hora. Quatro layouts de tabela em oito anos. |
| **Assembleias pela tela** | AP, CE, GO e RN; TO, BA e PE em coleta, entram no próximo envio | Playwright | AP: três selects em cascata por AJAX e um iframe por elemento de despesa. CE: lista paginada e modal com iframe, conferida contra o CSV do mês. GO (AngularJS) e RN (Angular Material): o robô lê a resposta que a tela recebe (a API do RN responde 401 fora do app). |
| **Elotech** | Curitiba (2017–2023) e outras câmaras do PR | API (httpx) | A entidade da Câmara é conferida pelo CNPJ antes de coletar; a diária que vem só com a matrícula ganha o nome pelo quadro de pessoal do mesmo ano. |
| **SAPL (Interlegis)** | atividade nas sessões de câmaras do PR | API (httpx) | Crawl-delay de 60 s: inventário de páginas com o filtro congelado na descoberta, câmaras em paralelo, respostas gravadas que reproduzem a coleta sem pedido nenhum. |
| **Câmara dos Deputados** | 57ª legislatura | API + arquivo anual | Arquivo anual para a carga, API para a lista de deputados e para conferir por amostra (o arquivo arredonda alguns valores; a API troca o sinal do valor líquido). |
| **Assembleia de Minas Gerais** | 2023–2026 | API | Uma chamada por deputado e mês; a soma das notas fecha com o total de cada tipo que a própria API dá. |
| **Câmara Legislativa do DF** (CKAN) | 2023–2026 | arquivo | CSV e XLSX lidos sem biblioteca; data só quando é inequívoca; CNPJ gravado como número recomposto só quando os dígitos verificadores fecham. |
| **Assembleia de São Paulo** | 2023–2026 | arquivo (JSON de 160 MB) | Baixa só quando muda (HEAD), guarda comprimido e lê em fluxo, com `Decimal`. Cada linha da fonte já é um agregado, e o site diz isso. |
| **TSE** | eleições de 2012 a 2024 | arquivo | O partido de cada vereador na eleição do mandato (nenhum sistema das câmaras traz partido). |

Quantas casas cada adaptador atende, e por que as outras ficaram de fora, está na
[Cobertura](https://rpa-transparencia.vercel.app/cobertura/); o que cada fonte tinha de difícil,
logo abaixo; como as peças se encaixam, em [`docs/arquitetura.md`](docs/arquitetura.md).

## O que cada fonte exigiu

| Fonte | Anos | Como | O que tinha de difícil |
|---|---|---|---|
| Portal legado da Câmara de Curitiba | 2013–2016 | robô + PDF | Aplicação React em que subpágina não abre direto: o robô navega pelo menu, clica no botão e captura o download. O PDF é uma planilha exportada: leitura pela grade da tabela, layout que muda de 11 para 15 colunas no meio da série, quatro formatos de período, valores compostos ("02 diárias + 02 refeições"). |
| Elotech | 2017–2023 | API | O próprio portal publica a API, então não há navegador. De 2017 a 2020 a diária vem sem nome, só com a matrícula (em 2018, às vezes dentro do campo cargo: "Vereador/1083"); o nome sai do quadro de pessoal do mesmo ano. |
| Portal da Prefeitura | 2024–2025 | robô | ASP.NET WebForms: cada filtro e cada página da tabela é um postback. A paginação não é reproduzível (a ordem muda entre postbacks), então o robô consulta mês a mês, lê duas vezes o mês que pagina, confere que toda linha é do órgão filtrado e compara com a consulta do ano inteiro. |
| Betha | 2026 | robô | Aplicação Vue. O robô lê a tabela da tela e confere cada linha com a resposta que a própria tela recebeu. Devolve 403 para User-Agent com "HeadlessChrome". |
| Câmara dos Deputados | 2023–2026 | API + arquivo | API para a lista de deputados e para conferência por amostra; arquivo anual para a carga. |
| Elotech em mais 12 câmaras do PR | 2023–2026 | API, o mesmo adaptador de Curitiba | A instalação atende Prefeitura, Câmara e autarquias; o robô confere a entidade da Câmara pelo CNPJ antes de coletar. Diária sem cargo (quase metade em algumas câmaras): o nome só fica se estiver, igual, no cadastro de vereadores do mesmo ano; senão é descartado na leitura e a linha vai para revisão. Exercício que a lista mostra e a contabilidade não tem (Renascença, 2023); instalação própria em que a API omite o campo do cargo (Umuarama). |
| Câmara Legislativa do DF | 2023–2026 | arquivo (CKAN) | 2024 e 2025 completos só em planilha XLSX, lida sem biblioteca. Cabeçalho, data e valor mudam a cada ano; a planilha de 2025 mistura dia/mês e mês/dia (a data só é lida quando é inequívoca) e tem linhas com as colunas deslocadas; o CNPJ gravado como número perde os zeros à esquerda (recompostos só quando os dígitos verificadores fecham). O CPF do deputado liga as grafias do nome na memória e não é gravado. |
| Assembleia de Minas Gerais | 2023–2026 | API | Uma chamada por deputado e mês, só nos meses que a API diz ter prestação fechada. A soma das notas de cada tipo é conferida contra o total que a própria API dá para o tipo no mês. |
| Assembleia de São Paulo | 2023–2026 | arquivo (JSON de 160 MB) | O arquivo traz 2002–2026 de uma vez: baixa só quando a data dele muda, guarda comprimido (20 MB) e lê em fluxo. A fonte publica a despesa já somada por fornecedor × tipo × mês: cada linha é um agregado, e a plataforma diz isso. |
| Assembleia do Amapá | 2023–2026 | robô | PHP com três selects em cascata por AJAX (ano, mês, gabinete), POST e um modal com iframe para cada elemento de despesa. O AJAX dos gabinetes manda UTF-8 codificado duas vezes. A conferência tem três degraus, todos na tela: as notas somam o elemento, os elementos somam o TOTAL do mês, e o TOTAL é o do histórico do ano, com o mês complementar. |
| Assembleia do Ceará | 2023–2026 | robô | Lista paginada e um modal com iframe, cuja chave é o base64 de "ano_mês_NOME", com o nome exato como a casa digita. O robô lê a tela e confere cada empenho contra o CSV do mês que a própria casa publica. O nome do deputado vem com erro de digitação, sufixo colado e espaço duplo: grafia só é ligada com prova na fonte (a anulação "para correção do nome do deputado", o mesmo nome civil no reembolso); o resto vai para a revisão. A coluna "CNPJ" do reembolso ao deputado traz o CPF dele, mascarado na leitura. |
| Assembleia de Goiás | 2025–2026 (pelo peso no site e porque o portal recusa conexão em rajadas) | robô | App AngularJS. O dado aberto da casa só tem o total do mês por deputado; o fornecedor e o CNPJ só existem na tela. O robô abre a rota da tela de cada deputado no mês e lê a resposta que a própria tela recebe. A conferência tem três níveis: os lançamentos somam o grupo, os grupos somam o total da tela, e o total da tela é o do dado aberto. O valor publicado é o indenizado (o apresentado e a glosa ficam ao lado). |
| Assembleia do Rio Grande do Norte | 2023–2026 | robô | App Angular Material: os filtros são `mat-select`, que abrem um painel fora do componente. A API responde 401 a quem não é o app, então a tela é a única entrada: o robô pesquisa como uma pessoa e lê a resposta que a tela recebe. A contagem e a soma da resposta batem com as linhas, a soma é a da frase da tela ("os parlamentares utilizaram um total de R$ …"), o paginador diz quantas linhas há, e a tabela, lida página a página, mostra as mesmas linhas. |
| Assembleia de Pernambuco | 2023–2026 | robô | App React em quatro níveis, cada um pedido pela própria tela: o deputado e o ano trazem os meses com prestação, o mês traz os pedidos, e cada pedido traz as notas. O select é controlado pelo React (trocar o valor por script não dispara a busca), então o robô escolhe como uma pessoa e lê as respostas que a tela recebe. O valor vem como texto, inteiro ("21880") ou com vírgula decimal ("8372,5"). As notas de cada pedido somam o total do pedido. Resposta sem corpo é falha de rede, e o robô tenta de novo; não vira "pedido sem nota". |
| Betha em mais 13 câmaras do PR | 2014–2026 (o que cada câmara publica) | robô, o mesmo adaptador de Curitiba | Cada câmara monta o próprio menu, e a mesma consulta aparece com outro número, em outro grupo e com outro texto ("Diárias", "Diárias.", "DIÁRIAS"). O robô acha a consulta pelo texto do item na tela e tira o número do menu que a página recebe; quando dois itens têm o mesmo texto (Bandeirantes), fica o que tem as colunas de diária. "0 registros" é resultado: a câmara tem a consulta e não a alimenta (Almirante Tamandaré). A consulta de Cornélio Procópio traz cargos da Prefeitura: as diárias de servidor dela vão para revisão. |
| Equiplano em 10 câmaras do PR | 2023–2026 | robô de tela + relatório | O formulário é uma cascata: a entidade dispara um AJAX que carrega os exercícios, o exercício recarrega a página, o período é obrigatório (sem ele, "Período de Empenho inválido" depois de recarregar) e tem máscara por tecla, e "Visualizar" devolve o arquivo como anexo. O "CSV" é o relatório impresso: cabeçalho de página repetido, rótulos e datas cortados pela largura do papel, descrição em várias linhas. A conta fecha com o próprio papel: a soma dos empenhos líquidos de cada ano dá, centavo a centavo, o total que o relatório imprime. Quem é vereador sai da natureza da despesa (agentes políticos). Em algumas câmaras o relatório traz **CPF e RG inteiros**: o robô intercepta a resposta e tira os dois na memória, antes de gravar o original. |
| Govbr Pronim em 6 câmaras do PR | 2023–2026 | robô, ASP clássico | Um formulário único com os campos de todas as consultas; o ano tem valor de chave interna, a entidade e os desdobramentos chegam por AJAX, o período vem com o mês corrente e "Gerar" passa por uma função de reCAPTCHA que, neste domínio, só envia o formulário (o robô para se o reCAPTCHA aparecer). **A tabela mostra o CPF sem máscara**: o robô lê o documento só na memória, para ligar a mesma pessoa entre as consultas, e mascara a página antes de gravar qualquer coisa, inclusive o original. A tela soma por credor no período: cada linha é um agregado (credor × mês), e a soma dos meses de cada credor é conferida contra a consulta do ano inteiro. Vereador = credor no desdobramento "agentes políticos"; a unidade gestora é a da Câmara, porque a "consolidada" de Salto do Lontra inclui a Prefeitura. |
| TSE | eleições 2012–2024 | arquivo | Partido de cada vereador na eleição do mandato, nos 42 municípios (nenhum sistema das câmaras traz partido). |
| SAPL (Interlegis), atividade nas sessões | 2025–2026 | API, o mesmo adaptador em 6 câmaras do PR | O robots.txt pede 60 s entre pedidos, e a API devolve no máximo 100 registros por página: cada câmara tem uma janela, o inventário é uma lista de páginas com o filtro congelado na descoberta (data de corte e maior id), e a retomada só pede o que falta. Câmaras em servidores diferentes andam juntas (`--paralelo`), uma página por minuto em cada uma. O voto nominal não diz a sessão: o robô a acha pelo nome que o texto do próprio voto traz. A coleta longa roda num banco de trabalho e entra no banco principal pelo `importar`; as respostas ficam gravadas e podem ser reproduzidas sem pedido nenhum. |
| Câmara de Curitiba, frequência (Betha) | 2019–2026 | robô + PDF | O PDF não tem link fixo: só aparece depois de "Ver arquivos", num link S3 que vence em 24 horas. O robô abre a consulta, clica, lê a lista que a própria tela recebe e baixa na hora. Quatro layouts de tabela em oito anos, nota colada ao nome ("Leprevost(B)", "13 [F]", "1[4]"), nome quebrado em duas linhas e o consolidado anual que repete os meses (não é somado). |

O levantamento que decidiu cada uma dessas escolhas, feito antes de escrever o
código, está em [`docs/etapa-0.md`](docs/etapa-0.md).

### O que ficou de fora, e por quê

O levantamento de 26/11/2026 procurou o fornecedor do portal das 399 câmaras do PR
e as despesas das 27 assembleias. O que ficou de fora:

| Casa ou fornecedor | Por quê |
|---|---|
| Assembleia do Paraná | A consulta da verba pede captcha, e o robots.txt proíbe a API. Captcha nunca se contorna. |
| IPM Atende.net (28 câmaras, entre elas Cascavel, Colombo e Guarapuava) | O robots.txt proíbe a consulta, e ela passa por um desafio da Cloudflare. |
| Inga Digital (32 câmaras) | O robots.txt proíbe o portal inteiro. |
| 39 câmaras, entre elas Londrina | O robots.txt do site proíbe qualquer robô. |
| As outras câmaras Govbr Pronim (o levantamento contou 14) | O adaptador já serve: falta pôr a câmara na configuração. |
| As outras câmaras Equiplano (o levantamento contou 36) | O adaptador já serve: falta pôr a câmara na configuração. As que migraram para a geração nova (`equiplano.cloud`) pedem outro adaptador. |
| União da Vitória, Goioerê, Jaguariaíva e Mandirituba (Betha) | O portal não tem a consulta de diárias com o cargo de quem recebeu: só a de empenhos de viagem, que mistura passagem e diária e não diz o cargo. |
| As outras câmaras Betha (o levantamento contou 59) | O adaptador já serve: falta pôr a câmara na configuração. |
| As outras câmaras Elotech (o levantamento contou 108) | O adaptador já serve: falta pôr a câmara na configuração. |
| Assembleias do TO e da BA | O robô está pronto e a coleta está em andamento: entram no próximo envio, depois de conferidas (AP, CE, GO, RN e PE já entraram). |
| Assembleias de MS, AM, RO, PB, AL, RS e SC | Na reserva: fonte aberta, ainda sem adaptador (em PB o CNPJ vem mascarado; em AL é PDF escaneado). |
| Assembleias do ES, PA, RR, SE e AC | Só totais, sem dizer quem recebeu, ou nada por deputado. A do RJ não tem verba indenizatória. |
| Assembleia do PI | Proteção contra robô no portal. MT estava fora do ar, e a do MA voltou vazia (não verificadas). |
| 135 câmaras | O levantamento não identificou o fornecedor do portal. |

A página [Cobertura](https://rpa-transparencia.vercel.app/cobertura/) traz essa
tabela casa por casa, com o mapa do PR por município e o do Brasil por UF.

## Atividade nas sessões

Além da despesa, a plataforma mostra o que a câmara registra das sessões plenárias:
sessão com presença registrada, ausência com o motivo que a fonte der e
voto nominal por tipo ("Sim", "Não", "Abstenção", como a fonte escreve). É outro tipo
de dado (`Atividade` no modelo, tabela `atividades`), e não entra em soma nenhuma em
reais. Só contagem bruta, com a ficha de procedência de cada número; nada de taxa,
ranking ou ordem por quem falta mais.

- **SAPL** (Interlegis): Foz do Iguaçu, Sarandi, Irati, Campina Grande do Sul e
  Renascença desde 01/01/2025 (a legislatura atual) e Maringá em 2026. Maringá vota
  quase tudo no painel eletrônico: só os votos nominais de 2025 e 2026 pediriam 837
  páginas, perto de 14 horas a um pedido por minuto, e a janela ficou em 2026.
- **Curitiba**: os 64 relatórios de frequência do portal Betha, de 2019 a 2026. A
  Câmara publica "presença + faltas justificadas" numa coluna só, "faltas
  (descontadas)" e "licença"; a plataforma mostra as colunas como a Câmara as escreve.
- A atividade não cria vereador: o nome que cada fonte traz se liga a um vereador que
  as fontes de despesa (e o TSE) já identificaram na mesma câmara. Nome que não fecha
  com ninguém, ou fecha com dois, vai para a revisão e não é publicado.
- O que a coleta ainda não fechou aparece como parcial, com a data até onde vale.

A página Cobertura diz quais câmaras têm a atividade, a janela de cada uma e por que
as outras ficaram de fora (SAPL sem sessão registrada, SAPL não encontrado).

## O resultado da última rodada (coleta de 25 a 27/11/2026)

O [relatório de conferência](relatorio/conferencia.html) é gerado a cada rodada. Para
cada fonte, **origem = coletado + revisão**, e nenhum item com erro em aberto:

| Fonte | Linhas na origem | Coletadas | Em revisão |
|---|---:|---:|---:|
| Câmara dos Deputados (arquivos anuais, 57ª legislatura) | 790.635 | 659.576 | 131.059 |
| Legado de Curitiba (PDFs) | 193 | 180 | 13 |
| Elotech (Curitiba) | 117 | 114 | 3 |
| Portal da Prefeitura | 121 | 40 | 81 |
| Betha | 54 | 54 | 0 |
| Elotech, 12 câmaras do PR | 2.671 | 2.374 | 297 |
| Betha, 13 câmaras do PR | 2.729 | 1.785 | 944 |
| Equiplano, 10 câmaras do PR | 3.096 | 3.090 | 6 |
| Govbr Pronim, 6 câmaras do PR (linhas credor × mês) | 1.223 | 1.122 | 101 |
| Câmara Legislativa do DF | 3.183 | 2.614 | 569 |
| Assembleia de Minas Gerais (notas) | 94.209 | 94.209 | 0 |
| Assembleia de São Paulo (linhas agregadas) | 82.182 | 82.182 | 0 |
| Assembleia do Amapá (notas, pela tela) | 7.094 | 7.094 | 0 |
| Assembleia do Ceará (empenhos, pela tela) | 17.316 | 17.246 | 70 |
| Assembleia de Goiás (lançamentos, pela tela, 2025–2026) | 26.234 | 26.204 | 30 |
| Assembleia do Rio Grande do Norte (notas, pela tela) | 16.501 | 16.501 | 0 |
| Assembleia de Pernambuco (notas, pela tela) | 9.876 | 9.874 | 0 (2 de valor zero na fonte, fora da soma) |

São 51 casas, com 1.865 parlamentares na plataforma. Nas câmaras do Elotech, a
maior parte do que está em revisão é diária sem cargo cujo nome não está no cadastro
de vereadores do ano: pode ser de servidor, então o nome é descartado e a linha fica
de fora, contada. No Betha, 877 das 944 linhas em revisão são de Cornélio Procópio,
cuja consulta da Câmara traz diárias de cargos da Prefeitura (achado abaixo).

"Coletadas" inclui as linhas que a própria fonte marca como canceladas ou devolvidas
(publicadas, mas fora da soma) e as de 2026 da Prefeitura, que servem para conferir
o Betha na fronteira entre os dois sistemas. As 81 da Prefeitura em revisão são 2024
e 2025 inteiros (ver o achado abaixo).

## O que a conferência achou

Achados reais, todos visíveis no relatório e na fila de revisão:

- **A "consolidada" que é o município inteiro.** No Pronim de Salto do Lontra, a
  unidade gestora padrão ("CONSOLIDADA") junta Câmara, Prefeitura e Fundo de Saúde, e
  a tabela da tela para perto de 100 credores. Foi a conferência do ano inteiro contra
  a soma dos meses que acusou: 99 credores num caminho, 197 no outro. O robô passou a
  escolher a unidade da Câmara (12 a 13 credores por ano) e para quando a tabela chega
  perto do corte, em vez de publicar uma lista cortada.
- **O relatório que fecha consigo mesmo.** No Equiplano não há API nem contador: o
  "CSV" é o relatório impresso. Nas 10 câmaras, em todos os 40 anos coletados, a
  soma dos empenhos lidos (empenhado menos o estorno de empenho) dá, centavo a
  centavo, o total que o próprio relatório imprime no rodapé.
- **CPF e RG inteiros no relatório de uma câmara.** O relatório de diárias de Santo
  Antônio do Sudoeste traz o CPF e o RG de quem viajou sem máscara. O robô intercepta
  a resposta do "Visualizar" e tira os dois na memória, antes de gravar o original.
- **A consulta da Câmara com diárias da Prefeitura.** No Betha de Cornélio Procópio,
  a consulta "Diárias." da Câmara traz cargos como "Chefe de Gabinete do Prefeito",
  "Secretário Mun. Agric., Pec. e Meio Ambiente" e "Chefe de Divisão de Galerias de
  Águas Pluviais", de 2014 a 2026, e o filtro de entidade da própria consulta diz
  que tudo é da Câmara. Sem como separar as duas entidades, as diárias de servidor
  dessa consulta ficam em revisão; as de vereador seguem publicadas.
- **Dois itens de menu com o mesmo texto.** O Betha de Bandeirantes tem "Diárias" e
  "DIÁRIAS" no mesmo grupo do menu, com consultas diferentes. O robô abre as duas e
  fica com a que tem as colunas de diária por pessoa; a outra é registrada como
  descartada, com as colunas que tinha.
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
  sabe que é vereadora. Nas câmaras novas, sem tabela revisada à mão, cargo que se
  parece com o de vereador sem ser ("Veriador", "Presidente Legislativo") também vai
  para revisão, em vez de virar servidor.
- **A CLDF publica dois arquivos para o mesmo ano, e eles não batem.** Em 2023, 90 das
  1.474 notas da planilha XLSX não estão no CSV do mesmo ano, e as notas do CSV que
  faltam na planilha ficam em revisão. O arquivo "2024 (até maio)" deveria estar contido no de 2024 inteiro, e 5
  das 92 notas dele não estão.
- **Na planilha de 2025 da CLDF**, a mesma coluna traz "1/16/2025" (mês primeiro) e
  "21/03/2025" (dia primeiro). A data que pode ser lida dos dois jeitos não é chutada.
- **A soma das notas da ALMG fecha** com o total que a própria API dá para cada tipo de
  despesa, em todos os meses coletados.
- **No Amapá, a tela fecha em três degraus**: as notas de cada elemento de despesa
  somam o elemento, os elementos somam o TOTAL do mês, e o TOTAL é o do histórico do
  ano, com o mês complementar ("Setembro/2025 (compl.)") somado. Fecha em todos os
  meses de 2023 a 2026.
- **No Ceará, o nome do deputado é digitado à mão a cada mês**, e a chave do detalhe é
  esse nome em base64: há erro de digitação ("GUILHREME SAMPAIO"), categoria colada
  ao nome ("ALMIR BIE - COMBUSTIVEIS E LUBRIFICANTES AUTOMOTIVOS"), espaço duplo e um
  "deputado" chamado "PLANO DE SAUDE". O sufixo sai na conferência; a grafia errada só
  é ligada ao deputado com prova na própria fonte (12 casos, quase todos com a
  anulação "para correção do nome do deputado"); o resto vai para a revisão. O
  contador "de N resultados" da tela conta um a mais do que a lista mostra, em todos
  os meses. O CSV do mês confere a tela empenho a empenho: só dois meses não fecham.
- **Em Goiás, a tela e o dado aberto da casa concordam em quase tudo**: 852 dos 853
  meses de deputado fecham nos três níveis. No que não fecha (Julio Pina, 03/2025), as
  notas somam o total da tela, mas o dado aberto diz 40.881,27 indenizados para
  40.486,82 apresentados; as 30 notas desse mês ficam em revisão.
- **No Rio Grande do Norte, a resposta que a tela recebe e a tabela que ela mostra são
  as mesmas linhas**, nos quatro anos: 16.501 notas, nenhuma em revisão.
- **Em Pernambuco, as notas de cada pedido somam o total do pedido** nos 3.110 pedidos
  de 2023 a 2026. A casa manda o valor como texto, sem centavos quando o valor é
  inteiro ("21880") e com vírgula quando não é ("8372,5" é 8.372,50).

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
Cada comando também roda sozinho, e `--fonte` limita a uma fonte ou a um fornecedor
inteiro (`--fonte elotech`, `--fonte assembleia`, `--fonte sapl`). `coletar --gravar-video` grava o
navegador em `dados/evidencias/videos/`. `--paralelo N` roda N fontes ao mesmo tempo,
cada uma no seu portal (dentro de um portal continua um pedido por vez).

A coleta do SAPL é longa (um pedido por minuto em cada câmara) e roda num banco de
trabalho, com as câmaras em paralelo; o `importar` (abaixo) leva ao canônico as que
fecharam:

```bash
RPA_DADOS=dados-trabalho .venv/Scripts/python -m coleta descobrir --fonte sapl --paralelo 6
RPA_DADOS=dados-trabalho .venv/Scripts/python -m coleta coletar --fonte sapl --paralelo 6
```

O SAPL guarda cada resposta comprimida em `cache/sapl/`. Com
`RPA_SAPL_REPRODUZIR=<pasta>/cache/sapl`, a coleta de uma câmara é refeita a partir
dessas respostas, sem pedido nenhum, com o mesmo hash e a mesma data de coleta.

Coleta longa (horas no navegador) roda num banco de trabalho, sem segurar o
canônico: `RPA_DADOS=<pasta de trabalho>` no `descobrir` e no `coletar`. Quando ela
fecha, `importar` leva as linhas dessas fontes para o banco de `RPA_DADOS`, numa
transação só, e move os originais e as evidências delas para lá:

```bash
.venv/Scripts/python -m coleta importar --de <pasta de trabalho>/estado.db --fontes alap,alece --sessao <nome>
```

Ele pega a trava `EM-USO.txt` do destino (e para se ela for de outra sessão), recusa
coleta com item pendente ou com erro na origem, e pode rodar de novo sem duplicar
nada: as linhas dessas fontes no destino são trocadas pelas da origem, e as das
outras fontes ficam como estavam. A trava fica até quem importou apagá-la. As
candidaturas do TSE não têm coluna de fonte e vêm inteiras: o `importar` recusa se a
origem não tiver algum município e eleição que o destino tem (`--aceitar-perda-tse`
passa por cima).

Numa coleta longa, a coleta para antes do próximo item quando o disco fica com menos
de 400 MB livres (`RPA_DISCO_MINIMO_MB`), e o item fica pendente para a retomada. Nas
fontes com navegador, o contexto é trocado a cada 20 itens (`RPA_ITENS_POR_CONTEXTO`,
ou `itens_por_contexto` na fonte de item longo), o que libera o que o navegador
acumula no Temp, e o rastro de cada item leva os prints, sem os snapshots. O rastro fica no Temp até o navegador fechar; a fonte de
item longo desliga o rastro (`rastrear = False`), e a evidência do erro fica com
o print e o HTML da página.

A primeira rodada completa baixa ~430 MB de arquivos do TSE e da Câmara dos Deputados
e o arquivo da ALESP (160 MB, guardado comprimido) para `dados/cache/`. A coleta é
educada: uma requisição por vez em cada portal, com a pausa que o robots.txt de cada
domínio pede (Crawl-delay, 10 s nos dados abertos da CLDF e da ALESP) e um piso
próprio. A da ALMG faz uma chamada por deputado e mês e leva perto de uma hora.

Plataforma:

```bash
cd plataforma
npm ci
npm run build
npm test
```

`npm run build` gera o site estático em `plataforma/out/`; `npm test` confere que todo
valor em reais nas páginas tem procedência.

## Como pôr uma casa nova

**Num fornecedor que já tem adaptador** (Elotech, Betha, Equiplano, Govbr Pronim,
SAPL), é um bloco em [`coleta/entidades.toml`](coleta/entidades.toml), sem código.
O que cada um pede:

| Fornecedor | Campos próprios | De onde sai |
|---|---|---|
| Elotech | `host`, `entidade`, `cnpj` | `entidade` é o número da Câmara em `/portaltransparencia-api/api/entidades`; o `descobrir` confere o CNPJ e para se não bater |
| Betha | `portal`, `de` | o código na URL `transparencia.betha.cloud/#/<portal>`; o `descobrir` confere o IBGE que o portal informa, e a consulta é achada pelo texto do menu |
| Equiplano | `host` (com a porta), `entidade` | a porta, no link do site da câmara ou da prefeitura; a entidade, no `<select id="formulario.codEntidade">` |
| Govbr Pronim | `base` | `https://webapp1-<cidade>.cidade360.cloud/pronimtb_cm` |
| SAPL | `host`, `de`, `lote_presenca` | `https://sapl.<cidade>.pr.leg.br`; `de` é o início da janela |

Todo bloco leva ainda `fonte` (o id, só `[a-z_]`), `casa`, `municipio`, `ibge` e
`regiao`. Um exemplo, do Equiplano:

```toml
[[equiplano]]
fonte = "equiplano_santo_antonio_do_sudoeste"
casa = "cm-santo-antonio-do-sudoeste"
municipio = "Santo Antônio do Sudoeste"
ibge = 4124400
regiao = "Sudoeste"
host = "https://santoantoniodosudoestepr.equiplano.com.br:7058"
entidade = 111
```

Depois, essa fonte e o TSE (o inventário do TSE lista os municípios, e é dele que vem
o partido de cada vereador; numa câmara nova, a lista muda e ele coleta de novo):

```bash
.venv/Scripts/python -m coleta descobrir --fonte equiplano_santo_antonio_do_sudoeste --fonte tse
.venv/Scripts/python -m coleta coletar --fonte equiplano_santo_antonio_do_sudoeste --fonte tse
.venv/Scripts/python -m coleta conferir
.venv/Scripts/python -m coleta publicar
```

A casa entra sozinha na página Cobertura, no grafo e na busca. Uma câmara que está
no fornecedor mas não dá para coletar fica no arquivo com `fora` e `detalhe`, e o
motivo vai para a Cobertura.

**Um fornecedor novo** é uma pasta em `coleta/fontes/<fornecedor>/` com uma classe que
herda de `Fonte` (API ou arquivo) ou de `FonteNavegador` (Playwright) e implementa
`descobrir()` e `coletar_item()`; uma linha em `_construir()`, em
[`coleta/fontes/__init__.py`](coleta/fontes/__init__.py); as categorias da fonte em
[`coleta/de_para/categorias.csv`](coleta/de_para/categorias.csv) (o que não tiver
de-para vai para revisão); e os testes: a leitura de uma amostra gravada e um teste
de contrato com o portal real. O núcleo não muda. O contrato que a classe cumpre e os
ganchos que ela pode usar estão em [`docs/arquitetura.md`](docs/arquitetura.md).

## Testes

```bash
.venv/Scripts/python -m pytest                      # unidade e portal falso, sem rede
.venv/Scripts/python -m pytest -m contrato          # contra os portais de verdade
```

Os testes ficam em [`coleta/testes/`](coleta/testes/), uma pasta por tipo:

- **[`unidade/`](coleta/testes/unidade/)**: a leitura de cada formato a partir de
  amostras reais gravadas pelo robô (PDF, página, planilha, resposta de API), em
  [`amostras/`](coleta/testes/amostras/), com nome de servidor tarjado e CPF trocado
  por número que não fecha o dígito verificador; as regras da conferência em casos
  montados (total que não fecha, categoria sem de-para, o mesmo registro em dois
  sistemas na fronteira); o `importar`; e o determinismo (a derivação inteira em dois
  processos com sementes de hash diferentes, comparada byte a byte).
- **[`portal_falso/`](coleta/testes/portal_falso/)**: o robô inteiro, sem rede,
  contra uma API falsa (`httpx.MockTransport`), um portal gravado servido pelo
  Playwright ou um portal falso local (Equiplano e Pronim). Erro 500, 503, timeout,
  lentidão e queda de sessão injetados dão o mesmo resultado da rodada limpa; a
  coleta interrompida no meio retoma sem duplicar; o CPF da tela não chega ao disco.
- **[`contrato/`](coleta/testes/contrato/)**: um teste por fonte contra o portal de
  verdade. Avisa quando o layout mudou. Fica fora do `pytest` padrão.
- [`apoio/`](coleta/testes/apoio/): os portais falsos, a gravação do portal legado e
  os scripts que geram as amostras.

## Integração contínua

Cada push roda, no GitHub Actions, o ruff, o mypy e o pytest; o build da plataforma,
o `tsc` e o teste de procedência (todo valor em reais na página tem fonte e data de
coleta); o axe-core em 23 telas do site exportado, no desktop e no celular; a
comparação com os prints de referência; e o Lighthouse CI com orçamento. Toda
segunda-feira, o **contrato** roda contra os portais reais: se um deles mudar, o
workflow abre uma issue sozinho. O que cada job confere e como atualizar os prints
está em [`docs/ci.md`](docs/ci.md).

```bash
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m mypy
```

```bash
cd plataforma
npm run build
npx playwright install chromium
npx playwright test            # axe; os prints só rodam no Linux do CI
npx lhci autorun               # relatório em testes/lighthouse/
```

## Como está organizado

```
coleta/
  entidades.toml   quem coletar: para cada fornecedor, as casas que o adaptador atende
  entidades.py     lê o entidades.toml em dataclasses imutáveis
  modelo.py        o modelo único (pydantic, dinheiro em Decimal): despesa, pendência,
                   atividade, pessoa como a fonte a vê, total que a fonte diz de si
  fontes/          um adaptador por sistema; base.py tem o contrato (Fonte,
                   FonteNavegador) e __init__.py, o registro
  nucleo/
    execucao.py    o esqueleto de toda coleta: retomada, repetição, evidência
    repositorio.py o que a coleta grava no SQLite
    banco.py       esquema, conexão e transação
    educacao.py    robots.txt, Crawl-delay e um pedido por vez em cada portal
    evidencia.py   original com hash e evidência no ponto do erro
    conferencia.py identidade, regras de cada fonte e fila de revisão
    importar.py    coleta longa de um banco de trabalho para o canônico
  destinos/        JSON da plataforma, cobertura, layout do grafo, relatório HTML
  de_para/         cargos, categorias e regras de valor negativo
  cobertura/       o levantamento das casas de fora e a malha do IBGE (mapas)
  testes/          unidade/, portal_falso/, contrato/, apoio/, amostras/
plataforma/        Next.js estático: grafo (sigma.js), partido, parlamentar, casa,
                   Cobertura, "Como os dados chegam aqui", Sobre
docs/              arquitetura (padrões e decisões), o levantamento (etapa 0), o CI
relatorio/         o relatório de conferência da última rodada (também no site, em /conferencia/)
DESIGN.md          o sistema visual da plataforma; PRODUCT.md, para quem ela é
```

`dados/` (o banco, os originais e as evidências) fica fora do repositório.

## Regras do projeto

- **Captcha nunca se contorna.** Portal com captcha ou login fica de fora (por isso a
  Assembleia Legislativa do Paraná e as câmaras do IPM Atende.net não estão aqui).
- O robots.txt de cada portal é respeitado, com o Crawl-delay que ele pede; o
  User-Agent diz que é um robô.
- Assessor e servidor aparecem só em totais, sem nome. O nome é descartado já na
  leitura, antes de qualquer gravação; os originais com nome ficam só na máquina que
  coleta (`dados/`, fora do repositório).
- Fornecedor pessoa física aparece com o CPF mascarado e não entra no grafo. O CPF que
  uma fonte publica do próprio parlamentar (CLDF) não é gravado.
- O que a fonte não publica aparece como "a fonte não publica", nunca como zero.
- Nenhum número inventado ou arredondado; só vai para o ar o que passou na
  conferência.
- A plataforma é independente e não imita site oficial.

## Limites conhecidos

- Partido de vereador é o da eleição do mandato; troca de partido durante o mandato
  não está em nenhuma das fontes.
- O custo de gabinete é um retrato da data da coleta (Betha e Elotech conferidos um
  contra o outro). Nenhuma fonte publica a folha mês a mês por gabinete para anos
  passados; a série cresce a cada coleta.
- Os JSON publicados somam 67 MB: um arquivo por parlamentar com os agregados, e as
  linhas à parte, um arquivo por parlamentar e ano, que a página só busca quando
  alguém abre aquele ano. Cada casa tem o seu resumo (`casas/<id>.json`). Quase tudo é
  linha a linha da cota federal (48 MB) e da ALESP (11 MB).
- Partido de deputado estadual: o da lista de deputados da própria assembleia, hoje.
  A CLDF não publica partido, e quem saiu da ALESP fica sem.
- O subsídio do vereador é um retrato da data da coleta, como o custo de gabinete.
- Atividade nas sessões: o que cada câmara registra no SAPL varia. Irati, por exemplo,
  registrou presença em 1 das 85 sessões de 2025–2026; a página do vereador diz quantas
  sessões a câmara fez e em quantas registrou presença, para o número não parecer falta.
- O SAPL de outras ~108 câmaras do PR fica para as próximas rodadas: a um pedido por
  minuto, cada câmara custa de 15 minutos a mais de 10 horas, conforme o volume de votos.

## Licença

O código está sob a [licença MIT](LICENSE). Os dados são públicos e vêm das fontes
citadas acima (Câmara dos Deputados, as assembleias legislativas, as câmaras
municipais e a Prefeitura de Curitiba, e o TSE); a malha dos mapas é do IBGE.
A licença do código não se aplica a eles.
