# Integração contínua

Três workflows em [`.github/workflows/`](../.github/workflows/). Nenhum usa segredo:
o `GITHUB_TOKEN` de cada um só tem a permissão que o próprio YAML pede.

## CI (`ci.yml`), a cada push

Roda em todo push, em qualquer branch, e em PR que venha de fork. Todo `uses:` está
fixado pelo SHA do commit, com a versão ao lado; o Dependabot atualiza os dois.

| Job | O que confere | Reprova quando |
|---|---|---|
| **Python** | `ruff check .`, `mypy` (pacote `coleta`, com `check_untyped_defs`) e `pytest` | um aviso de lint ou de tipo, ou um teste quebrado. O `pytest` padrão deixa de fora os testes de contrato (`-m 'not contrato'` no `pyproject.toml`), que vão à internet. Os de resiliência abrem o Chromium do Playwright, sem rede. |
| **Plataforma** | `npm run build` (export estático em `out/`), `tsc --noEmit` e `npm test` | o build ou os tipos quebram, ou um "R$" no HTML gerado sai sem fonte e data de coleta (`testes/procedencia.mjs`). O `out/` vai como artefato para os dois jobs abaixo. |
| **Navegador** | axe-core e prints de referência, com o Playwright, no `out/` servido como na Vercel (`testes/servidor.mjs`) | uma violação de acessibilidade fora da lista de exceções, uma exceção que já não acha a violação dela, ou um print diferente da referência. |
| **Lighthouse** | `lhci autorun` em oito páginas, três rodadas cada, no perfil de celular | uma nota ou métrica abaixo do orçamento em `plataforma/lighthouserc.js`. |

### axe (`plataforma/testes/e2e/acessibilidade.spec.ts`)

Regras WCAG 2.0, 2.1 e 2.2 (A e AA) e as de boas práticas, em 19 telas
([`estados.ts`](../plataforma/testes/e2e/estados.ts)): uma de cada tipo de página do
export, mais a lista do grafo, a busca aberta, a ficha de procedência aberta e a
página 404. Cada tela roda a 1366 px e no tamanho do Pixel 7.

O axe pega só uma parte dos problemas. O grafo é `<canvas>`, e o axe não enxerga os
pontos: a alternativa de teclado é a lista.

**Exceções conhecidas** ficam em
[`axe-excecoes.ts`](../plataforma/testes/e2e/axe-excecoes.ts), cada uma presa a uma
regra, a um trecho de HTML e às telas em que aparece. Quando o conserto entrar,
apague a exceção: o teste também reprova se uma exceção não cobrir mais nada.

