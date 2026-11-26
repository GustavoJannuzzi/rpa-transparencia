import { grafo } from "@/lib/dados";
import { corDaAresta, corDoNo, coresDaVista, entraNoGrafo, escalaDoNo, tamanhoDaAresta, tamanhoDoNo, VISTAS, type Vista } from "@/lib/grafo";

/**
 * O grafo desenhado como imagem no build, com o mesmo layout, as mesmas cores e
 * os mesmos tamanhos do canvas. Aparece enquanto o canvas carrega (no celular,
 * de 2 a 9 segundos) e some quando ele fica pronto.
 */
export const dynamic = "force-static";
export const dynamicParams = false;

export function generateStaticParams() {
  return VISTAS.map((v) => ({ arquivo: `${v}.svg` }));
}

// largura típica do quadro em cada vista: o celular abre no Paraná, o computador no Brasil
const LARGURA_TIPICA: Record<Vista, number> = { brasil: 860, parana: 343 };

const r1 = (n: number) => Math.round(n * 10) / 10;

export async function GET(_: Request, { params }: { params: Promise<{ arquivo: string }> }) {
  const { arquivo } = await params;
  const vista = arquivo.replace(/\.svg$/, "") as Vista;
  const d = grafo(vista);
  const { cores } = coresDaVista(d);
  const nos = d.nos.filter((n) => entraNoGrafo(vista, n));
  const pos = new Map(nos.map((n) => [n.id, n]));
  const xs = nos.map((n) => n.x);
  const ys = nos.map((n) => n.y);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const largura = x1 - x0 || 1;
  // um pixel da tela, em unidades do desenho, na largura típica do quadro
  const px = largura / LARGURA_TIPICA[vista];
  const escala = escalaDoNo(LARGURA_TIPICA[vista]);
  const margem = 8 * px;

  // linhas: um <path> por cor e espessura
  const linhas = new Map<string, string[]>();
  for (const a of d.arestas) {
    const pa = pos.get(a.a);
    const pb = pos.get(a.b);
    if (!pa || !pb) continue;
    const chave = `${corDaAresta(vista, a)}|${r1(tamanhoDaAresta(vista, a))}`;
    linhas.set(chave, [...(linhas.get(chave) ?? []), `M${r1(pa.x)} ${r1(pa.y)}L${r1(pb.x)} ${r1(pb.y)}`]);
  }
  // pontos: um <g> por cor; partidos por cima
  const pontos = new Map<string, string[]>();
  for (const n of [...nos].sort((a, b) => Number(a.tipo === "partido") - Number(b.tipo === "partido"))) {
    const cor = corDoNo(n, cores);
    pontos.set(cor, [...(pontos.get(cor) ?? []), `<circle cx="${r1(n.x)}" cy="${r1(n.y)}" r="${r1(tamanhoDoNo(vista, n, escala) * px)}"/>`]);
  }
  const svg = [
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${r1(x0 - margem)} ${r1(y0 - margem)} ${r1(largura + 2 * margem)} ${r1(y1 - y0 + 2 * margem)}" preserveAspectRatio="xMidYMid meet">`,
    ...[...linhas.entries()].map(([chave, ds]) => {
      const [cor, w] = chave.split("|");
      return `<path fill="none" stroke="${cor}" stroke-width="${w}" vector-effect="non-scaling-stroke" d="${ds.join("")}"/>`;
    }),
    ...[...pontos.entries()].map(([cor, cs]) => `<g fill="${cor}">${cs.join("")}</g>`),
    "</svg>",
  ].join("");
  return new Response(svg, { headers: { "Content-Type": "image/svg+xml; charset=utf-8" } });
}
