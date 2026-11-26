---
name: rpa-transparencia
description: Despesas de parlamentares com a procedência de cada número, num fichário de arquivo à noite.
colors:
  gaveta: "#1b2220"
  gaveta-2: "#212a27"
  gaveta-3: "#27312e"
  aco: "#2f3a36"
  aco-2: "#3c4844"
  tinta: "#e8e2d2"
  tinta-2: "#bdb8aa"
  tinta-3: "#929e98"
  manilha: "#d8c79f"
  manilha-2: "#e6d9b8"
  manilha-tinta: "#23201a"
  manilha-tinta-2: "#5a5240"
  carimbo: "#8a6fd1"
  carimbo-claro: "#b3a0ea"
  carimbo-escuro: "#5a43a6"
  sepia: "#5f4f27"
  sepia-claro: "#cdb274"
  contorno: "#6f7a75"
typography:
  display:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "3.2rem"
    fontWeight: 500
    lineHeight: 1.04
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 500
    lineHeight: 1.375
  title:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "1.02rem"
    fontWeight: 600
    lineHeight: 1.25
  body:
    fontFamily: "Libre Franklin, system-ui, sans-serif"
    fontSize: "0.95rem"
    fontWeight: 400
    lineHeight: 1.625
  label:
    fontFamily: "Libre Franklin, system-ui, sans-serif"
    fontSize: "0.8rem"
    fontWeight: 400
    lineHeight: 1.375
  carimbo:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "0.68rem"
    fontWeight: 600
    letterSpacing: "0.08em"
  numero:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "2.9rem"
    fontWeight: 500
    lineHeight: 1
    letterSpacing: "-0.02em"
    fontFeature: "\"tnum\", \"lnum\""
rounded:
  ficha: "3px"
  campo: "6px"
  aba: "5px"
spacing:
  margem: "16px"
  margem-sm: "32px"
  ficha: "16px"
  coluna-coleta: "440px"
  container: "1600px"
  barra: "64px"
components:
  ficha-procedencia:
    backgroundColor: "{colors.manilha}"
    textColor: "{colors.manilha-tinta}"
    rounded: "{rounded.ficha}"
    padding: "16px"
    width: "22rem"
  ficha-coleta:
    backgroundColor: "{colors.manilha}"
    textColor: "{colors.manilha-tinta}"
    rounded: "{rounded.ficha}"
    padding: "14px 16px"
  carimbo-conferido:
    textColor: "{colors.carimbo-escuro}"
    typography: "{typography.carimbo}"
    rounded: "{rounded.ficha}"
    padding: "2px 6px"
  carimbo-revisao:
    textColor: "{colors.sepia}"
    typography: "{typography.carimbo}"
    rounded: "{rounded.ficha}"
    padding: "2px 6px"
  campo-busca:
    backgroundColor: "{colors.gaveta-2}"
    textColor: "{colors.tinta}"
    rounded: "{rounded.campo}"
    padding: "0 14px"
    height: "40px"
  aba-vista-ativa:
    backgroundColor: "{colors.manilha}"
    textColor: "{colors.manilha-tinta}"
    rounded: "{rounded.aba}"
    padding: "8px 12px 6px"
  aba-vista:
    backgroundColor: "{colors.gaveta-3}"
    textColor: "{colors.tinta-2}"
    rounded: "{rounded.aba}"
    padding: "8px 12px 6px"
  botao-secundario:
    textColor: "{colors.tinta-2}"
    rounded: "{rounded.campo}"
    padding: "8px 16px"
---

# Design System: rpa-transparencia

## Overview

**Creative North Star: "O fichário de arquivo à noite"**

Uma gaveta de aço grafite aberta sob luz baixa. O fundo é escuro e plano; o texto é tinta creme; tudo o que é procedência (de onde veio um número, se a coleta fechou) sai em fichas de cartolina manilha com texto escuro. A tinta violeta de carimbo é rara: marca conferência, foco e o item ativo, nada mais. Os partidos aparecem como abas de fichário em tons apagados, atribuídos pela ordem de frequência na vista, nunca pela cor oficial de partido.