Hoje a lista está vazia. Ela começou com três exceções, que saíram com o conserto
de acessibilidade da plataforma
([#2](https://github.com/GustavoJannuzzi/rpa-transparencia/pull/2)):

| Regra | Onde | Por quê |
|---|---|---|
| `color-contrast` | carimbo sépia na inicial | 3,33:1 sobre a manilha |
| `nested-interactive` | busca aberta | `<button>` dentro de `role=option` |
| `target-size` | busca aberta, só no celular | a lista cobria as abas e o "Ver em lista" |

### Prints de referência (`plataforma/testes/e2e/visual.spec.ts`)

`toHaveScreenshot` em 13 telas, no desktop e no celular, com animação desligada. O
desenho do grafo fica mascarado (é WebGL, e o runner não tem GPU); a casca em volta
é comparada. As imagens ficam em `plataforma/testes/e2e/prints/`; as primeiras
entraram pelo workflow abaixo, em
[#5](https://github.com/GustavoJannuzzi/rpa-transparencia/pull/5).

**As referências só valem no runner Linux do CI.** A fonte é desenhada de outro
jeito no Windows e no macOS, e todo print reprovaria. Por isso, fora do Linux esses
testes são pulados, e as referências nunca são geradas na máquina de quem
desenvolve.

**Para atualizar** depois de uma mudança de tela feita de propósito:

1. Faça o merge da mudança (ou deixe a branch dela no GitHub).
2. Em *Actions*, abra **Atualizar prints de referência** e clique em *Run
   workflow*, escolhendo a branch. Diga no campo o que mudou.
3. O workflow gera os prints no mesmo runner do CI (`ubuntu-24.04`, o Playwright
   do `package-lock.json`), sobe numa branch `prints/atualizar-N`, abre o PR e
   dispara o CI nela.
4. Confira cada imagem na aba de arquivos do PR antes do merge.

Desde 26/11/2026 o repositório deixa o Actions abrir PR (*Settings > Actions >
General > Allow GitHub Actions to create and approve pull requests*). As permissões
padrão do `GITHUB_TOKEN` continuam só de leitura: cada workflow pede no próprio YAML
o que precisa. Se a opção for desligada, a branch sobe do mesmo jeito e o resumo da
rodada traz o link para abrir o PR à mão, como foi no #5.

Quando não há referência nenhuma para um tamanho de tela (antes da primeira rodada
desse workflow), os prints daquele tamanho são pulados com um aviso. Faltando só
algumas, eles reprovam.

### Lighthouse (`plataforma/lighthouserc.js`)

Perfil de celular do Lighthouse: CPU 4x e 4G lenta, simulados. Para cada métrica
vale a melhor das três rodadas, porque o runner compartilhado oscila. O relatório
vai como artefato do workflow (`upload.target: "filesystem"`), e o resumo do job
traz a tabela das notas. Nunca use `temporary-public-storage`: ele publica o
relatório num link aberto.

O orçamento partiu do que o runner mediu na primeira rodada (26/11/2026), menos
uma margem. Faixa entre as três rodadas de cada página:

| Página | Desempenho | Acessibilidade | Boas práticas | SEO | LCP (ms) | TBT (ms) | CLS | JS transferido |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `/` | 77–87 | 96 | 96 | 100 | 754–762 | 516–1.112 | 0 | 182 KB |
| `/partidos/` | 100 | 100 | 96 | 100 | 753–754 | 45–59 | 0 | 145 KB |
| `/parlamentares/` | 100 | 100 | 96 | 100 | 902–904 | 59–61 | 0 | 149 KB |
| `/parlamentares/dep-220704/` | 100 | 100 | 96 | 100 | 752–753 | 47–50 | 0,038 | 149 KB |
| `/como-os-dados-chegam-aqui/` | 100 | 100 | 96 | 100 | 902–903 | 36–59 | 0 | 145 KB |
| `/sobre/` | 100 | 100 | 96 | 100 | 752 | 44–52 | 0 | 145 KB |

Depois do conserto de acessibilidade
([#2](https://github.com/GustavoJannuzzi/rpa-transparencia/pull/2)), acessibilidade
e boas práticas foram a 100 em todas as páginas, e os pisos subiram junto. Na
mesma medição, a inicial ficou com desempenho de 70 a 90 e TBT de 399 ms a 4,4 s
(uma das três rodadas fora da curva, e por isso vale a melhor).

| Orçamento | Inicial (`/`) | Demais páginas |
|---|---:|---:|
| Desempenho, mínimo | 75 | 90 |
| Acessibilidade, mínimo | 98 | 98 |
| Boas práticas, mínimo | 95 | 95 |
| SEO, mínimo | 95 | 95 |
| TBT, máximo | 1.200 ms | 300 ms |
| LCP, máximo | 1.500 ms | 1.500 ms |
| CLS, máximo | 0,1 | 0,1 |
| JS transferido, máximo | 215.000 bytes | 175.000 bytes |

Os números do runner saem bem melhores que os da auditoria de 26/11/2026, que
mediu desempenho 53 e TBT de 2.140 ms na inicial (Lighthouse no perfil de celular,
contra o site no ar): o resultado da simulação depende da máquina que roda. O
orçamento do CI serve para pegar regressão de um commit para o outro, não para
dizer como o site se sai num celular. Quando uma melhoria subir a nota, suba o
piso junto. Quando uma mudança pesar de propósito, suba o teto no mesmo PR e diga
por quê.

## Contrato com os portais (`contrato.yml`), toda segunda-feira

`python -m pytest -m contrato`: um teste por fonte contra o portal de verdade
([`coleta/testes/test_contrato.py`](../coleta/testes/test_contrato.py)). Confere o
que o robô precisa encontrar: o menu e os botões do portal legado, os filtros e o
postback do portal da Prefeitura, a tabela e o contador do Betha, os campos da API
do Elotech e da Câmara dos Deputados, e os arquivos do TSE e da Câmara.

- Roda às 06:17 de segunda-feira (horário de Brasília) e quando alguém pede, em
  *Actions > Contrato com os portais > Run workflow*.
- O que reprovar na primeira tentativa roda de novo 5 minutos depois, só aquelas
  fontes (`pytest --last-failed`). Portal lento ou fora do ar por alguns minutos
  não é portal que mudou.
- Se reprovar também na segunda, abre uma issue com o rótulo `portal-mudou`, ou
  comenta na que já estiver aberta, com a tabela por fonte e o link da rodada.
  Quando o contrato volta a passar, comenta e fecha a issue.
- O robô continua educado: uma rodada por semana, uma requisição por vez, com o
  User-Agent de cada fonte. O Betha devolve 403 para "HeadlessChrome", e o
  navegador do robô já se apresenta de outro jeito. Nenhum captcha é contornado.
- Num PR que mexa no workflow ou nos testes de contrato, ele roda para mostrar o
  resultado, mas não abre issue.
- Os testes das casas novas (Elotech genérico, CLDF, ALMG e ALESP) são pulados, com o
  motivo, quando o portal nem abre a conexão a partir do runner: em 26/11/2026 a
  CLDF e a ALMG não responderam do GitHub (fora do Brasil). Isso é rede, não portal
  que mudou; o que responder segue conferido, e na máquina de quem coleta eles
  rodam inteiros.

### Rodadas registradas

| Quando | Como | Resultado |
|---|---|---|
| 26/11/2026, 19:37 UTC | [PR #1](https://github.com/GustavoJannuzzi/rpa-transparencia/pull/1), runner do GitHub | 6 de 6 passaram, em 34 s |
| 26/11/2026, 19:49 UTC | PR #1, segundo push | 6 de 6 passaram |
| 26/11/2026, 20:01 UTC | PR #1, terceiro push | 6 de 6 passaram |
| 26/11/2026, 20:04 UTC | PR #1, depois do rebase | 5 de 6: o portal da Prefeitura não terminou de abrir em 30 s (`Page.goto` com tempo esgotado). Foi isso que levou à segunda tentativa 5 minutos depois. |
| 26/11/2026, 20:10 UTC | PR #1, já com a segunda tentativa | 6 de 6 passaram de primeira |
| 26/11/2026, 20:16 UTC | **à mão** (*Run workflow*), na `main` | 6 de 6 passaram de primeira, em 20 s |

As seis fontes responderam aos IPs do GitHub, inclusive o Betha, que recusa
"HeadlessChrome". Por isso nenhuma fica fora do agendado. A falha do portal da
Prefeitura foi de tempo, não de layout: a mesma fonte passou em 8 s nas rodadas
anteriores e em 3 s na rodada à mão. Se um portal passar a
bloquear o runner, a saída é tirar aquela fonte do agendado, com um aviso aqui, em
vez de deixar um alarme falso toda semana. Contornar o bloqueio não é saída.

## Dependabot (`.github/dependabot.yml`)

Toda terça-feira, PRs para pip, npm e GitHub Actions, com o CI rodando em cada um.
Os pacotes de teste de navegador vêm juntos num PR só. Um PR que sobe o Playwright
pode mudar os prints: rode **Atualizar prints de referência** na branch dele.
