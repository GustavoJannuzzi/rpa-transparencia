# O produto: para quem é o site e o que ele não faz

## Para quem é

- **O cidadão curioso**, o leitor principal. Chega para saber quanto um parlamentar
  gastou e com quem, e se pode confiar no número. Lê no celular ou no computador, sem
  conhecer sistemas de transparência.
- **Quem avalia o trabalho técnico** (RPA, migração de sistemas). Quer ver o robô
  trabalhando: de onde veio cada número, o que foi conferido e o que ficou em revisão.

## O que o site faz

Junta, num modelo só, as despesas públicas de parlamentares que vêm de sistemas que
não conversam entre si, e mostra tudo num grafo que agrupa por partido e liga por
fornecedor em comum. O site é estático: os dados saem do robô (`coleta/`) em JSON, e a
plataforma não consulta nada ao vivo.

Ele cumpre o papel quando o visitante acha o parlamentar, entende o que está vendo e
confia no número porque vê de onde ele veio.

## Princípios

1. **Procedência antes de opinião.** O número vem com a fonte, a data da coleta e o
   documento oficial, ou não aparece.
2. **O que não se leu com certeza aparece como pendente**, numa fila de revisão
   visível. Nunca é escondido nem completado.
3. **Neutralidade.** O desenho descreve, não acusa.
4. **O robô é o protagonista técnico.** O site é a vitrine que torna o trabalho dele
   legível para qualquer pessoa.

## O que o site não faz

- Não se parece com portal oficial: sem brasão e sem a identidade da Câmara, da
  Prefeitura ou do gov.br.
- Não faz ranking de quem gasta mais, nem usa adjetivo, cor de alerta ou tom de
  denúncia. A tela do grafo diz que fornecedor em comum não insinua nada.
- Na atividade das sessões, mostra contagem bruta com procedência: nada de taxa,
  ordem por quem falta mais ou palavra de acusação.
- Assessor e servidor aparecem só no agregado. Fornecedor pessoa física aparece com o
  CPF mascarado e não entra no grafo.
- Cada valor leva o rótulo que a fonte usa ("valor previsto da diária", "remuneração
  contratual").
- Não traz depoimento, usuário nem métrica de uso: nada disso existe, e nada é
  inventado.

## Acessibilidade

WCAG 2.1 AA como piso, conferido pelo axe a cada push. O grafo é desenhado em WebGL e
o leitor de tela não o alcança: a alternativa é a navegação em lista (a busca, as
tabelas e a página Parlamentares).

## O visual

O sistema visual (cores, tipografia, componentes e as regras de uso) está em
[`DESIGN.md`](../DESIGN.md).