Não há moldura decorativa. A estrutura vem do tipo (Archivo grande e apertado contra Libre Franklin calma), dos campos de cor (gaveta, aço, manilha) e de filetes de 1px. A hierarquia é contraste de escala: um título ou um total em reais grande, todo o resto pequeno e tabular. O gesto assinatura é a ficha que sobe da gaveta quando se clica num número, com o carimbo batendo logo depois.

**Key Characteristics:**
- Escuro e plano; profundidade só nas fichas que saem.
- Manilha = procedência. Violeta = conferência e foco. Nada mais usa essas duas cores.
- Todo valor em reais é clicável e tem ficha; algarismos sempre tabulares.
- Abas de fichário (canto superior arredondado) para vistas e para a cor de partido.
- Carimbos girados (-6deg), em caixa alta, com borda de 2px.

## Colors

Grafite esverdeado em camadas, tinta creme em três pesos, cartolina manilha e uma única tinta de carimbo violeta.

### Primary
- **Violeta de carimbo** (carimbo): sublinhado do item ativo da navegação, borda do campo em foco, nó selecionado no grafo, seleção de texto.
- **Violeta claro** (carimbo-claro): anel de foco global (2px, offset 2px), hover dos valores e links sobre a gaveta, links de texto sobre o fundo escuro, contorno do nó em hover.
- **Violeta fundo de tinta** (carimbo-escuro): texto e borda do carimbo CONFERIDO e links dentro da ficha manilha.

### Secondary
- **Cartolina manilha** (manilha): fundo de toda ficha (procedência, coleta, nó selecionado), aba de vista ativa, filete de 2px sob as abas, preenchimento das barras (a 80%), nó de partido no grafo.
- **Manilha clara** (manilha-2): rótulo de partido desenhado no grafo.
- **Tinta de ficha** (manilha-tinta) e **tinta de ficha secundária** (manilha-tinta-2): texto principal e rótulos de campo dentro da manilha.

