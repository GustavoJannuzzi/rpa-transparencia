---
version: 1
slug: "plataforma-app-page-tsx"
primary_target: "plataforma/app/page.tsx"
related_targets: ["plataforma/app/como-os-dados-chegam-aqui/page.tsx","plataforma/app/parlamentares","plataforma/app/partidos","plataforma/app/sobre/page.tsx"]
---

# Plataforma: grafo, partido, parlamentar, como os dados chegam aqui, sobre

Modo: operate (a página "Como os dados chegam aqui" e "Sobre" são leitura dentro do mesmo mundo).
Leitor primário: o cidadão curioso. Tarefa: achar um parlamentar, ver com quem ele gastou e confiar no número porque vê de onde veio.
Abertura confirmada: o grafo ocupa a tela, com a coleta ao lado.
Evitar (confirmado): cara de portal oficial, tom de denúncia, dashboard genérico de BI, estética hacker/neon.

## Direction contract

THESIS: o grafo de quem gastou com quem, com a ficha de procedência de cada número a um clique; recusa o painel de cartões de KPI e o portal institucional azul.

OWN-WORLD: fichário de arquivo à noite. Fundo grafite de gaveta de aço (#1b2220), tinta de texto creme (#e8e2d2), fichas de cartolina manilha (#d8c79f) com texto escuro para a procedência, tinta violeta de carimbo (#8a6fd1) só em conferência e foco, abas de fichário em tons apagados para os partidos (atribuídos em ordem alfabética, nunca cores oficiais de partido). Archivo nos títulos e números grandes, Libre Franklin no texto, algarismos tabulares. Sem moldura decorativa: tipo e campos de cor fazem a estrutura (raise do Metro).

STORY: o visitante vê o grafo e entende que pontos são parlamentares e cores são partidos; busca um nome; abre o parlamentar e vê cada despesa com o link do documento oficial; clica num valor e a ficha mostra fonte, sistema, data da coleta e o carimbo da conferência; na gaveta da coleta, entende que o mesmo órgão está espalhado em quatro sistemas e que o que não fechou está em revisão.

FIRST VIEWPORT: barra de 64px com a marca, a navegação (Grafo, Partidos, Como os dados chegam aqui, Sobre) e a busca à direita. Abaixo, grade de duas áreas: o grafo ocupa o resto da largura com o título "Quem gastou com quem, e de onde vem cada número" e a nota de neutralidade no canto superior esquerdo e as abas de vista (Brasil · fornecedores / Paraná · partidos) presas embaixo como abas de fichário; à direita, coluna de 440px "A coleta" com uma ficha por fonte (sistema, como, anos, origem = coletado + revisão, carimbo). Ação principal: a busca e o clique num ponto.

FORM: Arquivo de procedência, item 3 da minha lista ordenada (1 atlas celeste, 2 diagrama da RIT, 3 arquivo de fichas, 4 nota fiscal, 5 carta topográfica, 6 livro-caixa, 7 etiqueta de museu). seed:26e5c591d8182fe5. Raises: índice e grafo são o mesmo espaço (catálogo de convenção); ao filtrar, ponto e linha mantêm o lugar e o que mudou fica marcado (painel de embarque); hierarquia por contraste de escala (espécime); sem moldura (Metro). Assinatura: a ficha de procedência que sai da gaveta quando se clica num número.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Decisões em aberto

- Nome do produto (provisório: rpa-transparencia).
