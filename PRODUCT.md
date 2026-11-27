# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Next.js + TypeScript + Tailwind, exportação estática (`plataforma/`), dados nos JSON que o comando `publicar` da coleta gera. Grafo com sigma.js + graphology; o layout (ForceAtlas2) vem calculado nos dados. Decidido no plano do projeto.

## Users

- **Primário (confirmado): o cidadão curioso.** Chega para saber em quem votou, quanto um parlamentar gastou e com quem, e se os números são de confiança. Lê no celular ou no computador, sem conhecer sistemas de transparência.
- **Secundário:** quem avalia o trabalho técnico (RPA, migração de sistemas). Quer ver o robô trabalhando: de onde veio cada número, o que foi conferido e o que ficou para revisão.

## Product Purpose

Uma plataforma independente que junta despesas públicas de parlamentares vindas de sistemas que não conversam entre si — a Câmara de Curitiba em quatro sistemas (legado em PDF, Elotech, portal da Prefeitura, Betha), mais câmaras do PR no Elotech, as assembleias do DF, de MG e de SP, e a cota dos deputados federais pela API e pelos arquivos anuais — num modelo só, e mostra tudo num grafo que agrupa por partido e liga por fornecedor em comum. Sucesso: o visitante acha o parlamentar, entende o que está vendo e confia no número porque vê de onde ele veio.

## Positioning

Todo número tem procedência (fonte, data da coleta, documento oficial) e só vai para o ar o que passou na conferência; o que não fecha fica numa fila de revisão visível, em vez de ser chutado. A linha do tempo mostra o mesmo órgão espalhado em quatro fornecedores de sistema.

## Operating Context

- Os dados saem de um robô (`coleta/`) que roda na máquina e publica JSON estáticos; a plataforma não consulta nada ao vivo.
- Abertura confirmada: o grafo ocupa a tela, com a coleta (de onde vieram os dados) ao lado.

## Capabilities and Constraints

- Telas: grafo (Brasil por fornecedor em comum; Paraná por partido), partido, parlamentar (de qualquer casa), casa (assembleia ou câmara municipal), Cobertura (quais casas, em qual sistema, e por que as outras ficaram de fora), "Como os dados chegam aqui" (linha do tempo da cobertura de Curitiba, fontes, conferência e revisão) e Sobre.
- Casas: Câmara dos Deputados, as assembleias do DF, de MG e de SP, e 13 câmaras municipais do PR (Curitiba em quatro sistemas; as outras no Elotech). Um adaptador por fornecedor, configurado por entidade.
- Atividade nas sessões (outro tipo de dado, não despesa): presença registrada, ausência com o motivo da fonte e voto nominal por tipo, do SAPL (Interlegis) em 6 câmaras do PR, e a frequência mensal que a Câmara de Curitiba publica em PDF. Só contagem bruta com procedência; nunca taxa, ranking, cor de alerta ou palavra de acusação. O nome se liga a um vereador das fontes de despesa ou fica em revisão.
- Assessor e servidor aparecem só no agregado (custo do gabinete, diárias de servidores no total da Câmara), nunca pelo nome. Fornecedor pessoa física aparece com CPF mascarado e não entra no grafo.
- Partido de vereador é o da eleição do mandato (TSE); de deputado, o informado em cada linha da cota.
- Valores do Betha são "valor previsto da diária"; do gabinete, "remuneração contratual" (Betha) e "remuneração" (Elotech): sempre com o rótulo da fonte.

## Brand Commitments

- Independente e não oficial: sem brasão, sem identidade da Câmara, da Prefeitura nem do gov.br.
- Neutra: sem ranking de quem gasta mais com tom de acusação, sem adjetivo, sem vermelho de alerta. A tela do grafo diz que fornecedor em comum não insinua nada.
- Confirmado como errado: parecer portal oficial; tom de denúncia; dashboard genérico de BI; estética hacker/neon.
- Nome do produto: em aberto (nome provisório do repositório: `rpa-transparencia`).

## Evidence on Hand

Dados reais coletados em 25–26/11/2026 em `plataforma/public/dados/` e o relatório de conferência em `relatorio/conferencia.html`. Não existem depoimentos, usuários ou métricas de uso: nada disso pode ser inventado.

## Product Principles

1. Procedência antes de opinião: o número vem com a fonte, ou não aparece.
2. O que não se leu com certeza é mostrado como pendente, nunca escondido nem completado.
3. Neutralidade: o desenho descreve, não acusa.
4. O robô é o protagonista técnico; a plataforma é a vitrine que torna o trabalho dele legível para qualquer pessoa.

## Accessibility & Inclusion

WCAG 2.1 AA como piso. O grafo tem alternativa navegável em lista (busca e tabelas), porque WebGL não é acessível a leitor de tela.
