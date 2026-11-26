// Lighthouse CI: orçamento de desempenho, acessibilidade, boas práticas e SEO no
// site exportado (out/), servido como na Vercel por testes/servidor.mjs.
//
// Perfil de celular do Lighthouse (o padrão: CPU 4x e 4G lenta, simulados), que é
// onde a plataforma sofre. Três rodadas por página; vale a melhor de cada métrica
// (aggregationMethod "optimistic", o padrão), porque o runner compartilhado oscila.
//
// O orçamento começou no que o runner do GitHub (ubuntu-24.04) mediu em
// 26/11/2026, menos uma margem; a tabela medida está em docs/ci.md. Quando uma
// melhoria subir a nota, suba o piso aqui junto. Quando uma mudança pesar de
// propósito (o sigma no pacote inicial, por exemplo), suba o teto no mesmo PR e
// diga por quê.
//
// O relatório fica em arquivo (upload.target "filesystem") e vai como artefato do
// workflow. Nunca use "temporary-public-storage": ele publica o relatório num link
// aberto.

const PAGINAS = {
  inicio: "/",
  partidos: "/partidos/",
  parlamentares: "/parlamentares/",
  deputada: "/parlamentares/dep-220704/",
  dados: "/como-os-dados-chegam-aqui/",
  sobre: "/sobre/",
};
const BASE = "http://127.0.0.1:3107";

// pisos comuns a todas as páginas (medido depois do conserto de acessibilidade,
// #2: acessibilidade, boas práticas e SEO 100 em todas; CLS de 0 a 0,038)
const comum = {
  "categories:accessibility": ["error", { minScore: 0.98 }],
  "categories:best-practices": ["error", { minScore: 0.95 }],
  "categories:seo": ["error", { minScore: 0.95 }],
  "cumulative-layout-shift": ["error", { maxNumericValue: 0.1 }],
};

module.exports = {
  ci: {
    collect: {
      startServerCommand: "node testes/servidor.mjs",
      startServerReadyPattern: "out/ em",
      url: Object.values(PAGINAS).map((p) => BASE + p),
      numberOfRuns: 3,
      settings: { chromeFlags: "--no-sandbox --headless=new" },
    },
    assert: {
      assertMatrix: [
        {
          // o grafo: a página mais pesada (JSON de 777 KB, sigma e WebGL)
          matchingUrlPattern: "^http://127\\.0\\.0\\.1:3107/$",
          // medido: desempenho de 70 a 90, TBT de 399 ms a 4,4 s (uma rodada fora da
          // curva), LCP de 755 a 873 ms, 183 KB de JS
          assertions: {
            ...comum,
            "categories:performance": ["error", { minScore: 0.75 }],
            "total-blocking-time": ["error", { maxNumericValue: 1200 }],
            "largest-contentful-paint": ["error", { maxNumericValue: 1500 }],
            "resource-summary:script:size": ["error", { maxNumericValue: 215000 }],
          },
        },
        {
          matchingUrlPattern: "^http://127\\.0\\.0\\.1:3107/.+",
          // medido: desempenho 100, TBT 36 a 61 ms, LCP 752 a 904 ms, 145 a 149 KB de JS
          assertions: {
            ...comum,
            "categories:performance": ["error", { minScore: 0.9 }],
            "total-blocking-time": ["error", { maxNumericValue: 300 }],
            "largest-contentful-paint": ["error", { maxNumericValue: 1500 }],
            "resource-summary:script:size": ["error", { maxNumericValue: 175000 }],
          },
        },
      ],
    },
    upload: {
      target: "filesystem",
      outputDir: "testes/lighthouse",
    },
  },
};
