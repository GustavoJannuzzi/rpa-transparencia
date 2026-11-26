/** Abas de fichário para os partidos. Tons apagados, atribuídos pela ordem dos
 * partidos que mais aparecem na vista; nunca a cor oficial de partido nenhum. O
 * violeta fica de fora: é a tinta do carimbo e do foco. */
export const ABAS = [
  "#c9a24a",
  "#5e9c8f",
  "#b07aa1",
  "#7f9fd1",
  "#d38a5c",
  "#a3b86c",
  "#8fb4c9",
  "#d1b48c",
  "#7fae8a",
  "#c99a9a",
];
export const ABA_DEMAIS = "#6f7a75";

export function paletaPartidos(contagem: Map<string, number>): Map<string, string> {
  const ordem = [...contagem.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const m = new Map<string, string>();
  ordem.forEach(([sigla], i) => m.set(sigla, i < ABAS.length ? ABAS[i] : ABA_DEMAIS));
  return m;
}
