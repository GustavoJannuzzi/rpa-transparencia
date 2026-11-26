import type { Metadata } from "next";
import Link from "next/link";
import Barras, { type ItemBarra } from "@/componentes/Barras";
import Valor from "@/componentes/Valor";
import { categorias, dataDaColeta, partido, partidos } from "@/lib/dados";
import { mes, ondeCurto, proporcao, tipoDaCasa } from "@/lib/formato";
import { metadadosDaPagina } from "@/lib/site";
import type { Procedencia } from "@/lib/tipos";

/** Fontes de vereador: o partido vem do TSE (eleição do mandato). */
const partidoDoTse = (f: string) => f.startsWith("cmc_") || f.startsWith("elotech_");

export const dynamicParams = false;

export function generateStaticParams() {
  return partidos().map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const p = partido(slug);
  return metadadosDaPagina({
    title: p.sigla,
    description: `Despesas conferidas dos parlamentares do ${p.sigla} no mês em que estavam no partido, com a fonte de cada número.`,
    caminho: `/partidos/${slug}/`,
  });
}

export default async function PaginaPartido({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const p = partido(slug);
  const rot = categorias();
  // as fontes que de fato entraram na soma (o partido de vereador vem do TSE)
  const fontesUsadas = [...p.fontes, ...(p.fontes.some(partidoDoTse) ? ["tse"] : [])];
  const coleta = Object.values(p.coleta).sort().at(-1) ?? dataDaColeta();
  const proc: Procedencia = { fontes: fontesUsadas, coleta, situacao: "soma", nota: p.regra };
  const recorte = (r: { fontes: string[]; linhas: number } | undefined): Procedencia => {
    const fs = r?.fontes ?? p.fontes;
    return {
      fontes: [...fs, ...(fs.some(partidoDoTse) ? ["tse"] : [])],
      coleta: fs.map((f) => p.coleta[f] ?? "").sort().at(-1) ?? coleta,
      situacao: "soma",
      linhas: r?.linhas,
      nota: p.regra,
    };
  };
  const meses = Object.entries(p.por_mes);
  // eixo de tempo de verdade: todo mês entre o primeiro e o último, os vazios com zero
  const eixo: string[] = [];
  if (meses.length) {
    let [a, m] = meses[0][0].split("-").map(Number);
    const [af, mf] = meses[meses.length - 1][0].split("-").map(Number);
    while (a < af || (a === af && m <= mf)) {
      eixo.push(`${a}-${String(m).padStart(2, "0")}`);
      m += 1;
      if (m > 12) {
        m = 1;
        a += 1;
      }
    }
  }
  const maxMes = meses.reduce((m, [, v]) => (Number(v) > Number(m) ? v : m), "0");
  const cats: ItemBarra[] = Object.entries(p.por_categoria).map(([k, v]) => ({ chave: k, valor: v, p: recorte(p.procedencia_categoria?.[k]) }));
  const federais = p.membros.filter((m) => tipoDaCasa(m.casa) === "federal");
  const estaduais = p.membros.filter((m) => tipoDaCasa(m.casa) === "estadual");
  const municipais = p.membros.filter((m) => tipoDaCasa(m.casa) === "municipal");

  return (
    <article className="mx-auto max-w-[1180px] px-4 py-8 sm:px-8 sm:py-10">
      <p className="text-sm text-tinta-3">
        <Link href="/partidos/" className="underline hover:text-tinta">
          Partidos
        </Link>
      </p>
      <header className="mt-3 grid gap-6 border-b border-aco pb-8 md:grid-cols-[1fr_auto] md:items-end">
        <div>
          <h1 className="font-titulo text-[3rem] font-medium leading-none tracking-[-0.02em] sm:text-[4rem]">{p.sigla}</h1>
          <p className="mt-3 text-tinta-2">
            {federais.length} deputado(s) federal(is) · {estaduais.length} deputado(s) estadual(is) · {municipais.length} vereador(es)
          </p>
        </div>
        {Number(p.total) !== 0 && (
          <div className="md:text-right">
            <p className="text-sm text-tinta-3">Despesas conferidas de quem estava no partido</p>
            <Valor valor={p.total} p={proc} tamanho="grande" />
          </div>
        )}
      </header>
      <p className="mt-4 max-w-[75ch] text-sm text-tinta-3">{p.regra}.</p>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-12 py-8 lg:grid-cols-2">
        <section aria-labelledby="por-cat" className="min-w-0">
          <h2 id="por-cat" className="font-titulo text-xl font-medium">
            Por categoria
          </h2>
          <div className="mt-4">
            {Object.keys(p.por_categoria).length ? (
              <Barras itens={cats} rotulos={rot} />
            ) : (
              <p className="text-tinta-3">Nenhuma despesa conferida no período.</p>
            )}
          </div>
        </section>
        <section aria-labelledby="por-mes" className="min-w-0">
          <h2 id="por-mes" className="font-titulo text-xl font-medium">
            Por mês
          </h2>
          {meses.length ? (
            <>
              <div className="mt-4 flex h-40 items-end gap-px border-b border-aco-2" aria-hidden="true">
                {eixo.map((m) => {
                  const v = p.por_mes[m];
                  return (
                    <span
                      key={m}
                      className={`flex-1 ${v ? "bg-manilha/75" : ""} ${m.endsWith("-01") ? "border-l border-aco-2" : ""}`}
                      style={{ height: v ? `${Math.max(1.5, proporcao(v, maxMes) * 100)}%` : "100%" }}
                      title={m}
                    />
                  );
                })}
              </div>
              <div className="num relative mt-1 h-4 text-xs text-tinta-3">
                {eixo.map((m, i) =>
                  m.endsWith("-01") || i === 0 ? (
                    <span key={m} className="absolute" style={{ left: `${(i / eixo.length) * 100}%` }}>
                      {m.slice(0, 4)}
                    </span>
                  ) : null,
                )}
              </div>
              <p className="mt-2 text-xs text-tinta-3">
                Mês sem barra: nenhuma despesa conferida do partido naquele mês nas fontes cobertas (a cota federal começa em 2023;
                as diárias de Curitiba, em 2013).
              </p>
              <details className="mt-4">
                <summary className="cursor-pointer text-sm text-tinta-2">Ver os valores de cada mês</summary>
                <ul className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
                  {meses.map(([m, v]) => (
                    <li key={m} className="flex justify-between gap-2 border-t border-aco pt-1">
                      <span className="num text-tinta-3">{mes(m)}</span>
                      <Valor valor={v} p={recorte(p.procedencia_mes?.[m])} />
                    </li>
                  ))}
                </ul>
              </details>
            </>
          ) : (
            <p className="mt-4 text-tinta-3">Nenhuma despesa conferida no período.</p>
          )}
        </section>
      </div>

      <section aria-labelledby="membros" className="border-t border-aco pt-8">
        <h2 id="membros" className="font-titulo text-xl font-medium">
          Parlamentares do partido
        </h2>
        <ul className="mt-4 columns-1 gap-8 sm:columns-2 lg:columns-3">
          {[...municipais, ...estaduais, ...federais].map((m) => (
            <li key={m.id} className="break-inside-avoid border-t border-aco py-1.5">
              <Link href={`/parlamentares/${m.id}/`} className="hover:text-carimbo-claro hover:underline">
                {m.nome}
              </Link>
              <span className="text-sm text-tinta-3"> · {ondeCurto(m)}</span>
            </li>
          ))}
        </ul>
      </section>
    </article>
  );
}
