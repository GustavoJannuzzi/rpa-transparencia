/** Dinheiro a partir do texto exato que o robô publicou ("-2113.91", "1467",
 * "39800.30"). Nada passa por float: a formatação é feita no texto. */
export function reais(valor: string): string {
  const neg = valor.trim().startsWith("-");
  const limpo = valor.trim().replace(/^[-+]/, "");
  const [int, dec = ""] = limpo.split(".");
  const centavos = (dec + "00").slice(0, Math.max(2, dec.length));
  const milhar = int.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${neg ? "−" : ""}R$ ${milhar},${centavos}`;
}

/** Soma exata de valores em texto, em centavos inteiros (BigInt). */
export function somar(valores: string[]): string {
  let total = 0n;
  for (const v of valores) {
    const neg = v.trim().startsWith("-");
    const [i, d = ""] = v.trim().replace(/^[-+]/, "").split(".");
    const c = BigInt(i || "0") * 100n + BigInt((d + "00").slice(0, 2) || "0");
    if (d.length > 2 && /[1-9]/.test(d.slice(2))) throw new Error(`valor com mais de duas casas: ${v}`);
    total += neg ? -c : c;
  }
  const neg = total < 0n;
  const a = neg ? -total : total;
  return `${neg ? "-" : ""}${a / 100n}.${String(a % 100n).padStart(2, "0")}`;
}

/** Razão entre dois valores em texto, só para desenhar barras (nunca é exibida como número). */
export function proporcao(valor: string, maximo: string): number {
  const m = Number(maximo);
  if (!m) return 0;
  return Math.max(0, Math.min(1, Number(valor) / m));
}

export function inteiro(n: number | string): string {
  return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

export function data(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  if (!d) return `${m}/${a}`;
  return `${d}/${m}/${a}`;
}

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

export function mes(comp: string): string {
  const [a, m] = comp.split("-");
  return `${MESES[Number(m) - 1]}/${a.slice(2)}`;
}

export function casaNome(casa: string): string {
  return casa === "cmc" ? "Câmara Municipal de Curitiba" : "Câmara dos Deputados";
}

export function cargoNome(casa: string): string {
  return casa === "cmc" ? "Vereador(a) de Curitiba" : "Deputado(a) federal";
}
