import { readFileSync } from "node:fs";
import path from "node:path";
import { normalizar, type DadosGrafo, type Vista } from "./grafo";
import type { Casa, Cobertura, Fontes, ItemIndice, ItemPartido, Mapa, Parlamentar, Partido, ResumoCasa, Revisao } from "./tipos";

const PASTA = path.join(process.cwd(), "public", "dados");

function ler<T>(rel: string): T {
  return JSON.parse(readFileSync(path.join(PASTA, rel), "utf-8")) as T;
}

export const indice = () => ler<ItemIndice[]>("parlamentares.json");
export const partidos = () => ler<ItemPartido[]>("partidos.json");
export const partido = (slug: string) => ler<Partido>(path.join("partidos", `${slug}.json`));
export const parlamentar = (id: string) => ler<Parlamentar>(path.join("parlamentares", `${id}.json`));
export const fontes = () => ler<Fontes>("fontes.json");
export const revisao = () => ler<Revisao>("revisao.json");
export const categorias = () => ler<Record<string, string>>("categorias.json");
export const casas = () => ler<ResumoCasa[]>("casas.json");
export const casa = (id: string) => ler<Casa>(path.join("casas", `${id}.json`));
export const cobertura = () => ler<Cobertura>("cobertura.json");
export const mapa = (nome: "pr" | "br") => ler<Mapa>(`mapa-${nome}.json`);

/** A casa de um parlamentar, pelo id (lida uma vez por build). */
let _casas: Map<string, ResumoCasa> | null = null;
export function casaDe(id: string): ResumoCasa | undefined {
  _casas ??= new Map(casas().map((c) => [c.id, c]));
  return _casas.get(id);
}

const grafos = new Map<Vista, DadosGrafo>();
/** O grafo de uma vista, lido uma vez por build. */
export function grafo(vista: Vista): DadosGrafo {
  if (!grafos.has(vista)) grafos.set(vista, normalizar(ler(`grafo-${vista}.json`)));
  return grafos.get(vista)!;
}

/** Em que vista do grafo cada parlamentar aparece (para o link "ver no grafo"). */
export function vistaNoGrafo(id: string): Vista | null {
  if (grafo("brasil").nos.some((n) => n.id === id && n.grau)) return "brasil";
  if (grafo("parana").nos.some((n) => n.id === id)) return "parana";
  return null;
}

/** A data da coleta mais recente entre as fontes (não a data em que os JSON foram gerados). */
export function dataDaColeta(): string {
  return fontes()
    .fontes.map((f) => f.ultima_coleta?.fim?.slice(0, 10) ?? "")
    .filter(Boolean)
    .sort()
    .at(-1) as string;
}
