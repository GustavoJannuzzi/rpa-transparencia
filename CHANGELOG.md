# Mudanças

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/), e as
versões seguem o [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não publicado]

### Adicionado

- **Assembleia de Pernambuco pela tela** (frente D2): o app React em quatro níveis
  (deputado e ano, meses, pedidos, notas), cada um pedido pela própria tela, com as notas
  de cada pedido conferidas contra o total do pedido.
- **Documentação da arquitetura** ([`docs/arquitetura.md`](docs/arquitetura.md)):
  componentes, fluxo de dados e a sequência de uma coleta com Playwright em Mermaid;
  os padrões que o código usa e onde (adaptador por fornecedor, esqueleto único de
  coleta, registro em `entidades.toml`, pipeline pelo banco, camada do SQLite,
  dependências invertidas para os testes sem rede, erros com tipo); e as decisões de
  projeto. O README ganha o que o projeto demonstra, os robôs por plataforma com a
  técnica de cada um e como pôr uma casa nova; o `docs/ci.md`, a contagem certa de
  telas no axe (23) e nos prints (14).
- **Assembleias pela tela, GO e RN** (frente D2). Goiás: a rota da tela de cada deputado
  no mês, lida pela resposta que a tela recebe, conferida em três níveis contra o dado
  aberto da casa; janela 2025–2026, pelo peso no site e porque o portal recusa conexão
  em rajadas (o motivo está em `entidades.toml` e na Cobertura). Rio Grande do Norte:
  `mat-select`, PESQUISAR e a resposta da tela (a API dá 401 fora do app), conferida
  contra a frase do total, o paginador e a tabela lida página a página.
- **"Em coleta" na Cobertura**: TO e BA têm o robô pronto e a coleta em andamento, e
  a página diz isso, em vez de "sem adaptador".
- **Assembleias pela tela, AP e CE** (frente D2): `FonteAssembleiaTela`, que espera a
  vez do portal a cada gesto e guarda a resposta que a tela recebeu, e a conferência de
  cada uma contra os totais da própria tela. Amapá: cascata AJAX, POST e iframe por
  elemento de despesa, com a conferência em três degraus. Ceará: chave do detalhe em
  base64 do nome, tela conferida contra o CSV do mês da casa, tabela de grafias com a
  prova de cada ligação, e nome digitado com erro que vai para a revisão em vez de virar
  deputado.
- **Govbr Pronim em 6 câmaras do PR**: robô de navegador no ASP clássico (formulário
  único, ano com chave interna, entidade e desdobramentos por AJAX, "Gerar"). A tela
  mostra o CPF sem máscara: o robô lê o documento só na memória (para ligar a mesma
  pessoa entre as consultas) e mascara a página antes de gravar qualquer coisa,
  inclusive o original; um teste prova isso contra um portal falso. A tela soma por
  credor no período: cada linha publicada é um agregado (credor × mês), conferido
  contra a consulta do ano inteiro. Quem é vereador sai do desdobramento "agentes
  políticos"; a unidade gestora é a da Câmara, não a consolidada.
- **Equiplano em 10 câmaras do PR**: robô de tela no formulário "Empenhos de Diárias
  Concedidas" (cascata por AJAX, recarga no exercício, período digitado com máscara,
  download por botão) e leitor do relatório impresso que vem como CSV. A soma dos
  empenhos líquidos de cada ano é conferida contra o total do rodapé do relatório.
  O CPF e o RG que alguns relatórios trazem inteiros saem na memória, antes de
  gravar o original; o robots.txt é lido pelo navegador quando o servidor não manda
  a cadeia TLS inteira.
- **Betha em 14 câmaras do PR**: o coletor de Curitiba generalizado. A câmara vem de
  `entidades.toml` pelo código do portal, conferido no IBGE que o portal informa; a
  consulta de diárias é achada pelo texto do item no menu da tela (cada câmara monta
  o seu). 13 câmaras novas, uma por região; União da Vitória, Goioerê, Jaguariaíva e
  Mandirituba ficam de fora, com o motivo na Cobertura. A conferência manda para
  revisão as diárias de servidor de consulta de câmara que traz cargo do Executivo.
- **`importar`**: leva as linhas de algumas fontes de um banco de trabalho para o
  canônico, numa transação só, com os originais e as evidências delas. A coleta
  longa pelo navegador roda à parte, e a trava do canônico dura minutos. Rodar de
  novo dá o mesmo banco, e importar uma fonte não toca as outras.
- **Coleta longa sem encher o disco**: a coleta para antes do próximo item com menos de
  400 MB livres e deixa o item pendente para a retomada; nas fontes com navegador, o
  contexto é trocado a cada 20 itens e o rastro leva só os prints (com os snapshots, o
  Temp passou de 800 MB por fonte numa coleta de horas e encheu o disco). O rastro
  fica no Temp do navegador até ele fechar, mesmo com o contexto trocado: a fonte de
  item longo põe `rastrear = False` (a evidência do erro fica com o print e o
  HTML da página).
