// Tabela em markdown com o que o Lighthouse CI mediu (para o resumo do job no
// GitHub e para calibrar o orçamento em lighthouserc.js). Lê o manifest.json que o
// upload "filesystem" grava em testes/lighthouse/.
// Uso: node testes/resumo-lighthouse.mjs
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

const PASTA = path.resolve(import.meta.dirname, "lighthouse");
const manifesto = path.join(PASTA, "manifest.json");
if (!existsSync(manifesto)) {
  console.log("Sem relatório do Lighthouse (o lhci não chegou a gravar).");
  process.exit(0);
}

const rodadas = JSON.parse(readFileSync(manifesto, "utf-8"));
const porUrl = new Map();
for (const r of rodadas) {
  const lhr = JSON.parse(readFileSync(path.isAbsolute(r.jsonPath) ? r.jsonPath : path.join(PASTA, path.basename(r.jsonPath)), "utf-8"));
  const a = lhr.audits;
  const linha = {
    p: lhr.categories.performance.score,
    a: lhr.categories.accessibility.score,
    bp: lhr.categories["best-practices"].score,
    seo: lhr.categories.seo.score,
    lcp: a["largest-contentful-paint"].numericValue,
    tbt: a["total-blocking-time"].numericValue,
    cls: a["cumulative-layout-shift"].numericValue,
    js: a["resource-summary"]?.details?.items?.find((i) => i.resourceType === "script")?.transferSize,
  };
  const rota = new URL(r.url).pathname;
  if (!porUrl.has(rota)) porUrl.set(rota, []);
  porUrl.get(rota).push(linha);
}

const pct = (v) => Math.round(v * 100);
const faixa = (xs, f) => {
  const lo = Math.min(...xs), hi = Math.max(...xs);
  return lo === hi ? f(lo) : `${f(lo)}–${f(hi)}`;
};
console.log(`### Lighthouse (celular simulado, ${rodadas.length} rodadas)\n`);
console.log("| Página | Desempenho | Acessibilidade | Boas práticas | SEO | LCP (ms) | TBT (ms) | CLS | JS transferido (KB) |");
console.log("|---|---:|---:|---:|---:|---:|---:|---:|---:|");
for (const [rota, ls] of porUrl) {
  const col = (k, f) => faixa(ls.map((l) => l[k]), f);
  console.log(
    `| \`${rota}\` | ${col("p", pct)} | ${col("a", pct)} | ${col("bp", pct)} | ${col("seo", pct)} | ${col("lcp", Math.round)} | ${col("tbt", Math.round)} | ${col("cls", (v) => v.toFixed(3))} | ${col("js", (v) => Math.round(v / 1024))} |`,
  );
}
console.log("\nCada célula mostra a faixa entre as rodadas; o orçamento compara a melhor delas.");
