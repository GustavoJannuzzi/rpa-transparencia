// Serve a pasta out/ do jeito que a Vercel serve o export estático, para os testes
// de navegador (axe, prints e Lighthouse) rodarem contra o mesmo HTML que vai ao ar:
// - /rota/ devolve rota/index.html, e /rota sem a barra redireciona para /rota/
//   (trailingSlash: true no next.config.ts);
// - endereço que não existe devolve 404.html com status 404;
// - texto vai com gzip, como na Vercel, para o Lighthouse não medir um site sem compressão.
// Uso: node testes/servidor.mjs   (porta 3107, ou PORTA=…)
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { gzipSync } from "node:zlib";

const OUT = path.resolve(import.meta.dirname, "..", "out");
const PORTA = Number(process.env.PORTA ?? 3107);
const TIPOS = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".xml": "application/xml; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
};
const COMPRIME = new Set([".html", ".js", ".css", ".json", ".txt", ".xml", ".svg"]);
const comprimidos = new Map();

async function arquivo(p) {
  try {
    const s = await stat(p);
    return s.isFile() ? p : null;
  } catch {
    return null;
  }
}

async function responder(req, res) {
  const url = new URL(req.url ?? "/", "http://localhost");
  let rota;
  try {
    rota = decodeURIComponent(url.pathname);
  } catch {
    rota = "/";
  }
  const alvo = path.normalize(path.join(OUT, rota));
  if (alvo !== OUT && !alvo.startsWith(OUT + path.sep)) {
    res.writeHead(400).end();
    return;
  }
  let status = 200;
  let achado = rota.endsWith("/") ? await arquivo(path.join(alvo, "index.html")) : await arquivo(alvo);
  if (!achado && !rota.endsWith("/") && !path.extname(rota) && (await arquivo(path.join(alvo, "index.html")))) {
    res.writeHead(308, { Location: `${rota}/${url.search}` }).end();
    return;
  }
  if (!achado) {
    status = 404;
    achado = path.join(OUT, "404.html");
  }
  const ext = path.extname(achado);
  let corpo = await readFile(achado);
  const cabecalhos = { "Content-Type": TIPOS[ext] ?? "application/octet-stream", "Cache-Control": "no-cache" };
  if (COMPRIME.has(ext) && /\bgzip\b/.test(req.headers["accept-encoding"] ?? "")) {
    if (!comprimidos.has(achado)) comprimidos.set(achado, gzipSync(corpo));
    corpo = comprimidos.get(achado);
    cabecalhos["Content-Encoding"] = "gzip";
    cabecalhos["Vary"] = "Accept-Encoding";
  }
  res.writeHead(status, { ...cabecalhos, "Content-Length": corpo.length });
  res.end(req.method === "HEAD" ? undefined : corpo);
}

createServer((req, res) => {
  responder(req, res).catch((e) => {
    console.error(e);
    if (!res.headersSent) res.writeHead(500);
    res.end();
  });
}).listen(PORTA, "127.0.0.1", () => console.log(`out/ em http://127.0.0.1:${PORTA}/`));
