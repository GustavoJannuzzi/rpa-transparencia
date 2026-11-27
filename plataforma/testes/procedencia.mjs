// Teste da plataforma: o build existe e todo número em reais tem procedência.
// - no HTML gerado, todo "R$" está dentro do componente Valor (data-fonte + data-coleta);
// - nos JSON publicados, toda linha aponta para uma coleta (fonte + data) e todo
//   total de parlamentar diz de quais fontes e de quando veio.
// Uso: npm run build && npm test
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import path from "node:path";

const RAIZ = path.resolve(import.meta.dirname, "..");
const OUT = path.join(RAIZ, "out");
const DADOS = path.join(RAIZ, "public", "dados");
const falhas = [];
let paginas = 0;
let valores = 0;

function arquivos(dir, ext) {
  const out = [];
  for (const nome of readdirSync(dir)) {
    const p = path.join(dir, nome);
    if (statSync(p).isDirectory()) out.push(...arquivos(p, ext));
    else if (p.endsWith(ext)) out.push(p);
  }
  return out;
}

if (!existsSync(path.join(OUT, "index.html"))) {
  console.error("sem build: rode `npm run build` antes");
  process.exit(1);
}

// 1. HTML: cada R$ dentro de um <button class="valor ..." data-fonte="..." data-coleta="...">
for (const arq of arquivos(OUT, ".html")) {
  // o relatório da coleta tem a sua própria procedência por linha
  if (arq.endsWith("conferencia.html") || arq.endsWith(path.join("conferencia", "index.html"))) continue;
  paginas++;
  const html = readFileSync(arq, "utf-8").replace(/<script[\s\S]*?<\/script>/g, "");
  let i = html.indexOf("R$");
  while (i !== -1) {
    valores++;
    const abre = html.lastIndexOf("<button", i);
    const fecha = html.lastIndexOf("</button>", i);
    const tag = abre === -1 ? "" : html.slice(abre, html.indexOf(">", abre) + 1);
    const ok =
      abre > fecha &&
      /class="[^"]*\bvalor\b/.test(tag) &&
      /data-fonte="[a-z_ ]+"/.test(tag) &&
      /data-coleta="\d{4}-\d{2}-\d{2}"/.test(tag);
    if (!ok) falhas.push(`${path.relative(OUT, arq)}: "R$" sem procedência perto de …${html.slice(Math.max(0, i - 60), i + 20).replace(/\s+/g, " ")}…`);
    i = html.indexOf("R$", i + 2);
  }
}

// 2. JSON: linhas com coleta, cabeçalhos com fontes e data
let linhas = 0;
for (const arq of readdirSync(path.join(DADOS, "parlamentares"))) {
  const p = path.join(DADOS, "parlamentares", arq);
  if (statSync(p).isDirectory()) {
    for (const ano of readdirSync(p)) {
      const j = JSON.parse(readFileSync(path.join(p, ano), "utf-8"));
      for (const l of j.linhas) {
        linhas++;
        const c = j.coletas[l[5]];
        if (!c || !c.fonte || !/^\d{4}-\d{2}-\d{2}$/.test(c.coletado_em)) falhas.push(`${arq}/${ano}: linha sem coleta`);
        if (!/^-?\d+\.\d{2,}$/.test(l[3])) falhas.push(`${arq}/${ano}: valor fora do formato exato: ${l[3]}`);
      }
    }
  } else {
    const j = JSON.parse(readFileSync(p, "utf-8"));
    for (const f of j.fontes) if (!j.p?.coleta?.[f]) falhas.push(`${arq}: fonte ${f} sem data de coleta`);
  }
}

// 3. casas: o resumo de cada casa diz de quais fontes e de quando veio
let casas = 0;
if (existsSync(path.join(DADOS, "casas"))) {
  for (const arq of readdirSync(path.join(DADOS, "casas"))) {
    casas++;
    const j = JSON.parse(readFileSync(path.join(DADOS, "casas", arq), "utf-8"));
    if (!j.p?.fontes?.length || !/^\d{4}-\d{2}-\d{2}$/.test(j.p.coleta ?? "")) falhas.push(`casas/${arq}: sem fonte ou sem data de coleta`);
    if (j.linhas > 0 && !j.sistemas?.length) falhas.push(`casas/${arq}: linhas publicadas sem o sistema de onde vieram`);
  }
}

// 4. atividade nas sessões: cada bloco diz de qual fonte, de quando e onde conferir
let atividades = 0;
for (const arq of readdirSync(path.join(DADOS, "parlamentares"))) {
  const p = path.join(DADOS, "parlamentares", arq);
  if (statSync(p).isDirectory()) continue;
  for (const a of JSON.parse(readFileSync(p, "utf-8")).atividade ?? []) {
    atividades++;
    if (!/^[a-z_]+$/.test(a.fonte ?? "") || !/^\d{4}-\d{2}-\d{2}$/.test(a.coleta ?? "") || !/^https:\/\//.test(a.documento ?? ""))
      falhas.push(`${arq}: atividade sem fonte, sem data de coleta ou sem documento`);
  }
}

if (falhas.length) {
  console.error(`${falhas.length} falha(s):`);
  for (const f of falhas.slice(0, 30)) console.error("  " + f);
  process.exit(1);
}
console.log(
  `ok: ${paginas} páginas, ${valores} valores em reais no HTML, ${linhas} linhas de despesa nos JSON, ${casas} casas e ${atividades} blocos de atividade, todos com procedência`,
);