- **Atividade nas sessões** (frente D3, [#21](https://github.com/GustavoJannuzzi/rpa-transparencia/pull/21) e [#25](https://github.com/GustavoJannuzzi/rpa-transparencia/pull/25)): um tipo de dado novo, não despesa. O
  adaptador do SAPL (Interlegis) lê sessões, presença, ausências (com o motivo da
  fonte, que pode ser "não apresentou justificativa") e votos nominais de 6 câmaras do PR, respeitando o Crawl-delay de
  60 s do robots.txt: janela por câmara com data de corte, inventário página a página
  com filtro congelado, retomada sem repetir pedido, `--paralelo` para câmaras em
  servidores diferentes e reprodução da coleta gravada num banco de trabalho. A
  frequência dos vereadores de Curitiba vem dos 64 relatórios em PDF do Betha
  (2019–2026), pelo navegador, com o link de 24 h usado na hora e nunca guardado. Os
  nomes se ligam aos vereadores das fontes de despesa; o que não fecha vai para
  revisão. Na plataforma: a seção "Nas sessões" na página do vereador e na da casa,
  contagem bruta com a ficha de procedência de cada número, e o bloco "Atividade nas
  sessões" na Cobertura, com a janela, o corte e o motivo de cada câmara de fora.

### Corrigido

- **Resposta que não chegou inteira não vira "nenhuma nota"** (PE, BA e TO): na rede que
  oscila, a tela recebe o 200 sem o corpo, e o leitor do PE lia isso como pedido sem nota
  (52 pedidos de um deputado; a conferência pegou e nada foi ao ar). Corpo vazio, no PE, e
  página sem o formulário da casa, na BA e no TO, agora são falha transitória, e o robô
  tenta de novo.
- **PE**: a casa manda o valor como texto, inteiro ("21880") ou com vírgula decimal
  ("8372,5" é 8.372,50); a leitura só aceitava ponto e mandava a nota para pendência.
- **TO**: a planilha tem duas formas (a de 2023 diz "CODAP", "Saldo acumulado" e "Gasto
  no mês"), mostra saldo negativo entre parênteses, às vezes deixa o item em branco ou
  escreve uma casa decimal só, e o PDF parte números em dois. A linha "Saldo de Notas
  mês anterior" é o que passou da cota no mês anterior, não nota nova. O ressarcido é
  conferido contra o que coube no saldo; a coluna de saldo da planilha que não fecha,
  com o total fechando, vira observação.
- **BA**: a lista mostra o valor da nota menos a glosa, e a conferência comparava com o
  valor cheio; a glosa de centavos vem sem o zero ("R$ ,17").
- **Achados da auditoria do site no ar (27/11)**:
  - `/casas/camara-deputados/` dava 404, embora o JSON da casa fosse publicado. A
    Câmara dos Deputados ganhou a página de casa, como as outras casas (sistema,
    conferência, ano a ano, categorias, fornecedores em comum), e a Cobertura, a lista
    de parlamentares e o cabeçalho do deputado passam a levar a ela.
  - O endereço da ALMG mostrado na plataforma era a raiz da API (`/api/v2`), que
    responde 404: passa a ser a página da documentação. Um teste reprova endereço de
    fonte que seja só a raiz de uma API. O site muda na próxima republicação.
  - `/parlamentares/` desenhava todos os nomes de uma vez (1.725 na medição): 70 mil
    px de altura no celular, 3,2 s de linha principal bloqueada só pelo HTML (Pixel 7
    emulado, CPU 4x) e 203 pedidos ao rolar até o fim (cada link visível pedia de
    antemão a página do parlamentar). A lista
    de cada casa agora começa recolhida (`<details>`, sem JavaScript), abre sozinha
    quando o endereço aponta a casa (`#casa-<id>`), e os links não pedem nada de
    antemão. Na casa, a lista de membros só começa recolhida acima de 200 nomes (a da
    Câmara dos Deputados).
  - Textos de cobertura escritos à mão e desatualizados ("DF, MG e SP", "13 câmaras",
    "12 câmaras") na página inicial, em "Como os dados chegam aqui", na descrição de
    Parlamentares e na Sobre: agora saem dos dados no build (`lib/resumo.ts`). Na
    inicial, o que cada grafo mostra é contado no próprio grafo. A busca vazia
    deixou de listar casas e aponta a Cobertura.
  - O painel "A coleta" da inicial diz que as fichas são da Câmara dos Deputados, de
    Curitiba e do TSE, e ganhou o resumo das outras casas por sistema.
  - A tabela de `/partidos/` estourava a tela do celular (400 px num espaço de 358 px
    a 390 px de largura). No celular, os cabeçalhos ficam curtos (o leitor de tela
    ouve o nome inteiro), os números vão à direita, e numa tela estreita demais a
    tabela rola dentro do quadro, sem empurrar a página.
  - Não eram defeito: os portais do Equiplano abrem no navegador (o servidor não
    manda o certificado intermediário, e só um cliente HTTP sem o Chromium recusa), e
    os 504 da nota fiscal eletrônica são do servidor da Câmara dos Deputados.
- **"Em revisão" de Curitiba em vereador de outra cidade**: os anos que o portal da
  Prefeitura de Curitiba manda para revisão (2024 e 2025) apareciam fora da soma na
  página de 580 vereadores de 38 outras câmaras. Agora só uma fonte da própria casa
  põe um ano em revisão. Valores e totais não mudam.
- `importar` com o `tse`: recusa quando a origem não tem as candidaturas de algum
  município e eleição que o destino tem (o partido dos vereadores sumiria); migra
  origem e destino com o código atual e para se as colunas de alguma tabela forem
  diferentes.

- **Muitas casas** ([#9](https://github.com/GustavoJannuzzi/rpa-transparencia/pull/9) e o PR seguinte): um
  adaptador por fornecedor, configurado por entidade em `coleta/entidades.toml`. O
  Elotech passa a servir qualquer câmara (mais 12 do PR, 2023–2026, com o subsídio do
  vereador); entram as assembleias do DF (CSV e planilha), de MG (API) e de SP (JSON
  agregado por fornecedor × tipo × mês, marcado como agregado). A pausa de cada
  portal vem do Crawl-delay do robots.txt. Na plataforma: página de cada casa,
  parlamentar de qualquer casa, busca atravessando as casas e a página Cobertura, com
  o mapa do PR por município, o do Brasil por UF e a tabela de todas as casas, com o
  motivo de cada uma que ficou de fora.
- **CI no GitHub Actions** a cada push: ruff, mypy e pytest no Python; build do
  export estático, `tsc --noEmit` e o teste de procedência na plataforma; axe-core
  (Playwright) em 13 telas, no desktop e no celular; prints de referência com
  `toHaveScreenshot`; e o Lighthouse CI com orçamento. O que cada job confere está
  em [`docs/ci.md`](docs/ci.md).
- **Contrato agendado**: toda segunda-feira o workflow roda `pytest -m contrato`
  contra os portais reais. Se algum reprovar, abre uma issue (ou comenta na aberta)
  e fecha sozinho quando o contrato volta a passar.
- Workflow manual que gera de novo, no runner Linux, os prints de referência e abre
  um PR para revisão.
- Configuração do ruff e do mypy no `pyproject.toml`, com as ferramentas fixadas em
  `requirements-dev.txt`.
- Dependabot para pip, npm e GitHub Actions.
- Licença MIT para o código.
- Animação do robô passando pelos três sistemas de navegador, no README.
- Plataforma: favicon, imagem de compartilhamento (Open Graph), `robots.txt` e
  `sitemap.xml` ([#2](https://github.com/GustavoJannuzzi/rpa-transparencia/pull/2)).

- Grafo: campo "Achar alguém no grafo" dentro do quadro, botões de aproximar,
  afastar e ver o grafo inteiro, dica de uso sob as abas e a legenda dentro do
  quadro no computador ([#7](https://github.com/GustavoJannuzzi/rpa-transparencia/pull/7)).
- Grafo: o estado fica na URL (`/?vista=parana&no=…&lista=1&partido=…`). O Voltar
  devolve o grafo como estava, e a página do parlamentar tem o link "Ver … no
  grafo" ([#7](https://github.com/GustavoJannuzzi/rpa-transparencia/pull/7)).

### Alterado

- **`docs/produto.md`**: para quem é o site, os princípios e o que ele não faz, em
  vez de um arquivo de briefing solto na raiz. O `DESIGN.md` passa a ter os títulos em
  português.
- **Estrutura do núcleo, sem mudar a saída**: a gravação no SQLite sai do executor
  para `nucleo/repositorio.py` (o executor fica com a retomada, a repetição, a
  evidência e a decisão pelo tipo do erro), e o `publicar` de 310 linhas vira uma
  sequência de etapas nomeadas (base, soma das despesas, parlamentares, partidos,
  grafos, casas, CSV). Conferido contra o banco real: as versões antiga e nova geram
  os mesmos arquivos, byte a byte.
- **Testes organizados por tipo**, em `coleta/testes/`: `unidade/` (leitura de
  amostras gravadas, regras da conferência, importar e determinismo, sem rede nem
  navegador), `portal_falso/` (o robô inteiro contra API falsa, portal gravado ou
  portal falso local), `contrato/` (o portal de verdade, `-m contrato`) e `apoio/`
  (os portais falsos e os geradores de amostra). Os arquivos que misturavam os
  tipos foram divididos; são os mesmos 197 testes, com os mesmos nomes.
- Grafo no celular: abre na vista Paraná quando a URL não diz outra; a ficha do
  ponto sobe da base da tela e a câmera põe o ponto acima dela; um toque a até
  22 px de um ponto vale como toque nele; a ficha mostra todas as ligações e os
  fornecedores por extenso ([#7](https://github.com/GustavoJannuzzi/rpa-transparencia/pull/7)).
- Grafo mais leve: `grafo-brasil.json` de 779 KB para 150 KB (os nomes dos
  fornecedores vão para `grafo-brasil-fornecedores.json`, carregado quando a
  primeira ficha abre); os dados são pedidos logo depois da primeira pintura, e um
  desenho do grafo gerado no build ocupa o quadro enquanto o canvas carrega ([#7](https://github.com/GustavoJannuzzi/rpa-transparencia/pull/7)).
- O GitHub Actions pode abrir PR neste repositório, para o workflow de prints
  abrir o dele sozinho. As permissões padrão do `GITHUB_TOKEN` continuam só de
  leitura.

### Corrigido

- O que a conferência deixou em revisão aparece na página do parlamentar, logo
  abaixo do total, com o motivo; 2024 e 2025 entram na tabela de diárias da Câmara
  de Curitiba, marcados; a fila de revisão diz quantas linhas de despesa cada
  motivo segura ([#2](https://github.com/GustavoJannuzzi/rpa-transparencia/pull/2)).
- A ficha de procedência cabe no celular, e a tabela de despesas vira lista lá
  ([#2](https://github.com/GustavoJannuzzi/rpa-transparencia/pull/2)).
- Acessibilidade: contraste do carimbo sépia, busca como combobox com
  `aria-activedescendant`, abas com setas e o foco depois de "mostrar no grafo"
  ([#2](https://github.com/GustavoJannuzzi/rpa-transparencia/pull/2)).
- O link do relatório da conferência, que dava 404 no ar, agora é `/conferencia/`
  ([#2](https://github.com/GustavoJannuzzi/rpa-transparencia/pull/2)).
- Os avisos do ruff e do mypy no pacote `coleta` (imports sem uso, tipos de
  variáveis reaproveitadas, `zip` sem `strict` onde o tamanho já é conferido, um
  lambda que capturava a variável do laço). Nenhuma mudança de comportamento: com
  a mesma base e a mesma semente de hash, o código antigo e o novo geram os mesmos
  JSON, CSV, relatório e tabelas de conferência, tirando os carimbos de hora.
- A mesma coleta publica o mesmo site em qualquer rodada. Antes, a saída dependia
  da semente de hash do Python (`PYTHONHASHSEED`, sorteada a cada processo). A
  ordem das datas de coleta na página do vereador com mais de um sistema mudava
  sozinha, e o nome exibido de quem tem dois nomes parlamentares no gabinete
  também. Agora o nome segue uma regra escrita: o nome parlamentar do período mais
  recente; no empate, o mais completo e depois a ordem alfabética. As datas de
  coleta seguem a ordem cronológica dos sistemas. Com `SOURCE_DATE_EPOCH`, a data
  de geração fica fixa, e duas gerações saem iguais byte a byte. O teste
  `test_determinismo.py` roda a derivação com duas sementes e compara.

## [0.1.0] - 2026-11-26

Etapa 0 e Fase 1, publicadas em https://rpa-transparencia.vercel.app.

### Adicionado

- Levantamento das fontes antes do código ([`docs/etapa-0.md`](docs/etapa-0.md)).
- Robôs para seis fontes num modelo único: o portal legado da Câmara de Curitiba
  (robô + PDF), o Elotech (API), o portal da Prefeitura (robô, ASP.NET WebForms), o
  Betha (robô, Vue), a Câmara dos Deputados (API e arquivo anual) e o TSE (arquivo).
- Núcleo comum: inventário, retomada, repetição com espera, evidência no erro e
  coleta educada (uma requisição por vez em cada portal, respeitando o robots.txt).
- Conferência contra o que a própria fonte diz de si; o que não fecha vai para uma
  fila de revisão, com o motivo.
- Travas do `publicar`: não grava se sobrar nome de servidor nas amostras ou um CPF
  que fecha o dígito verificador.
- Testes de parser, conferência, resiliência (falha injetada e retomada) e contrato.
- Plataforma estática (Next.js e sigma.js) com o grafo, as páginas de partido e de
  parlamentar e a ficha de procedência de cada valor.

[Não publicado]: https://github.com/GustavoJannuzzi/rpa-transparencia/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/GustavoJannuzzi/rpa-transparencia/releases/tag/v0.1.0
