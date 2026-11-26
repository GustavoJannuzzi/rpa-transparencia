// axe-core em cada tela de estados.ts: regras WCAG 2.0, 2.1 e 2.2 (A e AA) e as
// de boas práticas. O axe pega só uma parte dos problemas; o grafo é <canvas> e
// o axe não enxerga os pontos (a alternativa de teclado é a lista).
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { EXCECOES } from "./axe-excecoes";
import { ESTADOS, abrir } from "./estados";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"];

// a lista do grafo tem milhares de linhas, e o axe confere cada uma
test.describe.configure({ timeout: 120_000 });

for (const estado of ESTADOS) {
  test(`axe: ${estado.nome}`, async ({ page }, info) => {
    await abrir(page, estado);
    const valeAqui = (e: (typeof EXCECOES)[number]) => e.telas.includes(estado.nome) && (!e.projetos || e.projetos.includes(info.project.name));
    const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze();

    const usadas = new Set<number>();
    const sobra: string[] = [];
    for (const v of violations) {
      for (const no of v.nodes) {
        const i = EXCECOES.findIndex((e) => e.regra === v.id && valeAqui(e) && e.html.test(no.html));
        if (i >= 0) usadas.add(i);
        else sobra.push(`${v.id} (${v.impact}): ${no.target.join(" ")}\n    ${no.html.slice(0, 160)}\n    ${no.failureSummary?.split("\n").slice(0, 2).join(" ")}`);
      }
    }
    const esquecidas = EXCECOES.flatMap((e, i) =>
      valeAqui(e) && !usadas.has(i) ? [`${e.regra} em "${estado.nome}" já não aparece: apague a exceção em testes/e2e/axe-excecoes.ts`] : [],
    );

    expect(sobra, `violações do axe em ${estado.rota}`).toEqual([]);
    expect(esquecidas, "exceções que não cobrem mais nada").toEqual([]);
  });
}
