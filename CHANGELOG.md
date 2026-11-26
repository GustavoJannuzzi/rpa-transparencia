# Mudanças

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/), e as
versões seguem o [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não publicado]

### Adicionado

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
