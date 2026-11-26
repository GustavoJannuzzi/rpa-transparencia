import Link from "next/link";
import { anosTexto, contagem, listaE } from "@/lib/formato";
import { FONTES } from "@/lib/fontes";
import { MOTIVO_LEIGO } from "@/lib/revisao";
import type { GrupoRevisao, Parlamentar } from "@/lib/tipos";

/** Carimbo de revisão sobre a gaveta: sépia clara, a mesma das notas "não somada". */
export function CarimboRevisao({ children = "EM REVISÃO" }: { children?: React.ReactNode }) {
  return (
    <span
      className="inline-block shrink-0 rounded-[3px] border-2 border-sepia-claro px-1.5 py-0.5 font-titulo text-[0.68rem] font-semibold leading-tight tracking-[0.08em] text-sepia-claro"
      style={{ transform: "rotate(-3deg)" }}
    >
      {children}
    </span>
  );
}

/** Junta os recortes iguais (mesma categoria) para a frase do cabeçalho. */
function porCategoria(grupos: GrupoRevisao[]) {
  const m = new Map<string, { anos: number[]; linhas: number }>();
  for (const g of grupos) {
    const atual = m.get(g.categoria) ?? { anos: [], linhas: 0 };
    atual.anos.push(...g.anos);
    atual.linhas += g.linhas;
    m.set(g.categoria, atual);
  }
  return [...m.entries()].sort((a, b) => b[1].linhas - a[1].linhas);
}

/** Anos de mandato do vereador, separados pelo que as fontes dizem de cada um. */
export function anosDoVereador(p: Parlamentar) {
  const mandato = p.anos_mandato ?? [];
  const emRevisao = new Set<number>([...(p.periodos_em_revisao ?? []).flatMap((x) => x.anos), ...p.em_revisao.flatMap((g) => g.anos)]);
  const comDiaria = new Set(p.anos);
  return {
    semFonte: mandato.filter((a) => a < 2013),
    semDiaria: mandato.filter((a) => a >= 2013 && !comDiaria.has(a) && !emRevisao.has(a)),
  };
}

/**
 * A linha logo abaixo do total: o que ficou fora desta soma e por quê.
 * O princípio é o do produto: o que não fecha aparece como pendente, nunca escondido.
 */
export function ForaDaSoma({ p }: { p: Parlamentar }) {
  const periodo = (p.periodos_em_revisao ?? []).filter((x) => x.anos.length);
  const fontesPeriodo = new Set(periodo.map((x) => x.fonte));
  // o ano inteiro em revisão engole as linhas daquela fonte: elas entram na contagem, não viram outro item
  const itens = [
    ...periodo.map((x) => `diárias de ${anosTexto(x.anos)} (${FONTES[x.fonte]?.curto ?? x.fonte})`),
    ...porCategoria(p.em_revisao.filter((g) => !fontesPeriodo.has(g.fonte))).map(([c, v]) => `${c} (${anosTexto(v.anos)})`),
  ];
  const linhas = p.em_revisao.reduce((s, g) => s + g.linhas, 0);
  const anos = p.casa === "cmc" ? anosDoVereador(p) : null;
  if (!itens.length && !(anos && (anos.semDiaria.length || anos.semFonte.length))) return null;

  return (
    <div className="space-y-2 text-[0.92rem] leading-relaxed text-tinta-2 md:col-span-2">
      {itens.length > 0 && (
        <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <CarimboRevisao />
          <span className="min-w-0 flex-1 basis-[28ch]">
            Fora desta soma, em revisão: {listaE(itens)}
            {linhas > 0 && (
              <>
                , <span className="num">{contagem(linhas, "despesa lida", "despesas lidas")}</span>
              </>
            )}
            .{" "}
            <a href="#em-revisao" className="whitespace-nowrap text-carimbo-claro underline">
              Por quê
            </a>
          </span>
        </p>
      )}
      {anos && anos.semDiaria.length > 0 && (
        <p className="text-tinta-3">Nenhuma diária nas fontes conferidas em {anosTexto(anos.semDiaria)}.</p>
      )}
      {anos && anos.semFonte.length > 0 && (
        <p className="text-tinta-3">{anosTexto(anos.semFonte)}: as fontes da Câmara não trazem diária por pessoa antes de 2013.</p>
      )}
    </div>
  );
}

/** A seção que explica cada recorte em revisão, com o caminho para a fila. */
export function SecaoEmRevisao({ p }: { p: Parlamentar }) {
  const periodo = (p.periodos_em_revisao ?? []).filter((x) => x.anos.length);
  if (!p.em_revisao.length && !periodo.length) return null;
  const fontesPeriodo = new Set(periodo.map((x) => x.fonte));
  const grupos = p.em_revisao.filter((g) => !fontesPeriodo.has(g.fonte));
  const fontes = [...new Set([...periodo.map((x) => x.fonte), ...p.em_revisao.map((g) => g.fonte)])];
  return (
    <section id="em-revisao" aria-labelledby="em-revisao-t" className="scroll-mt-6">
      <h2 id="em-revisao-t" className="font-titulo text-lg font-medium">
        Em revisão, fora da soma
      </h2>
      <p className="mt-1 text-sm text-tinta-3">
        O que o robô não leu com certeza não entra nos totais nem é completado. Fica aqui, contado, até alguém explicar a diferença.
      </p>
      <ul className="mt-3 space-y-3 text-sm">
        {periodo.map((x) => {
          const lidas = p.em_revisao.filter((g) => g.fonte === x.fonte).reduce((s, g) => s + g.linhas, 0);
          return (
            <li key={`${x.fonte}-periodo`} className="border-t border-aco pt-2.5">
              <p className="text-tinta">
                Diárias <span className="num text-tinta-3">· {anosTexto(x.anos)} · {FONTES[x.fonte]?.curto ?? x.fonte}</span>
              </p>
              <p className="mt-0.5 text-tinta-2">
                {MOTIVO_LEIGO[x.motivo] ?? MOTIVO_LEIGO.outro} O ano inteiro fica fora desta página
                {lidas > 0 ? <>, incluídas <span className="num">{contagem(lidas, "diária lida", "diárias lidas")}</span> com este nome</> : null}.
              </p>
            </li>
          );
        })}
        {grupos.map((g) => (
          <li key={`${g.fonte}-${g.motivo}-${g.categoria}`} className="border-t border-aco pt-2.5">
            <p className="text-tinta">
              {g.categoria} <span className="num text-tinta-3">· {anosTexto(g.anos)} · {contagem(g.linhas, "despesa", "despesas")}</span>
            </p>
            <p className="mt-0.5 text-tinta-2">{MOTIVO_LEIGO[g.motivo] ?? MOTIVO_LEIGO.outro}</p>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-sm">
        {fontes.map((f, i) => (
          <span key={f}>
            {i > 0 && " · "}
            <Link href={`/como-os-dados-chegam-aqui/#revisao-${f}`} className="text-carimbo-claro underline">
              Fila de revisão: {FONTES[f]?.curto ?? f}
            </Link>
          </span>
        ))}
      </p>
    </section>
  );
}
