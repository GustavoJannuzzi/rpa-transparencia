import { type Classe, classe } from "@/lib/cobertura";
import { cobertura, mapa } from "@/lib/dados";

/**
 * Os mapas da página Cobertura, desenhados no build como arquivo SVG: o PR por
 * município e o Brasil por UF, cada área com a cor da situação da casa. Como arquivo
 * à parte, o desenho (centenas de contornos) não pesa no HTML da página, que só o
 * carrega como imagem quando ele chega perto da tela.
 */
export const dynamic = "force-static";
export const dynamicParams = false;

export function generateStaticParams() {
  return [{ arquivo: "pr.svg" }, { arquivo: "br.svg" }];
}

// as cores do DESIGN.md (globals.css), escritas por extenso: a imagem não enxerga as variáveis da página
const COR = {
  manilha: "#d8c79f",
  gaveta: "#1b2220",
  gaveta2: "#212a27",
  gaveta3: "#27312e",
  aco: "#2f3a36",
  aco2: "#3c4844",
  contorno: "#6f7a75",
  sepiaClaro: "#cdb274",
};

const PREENCHE: Record<Classe, string> = {
  coletada: COR.manilha,
  em_revisao: "url(#r)",
  barrada: "url(#b)",
  sem_adaptador: COR.aco2,
  nao_identificado: COR.gaveta2,
  outra: COR.gaveta3,
};

export async function GET(_: Request, { params }: { params: Promise<{ arquivo: string }> }) {
  const { arquivo } = await params;
  const qual = arquivo === "br.svg" ? "br" : "pr";
  const m = mapa(qual);
  const cob = cobertura();
  const classes = new Map<string, Classe>(
    qual === "pr"
      ? cob.camaras_pr.map((c) => [String(c.ibge), classe(c.situacao, c.motivo)])
      : cob.assembleias.map((a) => [a.uf, classe(a.situacao, a.motivo)]),
  );
  // um <path> por situação: o desenho fica pequeno e a casa coletada vai por cima, com o filete escuro
  const porClasse = new Map<Classe, string[]>();
  for (const a of m.areas) {
    const c = classes.get(String(a.id)) ?? "outra";
    porClasse.set(c, [...(porClasse.get(c) ?? []), a.d]);
  }
  const ordem: Classe[] = ["nao_identificado", "outra", "sem_adaptador", "barrada", "em_revisao", "coletada"];
  const caminhos = ordem
    .filter((c) => porClasse.has(c))
    .map((c) => {
      const coletada = c === "coletada";
      return `<path d="${porClasse.get(c)!.join("")}" fill="${PREENCHE[c]}" stroke="${coletada ? COR.gaveta : COR.aco}" stroke-width="${coletada ? 1.2 : 0.6}" stroke-linejoin="round"/>`;
    })
    .join("");
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${m.viewBox}">` +
    `<defs><pattern id="r" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="5" height="5" fill="${COR.gaveta3}"/><line x1="0" y1="0" x2="0" y2="5" stroke="${COR.sepiaClaro}" stroke-width="2.2"/></pattern>` +
    `<pattern id="b" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)"><rect width="5" height="5" fill="${COR.gaveta3}"/><line x1="0" y1="0" x2="0" y2="5" stroke="${COR.contorno}" stroke-width="1.4"/></pattern></defs>` +
    caminhos +
    `</svg>`;
  return new Response(svg, { headers: { "Content-Type": "image/svg+xml" } });
}