### Tertiary
- **Sépia de revisão** (sepia, #5f4f27): carimbos VER CONFERÊNCIA / EM REVISÃO / FORA DA SOMA sobre manilha. Só para carimbo. Escurecida em 26/11 para 4,8:1 sobre a manilha (a anterior, #7a6635, dava 3,3:1).
- **Sépia clara** (sepia-claro): nota "Não somada" sobre a gaveta, na tabela de despesas, e o carimbo EM REVISÃO quando ele fica sobre a gaveta (linha "Fora desta soma" do parlamentar, ano em revisão na tabela de diárias).

### Neutral
- **Gaveta** (gaveta): fundo da página e `theme-color`.
- **Gaveta 2** (gaveta-2): campos, lista da busca, fundo do quadro do grafo.
- **Gaveta 3** (gaveta-3): aba inativa, opção ativa da busca, trilho das barras, chip de partido em foco.
- **Aço** (aco) e **aço 2** (aco-2): filetes de cabeçalho, rodapé, colunas e linhas de tabela (aco); borda da lista suspensa, barra de rolagem (aco-2).
- **Contorno** (contorno, #6f7a75): borda de campo, select e botão secundário. É o cinza das abas "demais", e dá 3,3:1 sobre a gaveta-2, o mínimo para o contorno de um controle.
- **Tinta** (tinta), **tinta 2** (tinta-2), **tinta 3** (tinta-3): texto principal, texto de apoio, metadados e legendas (tinta-3 a 5,8:1 sobre a gaveta).

Abas de partido (lib/cores.ts): dez tons apagados (ouro, verde-água, malva, azul-acinzentado, terracota, oliva, azul-névoa, areia, sálvia, rosa-pó) mais um cinza (#6f7a75) para "demais". O violeta fica fora dessa lista.

### Named Rules
**The Carimbo Raro Rule.** O violeta só aparece onde houve conferência, foco ou estado ativo. Nunca como fundo de área, nunca em gráfico, nunca como cor de partido.

**The Manilha É Procedência Rule.** Superfície manilha significa "isto diz de onde veio o dado". Não use manilha para cartões de conteúdo comum, destaques de marketing ou botões.

**The Aba Não É Partido Rule.** A cor de um partido vem da posição dele na contagem da vista, nunca da cor oficial. A mesma sigla pode trocar de tom entre vistas.

## Typography

**Display Font:** Archivo (com system-ui, sans-serif), pesos 400/500/600
**Body Font:** Libre Franklin (com system-ui, sans-serif), pesos 400/500

**Character:** Archivo, grotesca de arquivo, aperta os títulos e os totais; Libre Franklin carrega a leitura com calma. Números sempre `tabular-nums lining-nums` (classe `.num`).

### Hierarchy
- **Display** (500, 2.4rem a 3.2rem; 3rem a 4rem no nome do partido; altura 1.02 a 1.04; -0.02em): título de página, no máximo ~20 a 24ch.
- **Número grande** (500, 2.4rem a 2.9rem, altura 1, -0.02em, tabular): total conferido no cabeçalho do parlamentar e do partido, sempre clicável com ficha.
- **Headline** (500, 1.5rem a 2.2rem): seções ("A coleta", "Despesas, uma a uma").
- **Title** (600, 0.95rem a 1.35rem): nome da fonte na ficha de coleta, título da ficha, contagem de linhas na origem.
- **Body** (400, 0.92rem a 1.05rem, leading relaxado): parágrafos com 62 a 70ch de medida.
- **Label** (400, 0.78rem a 0.8rem, tinta-3 ou manilha-tinta-2): cabeçalho de tabela, CNPJ, rótulos de campo na ficha.
- **Carimbo** (Archivo 600, 0.62rem a 0.68rem, 0.06em a 0.08em, caixa alta): só dentro de carimbos.

### Named Rules
**The Caixa Alta É Carimbo Rule.** Caixa alta com espaçamento só existe no carimbo, que é objeto do mundo. Nada de rótulo em caixa alta acima de título.

## Layout

Container de até 1600px, margens laterais de 16px (32px a partir de `sm`). Barra superior de 64px em `lg` com marca, navegação e busca à direita; abaixo de `lg` ela empilha. A página inicial é uma grade de duas áreas em `lg`: o grafo ocupa `1fr` com altura mínima de tela menos a barra, e "A coleta" é uma coluna fixa de 440px separada por filete de aço; no celular a coleta desce para baixo do grafo. Páginas de leitura usam ~1180px de largura; a do parlamentar divide em tabela larga à esquerda e coluna de barras à direita. Ritmo vertical em passos de 4px (gap de 12px entre fichas, 20px entre blocos). Densidade alta e tabular: é um arquivo, não uma vitrine.

## Elevation & Depth

Tudo é plano e em camadas tonais (gaveta, gaveta-2, gaveta-3) separadas por filetes de aço. Sombra existe só no que flutua sobre a gaveta: a ficha de procedência, a ficha do nó selecionado e a lista da busca. Sombras são longas, escuras e deslocadas para baixo, como papel erguido de uma gaveta.

### Shadow Vocabulary
- **Ficha erguida** (`box-shadow: 0 14px 30px -8px rgba(0,0,0,0.6)`): ficha de procedência.
- **Ficha do nó** (`box-shadow: 0 18px 36px -12px rgba(0,0,0,0.7)`): ficha do ponto selecionado no grafo.
- **Lista suspensa** (`box-shadow: 0 14px 30px -10px rgba(0,0,0,0.7)`): resultados da busca.

### Named Rules
**The Só O Que Sai Da Gaveta Rule.** Superfície em repouso não tem sombra. Sombra só em ficha ou lista que abre sobre o conteúdo.

## Shapes

Cantos quase retos. Fichas e carimbos com 3px; campos, selects e botões com 6px; abas de vista com 5px só nos cantos de cima, presas sobre um filete manilha de 2px; amostra de partido é uma aba de 14 x 8px arredondada em cima. As fichas da coleta alternam um recuo de 6px, como cartões mal alinhados numa gaveta. Carimbos giram -6deg (o segundo, -3deg). Barras de proporção são o único elemento totalmente arredondado.

## Components

### Ficha de procedência (assinatura)
Todo valor em reais passa pelo componente de valor: sublinhado pontilhado em tinta-3, hover em violeta claro, `cursor: help`. O clique abre uma ficha manilha de até 22rem: título "De onde vem este número", carimbo no canto (CONFERIDO, SOMA CONFERIDA ou FORA DA SOMA), filete, fontes, grade rótulo/valor (Coleta, Linhas, No original, Nota), link "Abrir o documento oficial" e "fechar". A ficha é desenhada fora do fluxo (portal no body), para nunca ficar presa num contêiner com rolagem. No computador, sai embaixo do número (em cima, se não couber), alinhada pela borda que cabe e nunca a menos de 16px da borda da tela. Abaixo de 640px, sobe da base da tela como uma folha de largura inteira, com a mesma manilha e o mesmo carimbo. Recebe o foco ao abrir; fecha com Esc, clique fora ou o Tab que sai dela, e o foco volta ao número. Valor fora da soma aparece riscado e em tinta-3.

### Linha "Fora desta soma"
Logo abaixo do total do parlamentar: carimbo EM REVISÃO em sépia clara sobre a gaveta e a frase do que ficou de fora (categoria e anos, quantas despesas), com "Por quê" levando à seção "Em revisão, fora da soma", que explica cada recorte em português de leigo e leva à fila de revisão da fonte. Para vereador, separa os anos de mandato em revisão dos anos sem diária nas fontes.

### Ficha da coleta
Uma ficha manilha por fonte: nome em Title, modo e anos em Label, e a equação "N linhas na origem = publicadas + em revisão" com o N em Archivo 1.35rem. Carimbos empilhados no canto superior direito.

### Carimbo
Borda de 2px, cantos de 3px, Archivo 600 em caixa alta, girado. Violeta fundo de tinta quando conferido; sépia quando há revisão ou fora da soma. Entra com a animação de batida.

### Abas de vista e quadro do grafo
Abas de fichário em Archivo 0.9rem: ativa em manilha, inativa em gaveta-3; respondem às setas, a Home e a End. Embaixo delas, uma linha de dica em tinta-3. O quadro do grafo é gaveta-2 com filete manilha de 2px no topo, e leva por cima: no canto superior esquerdo, o campo "Achar alguém no grafo" (a mesma busca do topo, que aqui seleciona o ponto, trocando de vista se preciso); no direito, três botões empilhados (aproximar, afastar, ver o grafo inteiro) em gaveta a 90% com contorno, ícones desenhados de traço 1.6. Enquanto o canvas carrega, o quadro mostra o mesmo grafo como imagem gerada no build (mesmo layout, cores e tamanhos), com "Abrindo o grafo…" no canto. Rótulos de partido no canvas são placas gaveta a 88% com texto manilha-2, posicionadas para não se sobreporem; o hover desenha placa escura com texto creme e anel violeta claro de 2px. Um toque perto de um ponto (22px além da borda dele) vale como toque no ponto. A legenda é uma lista de chips com aba colorida, sigla e contagem: abaixo do quadro até `lg`, e dentro dele, no canto inferior direito, a partir de `lg`. "Ver em lista" oferece a tabela acessível equivalente.

A ficha do ponto é manilha, como a de procedência: no computador, dentro do quadro, no canto inferior esquerdo, e a câmera põe o ponto no meio da área livre à direita dela; abaixo de 640px, sobe da base da tela como folha, e a câmera rola o quadro para cima e põe o ponto acima da folha. Mostra todas as ligações do ponto, com os fornecedores em comum por extenso (os nomes chegam à parte, na primeira ficha aberta). Esc fecha.

Vista, ponto escolhido, lista e partido em foco ficam na URL (`/?vista=parana&no=…&lista=1&partido=…`): o Voltar devolve o grafo como estava, e a página do parlamentar tem o link "Ver … no grafo". Sem nada na URL, o celular abre no Paraná (leve e legível) e o computador no Brasil.

### Cobertura e casas
A página Cobertura é a vitrine dos vários sistemas e tem cinco blocos, nesta ordem:
- **Frase medida:** sem cartões de KPI, uma frase em Archivo com os números da coleta ("N casas coletadas, em M sistemas diferentes") e uma linha de apoio com parlamentares, linhas e a data da coleta.
- **Fichas de sistema:** uma ficha manilha por adaptador (sistema, fornecedor, modo, casas que ele atende, com os anos), no recuo alternado de 6px das fichas da coleta. A ficha do sistema que atende muitas casas ocupa a largura toda e lista as casas em colunas.
- **Mapas:** o Paraná por município e o Brasil por UF, como SVG estático gerado no `publicar` a partir da malha do IBGE. O preenchimento diz a situação: manilha para "coletada" (o mesmo preenchimento das barras), hachura sépia clara para "em revisão", hachura em contorno para "o portal barra o robô" (robots.txt, Cloudflare, captcha), gaveta-3 para "ainda sem adaptador" e gaveta-2, quase o fundo, para o resto. O filete é aço; o da casa coletada, gaveta, para ela saltar. O mapa não é interativo: cada área tem `<title>`, a figura diz por extenso o que mostra, e a tabela é a forma de navegar.
- **Levantamento:** tabela com as contagens do levantamento das fontes, sempre rotuladas com a data, separadas do que a coleta mediu.
- **Todas as casas:** tabela agrupada (Congresso, Assembleias, Câmaras do PR), com uma busca e um select de situação que filtram no navegador. Três colunas: casa, sistema do portal e situação, que traz a amostra da mesma cor do mapa, o rótulo e o motivo em português de leigo.

A página de cada casa segue o desenho do parlamentar: cabeçalho com o total na ficha, a linha "Fora desta soma", as fichas de sistema com a equação "N linhas na origem = publicadas + em revisão" e o carimbo, a tabela ano a ano (vereadores com nome × servidores só na soma, e "a fonte não publica" no lugar de zero), a revisão por motivo, os membros em ordem alfabética e, na coluna, categoria, subsídio, outras conferências e os fornecedores pagos por mais de um.

### Inputs / Fields
- **Style:** fundo gaveta-2, borda contorno de 1px, cantos de 6px, 40px de altura na busca e nos selects; placeholder tinta-3; cursor de texto violeta claro.
- **Focus:** a borda passa a violeta; o resto do sistema usa o contorno global violeta claro.
- **Busca:** combobox com lista suspensa gaveta-2; opção ativa em gaveta-3, nome à esquerda e "partido · UF" em tinta-3 à direita.

### Buttons
- **Secundário:** sem fundo, borda aço-2, cantos de 6px, 8 x 16px, texto tinta-2 que clareia para tinta no hover ("Mostrar mais").
- **Ações em texto:** a maioria das ações é link sublinhado (offset 3px, 1px), tinta-2 indo a tinta ou violeta claro.

### Navigation
Itens em Libre Franklin 0.95rem, tinta-2; hover em tinta; ativo em tinta com sublinhado interno violeta de 2px. No celular a lista quebra em linhas sob a marca.

### Tabelas e barras
Tabelas sem zebra: cabeçalho em Label tinta-3 sobre filete aço-2, linhas separadas por filete aço, valores alinhados à direita. Barras horizontais: trilho gaveta-3 de 6px, preenchimento manilha a 80%, número exato com ficha ao lado do rótulo; o comprimento é só desenho.

### Movimento
A ficha sai em 260ms (`cubic-bezier(0.16, 1, 0.3, 1)`), subindo 10px com leve giro e revelada de cima para baixo; o carimbo bate em 320ms com atraso de 120ms, de escala 1.35 a 1. Com movimento reduzido, tudo vira corte.

## Do's and Don'ts

### Do:
- **Do** passar todo número em reais pelo componente de valor, com ficha e algarismos tabulares.
- **Do** usar manilha com texto manilha-tinta para qualquer superfície de procedência, cantos de 3px.
- **Do** reservar o violeta para conferência, foco e item ativo (The Carimbo Raro Rule).
- **Do** tirar a cor de partido da lista de abas por ordem de frequência na vista, com o cinza para "demais".
- **Do** separar áreas com filetes de aço de 1px e camadas tonais da gaveta, sem sombra em repouso.
- **Do** oferecer uma lista acessível equivalente a qualquer vista em canvas.

### Don't:
- **Don't** usar a cor oficial de um partido, nem violeta em partido.
- **Don't** pôr rótulo em caixa alta acima de títulos; caixa alta é só do carimbo.
- **Don't** montar painel de cartões de KPI nem a cara de portal institucional azul.
- **Don't** usar néon, brilho ou estética hacker; a gaveta é fosca.
- **Don't** usar sépia para texto corrido sobre manilha; ela fica nos carimbos.
- **Don't** pôr sombra em superfície que não abre sobre o conteúdo.
