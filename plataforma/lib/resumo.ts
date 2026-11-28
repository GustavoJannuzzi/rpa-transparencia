// O que a plataforma cobre, contado nos próprios dados no build: casa nova entra
// nos textos sem ninguém editar frase. Só para componente de servidor (lê arquivo).
import { casas, grafo } from "./dados";
import { listaE } from "./formato";

const ordemUf = (a: string, b: string) => a.localeCompare(b, "pt-BR");

/** As assembleias publicadas, pela UF: "AP, CE, DF, GO, MG, RN e SP". */
export function ufsDasAssembleias(): string[] {
  return casas()
    .filter((c) => c.tipo === "assembleia")
    .map((c) => c.uf)
    .sort(ordemUf);
}

/** Quantas câmaras municipais estão publicadas (Curitiba incluída). */
export function quantasCamaras(): number {
  return casas().filter((c) => c.tipo === "camara_municipal").length;
}

/** "deputados estaduais de AP, CE, DF, GO, MG, RN e SP" (o DF é distrital, e a frase diz). */
export function frasesDasAssembleias(): { ufs: string; texto: string } {
  const ufs = ufsDasAssembleias();
  const estaduais = ufs.filter((u) => u !== "DF");
  const texto = ufs.includes("DF")
    ? `deputados estaduais (${listaE(estaduais)}) e distritais (DF)`
    : `deputados estaduais (${listaE(estaduais)})`;
  return { ufs: listaE(ufs), texto };
}

/** O que cada grafo mostra, contado nos nós do próprio grafo (pode ser menos que a cobertura:
 * uma câmara sem vereador com partido conhecido não tem ponto no grafo). */
export function noGrafo(): { ufsBrasil: string; camarasParana: number } {
  const uf = new Map(casas().map((c) => [c.id, c.uf]));
  const ufs = [...new Set(grafo("brasil").nos.flatMap((n) => (n.casa && uf.get(n.casa) ? [uf.get(n.casa)!] : [])))].sort(ordemUf);
  const municipios = new Set(grafo("parana").nos.filter((n) => n.tipo === "vereador").map((n) => n.municipio ?? "Curitiba"));
  return { ufsBrasil: listaE(ufs), camarasParana: municipios.size };
}

/** O nome do sistema como se fala: "Portal da Transparência Betha" → "Betha";
 * "Portal da Transparência Govbr (Pronim)" → "Govbr Pronim". */
export function nomeCurtoDoSistema(sistema: string): string {
  return sistema.replace(/^Portal da Transparência\s+/, "").replace(/\s*\(([^)]*)\)$/, " $1");
}

/** As câmaras municipais além da de Curitiba, por sistema de despesas, com o modo de leitura:
 * [{ sistema: "Betha", modo: "robo", camaras: 13 }, …], da que tem mais câmaras para a que tem menos. */
export function camarasPorSistema(): { sistema: string; modo: string; camaras: number }[] {
  const grupos = new Map<string, { sistema: string; modo: string; ids: Set<string> }>();
  for (const c of casas()) {
    if (c.tipo !== "camara_municipal" || c.id === "cmc") continue;
    for (const s of c.sistemas) {
      const g = grupos.get(s.fornecedor) ?? { sistema: nomeCurtoDoSistema(s.sistema), modo: s.modo, ids: new Set<string>() };
      g.ids.add(c.id);
      grupos.set(s.fornecedor, g);
    }
  }
  return [...grupos.values()]
    .map((g) => ({ sistema: g.sistema, modo: g.modo, camaras: g.ids.size }))
    .sort((a, b) => b.camaras - a.camaras || a.sistema.localeCompare(b.sistema, "pt-BR"));
}

/** As assembleias publicadas, com o modo de leitura de cada uma, em ordem de UF. */
export function assembleias(): { nome: string; uf: string; modo: string }[] {
  return casas()
    .filter((c) => c.tipo === "assembleia")
    .map((c) => ({ nome: c.nome, uf: c.uf, modo: c.sistemas[0]?.modo ?? "" }))
    .sort((a, b) => a.uf.localeCompare(b.uf, "pt-BR"));
}
