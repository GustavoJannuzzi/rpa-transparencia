/** O que o canvas do grafo e a imagem estática dele (gerada no build) têm em comum:
 * o formato dos dados, o tamanho e a cor de cada ponto e de cada linha. */
import { ABA_DEMAIS, paletaPartidos } from "./cores";

export type Vista = "brasil" | "parana";
export const VISTAS: Vista[] = ["brasil", "parana"];

export type No = { id: string; rotulo: string; partido: string | null; uf?: string; grau?: number; tipo?: string; total?: string; x: number; y: number };
export type Aresta = { a: string; b: string; peso?: number; atual?: boolean; periodo?: string; base?: string; f?: number[] };
export type DadosGrafo = { nos: No[]; arestas: Aresta[]; partidos: string[]; regra: string; regra_tecnica?: string; fornecedores_em?: string };

/** Como o `publicar` grava: Brasil com ligações compactas ([a, b, peso, [fornecedores]]), Paraná com objetos. */
type Bruto = Omit<DadosGrafo, "arestas"> & { arestas: (Aresta | [number, number, number, number[]])[] };

export function normalizar(d: Bruto): DadosGrafo {
  return {
    ...d,
    arestas: d.arestas.map((a) => (Array.isArray(a) ? { a: d.nos[a[0]].id, b: d.nos[a[1]].id, peso: a[2], f: a[3] } : a)),
  };
}

export const APAGADO = "#2b3532";
export const COR_PARTIDO = "#d8c79f";

/** Partido → aba de cor, pela ordem de quem mais aparece na vista (nunca a cor oficial). */
export function coresDaVista(d: DadosGrafo) {
  const cont = new Map<string, number>();
  d.nos.forEach((n) => n.partido && n.tipo !== "partido" && cont.set(n.partido, (cont.get(n.partido) ?? 0) + 1));
  return {
    cores: paletaPartidos(cont),
    legenda: [...cont.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])),
  };
}

/** Na vista Brasil, quem não divide fornecedor com ninguém fica só na lista. */
export const entraNoGrafo = (vista: Vista, n: No) => !(vista === "brasil" && !n.grau);

export function tamanhoDoNo(vista: Vista, n: No, escala = 1) {
  const t = n.tipo === "partido" ? 7 : vista === "brasil" ? 2.4 + Math.min(n.grau ?? 0, 60) / 16 : n.tipo === "deputado" ? 5.5 : 4;
  return t * escala;
}

export function corDoNo(n: No, cores: Map<string, string>) {
  return n.tipo === "partido" ? COR_PARTIDO : (n.partido && cores.get(n.partido)) || ABA_DEMAIS;
}

export function tamanhoDaAresta(vista: Vista, a: Aresta) {
  return vista === "brasil" ? 0.25 + Math.min(a.peso ?? 1, 30) / 40 : a.atual ? 0.9 : 0.5;
}

// cores opacas e escuras: o sigma não mistura transparência, e linha clara cruzada vira mancha
export function corDaAresta(vista: Vista, a: Aresta) {
  return vista === "brasil" ? "#34403c" : a.atual ? "#6e6650" : "#3d3b33";
}

/** Abaixo de 640 px o ponto precisa ser menor, senão a rede vira uma bola só. */
export const escalaDoNo = (largura: number) => (largura < 640 ? 0.55 : 1);
