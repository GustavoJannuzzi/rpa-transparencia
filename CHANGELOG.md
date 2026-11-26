# Mudanças

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/), e as
versões seguem o [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não publicado]

### Adicionado

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

### Corrigido

- Os avisos do ruff e do mypy no pacote `coleta` (imports sem uso, tipos de
  variáveis reaproveitadas, `zip` sem `strict` onde o tamanho já é conferido, um
  lambda que capturava a variável do laço). Nenhuma mudança de comportamento: os
  mesmos testes passam.

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
