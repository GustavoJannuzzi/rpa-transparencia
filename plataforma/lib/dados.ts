import { readFileSync } from "node:fs";
import path from "node:path";
import { normalizar, type DadosGrafo, type Vista } from "./grafo";
import type { Fontes, ItemIndice, ItemPartido, Parlamentar, Partido, Revisao } from "./tipos";

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
