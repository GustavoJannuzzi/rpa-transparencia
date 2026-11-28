import type { Metadata } from "next";
import Link from "next/link";
import { CarimboRevisao } from "@/componentes/EmRevisao";
import Valor from "@/componentes/Valor";
import { fontes, revisao } from "@/lib/dados";
import { FONTES, MODO } from "@/lib/fontes";
import { contagem, data, inteiro, listaE } from "@/lib/formato";
import { quantasCamaras, ufsDasAssembleias } from "@/lib/resumo";
import { motivoDaFila } from "@/lib/revisao";
import { metadadosDaPagina } from "@/lib/site";
import type { Fonte, GrupoFila } from "@/lib/tipos";

export const metadata: Metadata = metadadosDaPagina({
  title: "Como os dados chegam aqui",
  description: "Os quatro sistemas da Câmara de Curitiba, a API da Câmara dos Deputados, a conferência de cada fonte e a fila de revisão.",
  caminho: "/como-os-dados-chegam-aqui/",
});

const COR: Record<string, string> = {
  cmc_legado: "#c9a24a",
  cmc_elotech: "#5e9c8f",
  cmc_prefeitura: "#b07aa1",
  cmc_betha: "#7f9fd1",
};

const ROTULO_VERIFICACAO: Record<string, string> = {
  origem_igual_coletado_mais_revisao: "Origem = coletado + revisão",
  erros_em_aberto: "Erros em aberto no inventário",
  api_x_arquivo: "API × arquivo anual (amostra)",
  sinal_valor_liquido_api: "Sinal do valor líquido na API",
  parlamentares_x_lista_oficial: "Parlamentares × lista oficial",
  total_mensal_diarias: "Total do mês no PDF (diárias)",
  total_mensal_hospedagem: "Total do mês no PDF (hospedagem)",
  total_mensal_transporte: "Total do mês no PDF (transporte)",
  total_anual_diarias: "Total do ano no PDF (diárias)",
  total_anual_hospedagem: "Total do ano no PDF (hospedagem)",
  total_anual_transporte: "Total do ano no PDF (transporte)",
  fronteira_betha_2026: "Fronteira 2026: Prefeitura × Betha",
  fronteira_elotech: "Fronteira 2023: Elotech × Prefeitura",
  gabinetes_betha_x_elotech: "Gabinetes: Betha × Elotech",
  lista_de_vereadores: "Lista de vereadores",
  eleitos: "Eleitos no arquivo do TSE",
  ano_inteiro_x_mes_a_mes: "Consulta do ano inteiro × consulta mês a mês",
};

/** Nunca mostrar a chave crua: o que não tem rótulo vira texto legível. */
function rotuloVerificacao(v: string): string {
  return ROTULO_VERIFICACAO[v] ?? (v.charAt(0).toUpperCase() + v.slice(1)).replaceAll("_x_", " × ").replaceAll("_", " ");
}

/** Ordem das fontes na fila; "cmc" são as identidades da Câmara de Curitiba como um todo. */
const ORDEM_FILA = ["camara_deputados", "cmc_legado", "cmc_elotech", "cmc_prefeitura", "cmc_betha", "cmc", "tse"];
const NOME_FILA: Record<string, string> = { cmc: "Câmara de Curitiba (identidades)", tse: "TSE" };

const RESULTADO: Record<string, string> = {
  confere: "confere",
  confere_sem_marcadas: "confere sem as linhas devolvidas",
  diverge: "diverge",
  parcial: "parcial",
  observacao: "observação",
  sem_total_na_fonte: "a fonte não traz total",
};

function resumoConferencias(f: Fonte) {
  const grupos = new Map<string, Map<string, number>>();
  for (const c of f.conferencias) {
    const g = grupos.get(c.verificacao) ?? new Map<string, number>();
    g.set(c.resultado, (g.get(c.resultado) ?? 0) + 1);
    grupos.set(c.verificacao, g);
  }
  return [...grupos.entries()];
}

export default function ComoOsDadosChegam() {
  const f = fontes();
  const rev = revisao();
  const anoMin = 2010;
  const anoMax = 2026;
  const largura = (de: number, ate: number) => ((ate - de + 1) / (anoMax - anoMin + 1)) * 100;
  const inicio = (de: number) => ((de - anoMin) / (anoMax - anoMin + 1)) * 100;
  const ordem = ["camara_deputados", "cmc_legado", "cmc_elotech", "cmc_prefeitura", "cmc_betha", "tse"];
  const lista = ordem.map((id) => f.fontes.find((x) => x.id === id)).filter(Boolean) as Fonte[];
  const porFonte = new Map<string, GrupoFila[]>();
  for (const g of rev.grupos) porFonte.set(g.fonte, [...(porFonte.get(g.fonte) ?? []), g]);
  const fila = [...porFonte.entries()]
    .sort(([a], [b]) => (ORDEM_FILA.indexOf(a) + 99) % 99 - (ORDEM_FILA.indexOf(b) + 99) % 99 || a.localeCompare(b))
    .map(([fonte, grupos]) => ({
      fonte,
      grupos: [...grupos].sort((a, b) => b.linhas - a.linhas || b.n - a.n),
      linhas: grupos.reduce((s, g) => s + g.linhas, 0),
    }));
  const totalFila = fila.reduce((s, x) => s + x.linhas, 0);

  return (
    <article className="mx-auto max-w-[1180px] px-4 py-8 sm:px-8 sm:py-10">
      <h1 className="max-w-[20ch] font-titulo text-[2.4rem] font-medium leading-[1.04] tracking-[-0.02em] sm:text-[3.2rem]">
        Como os dados chegam aqui
      </h1>
      <p className="mt-4 max-w-[68ch] text-[1.05rem] leading-relaxed text-tinta-2">
        A Câmara Municipal de Curitiba trocou de sistema três vezes. O histórico das diárias está espalhado em quatro lugares,
        de quatro fornecedores, e só um deles tem API. Onde há API, a coleta usa a API; onde não há, um robô abre o portal como
        uma pessoa faria. Tudo vai para um modelo único, passa pela conferência e só então aparece aqui.
      </p>
      <p className="mt-3 max-w-[68ch] text-[0.95rem] leading-relaxed text-tinta-3">
        As outras casas (as assembleias legislativas de {listaE(ufsDasAssembleias())} e mais {quantasCamaras() - 1} câmaras do Paraná) usam o
        mesmo modelo e a mesma
        conferência. Que casas estão aqui, por qual sistema, e por que as outras ainda não estão:{" "}
        <Link href="/cobertura/" className="text-carimbo-claro underline">
          Cobertura
        </Link>
        .
      </p>
      <dl className="mt-8 grid max-w-[68rem] gap-x-8 gap-y-4 text-[0.95rem] leading-relaxed sm:grid-cols-3">
        <div className="border-t border-aco pt-3">
          <dt className="font-titulo font-semibold text-tinta">Conferido</dt>
          <dd className="mt-1 text-tinta-2">A soma das linhas bateu com o total que o próprio órgão publica, ou com uma segunda leitura da mesma fonte.</dd>
        </div>
        <div className="border-t border-aco pt-3">
          <dt className="font-titulo font-semibold text-tinta">Em revisão</dt>
          <dd className="mt-1 text-tinta-2">O robô não teve certeza. O número fica fora dos totais, contado na fila de revisão, até alguém explicar a diferença.</dd>
        </div>
        <div className="border-t border-aco pt-3">
          <dt className="font-titulo font-semibold text-tinta">Procedência</dt>
          <dd className="mt-1 text-tinta-2">De onde veio cada número: o sistema, a data em que o robô leu e o link do documento oficial. Clique em qualquer valor para ver.</dd>
        </div>
      </dl>

      <section aria-labelledby="linha" className="mt-12">
        <h2 id="linha" className="font-titulo text-2xl font-medium">
          A linha do tempo da Câmara de Curitiba
        </h2>
        <div className="mt-6 hidden md:block" aria-hidden="true">
          <div className="relative h-16">
            <div className="absolute inset-y-0 rounded-[3px] border border-dashed border-aco-2" style={{ left: `${inicio(2010)}%`, width: `${largura(2010, 2012)}%` }} />
            {f.cobertura_curitiba
              .filter((c) => c.fonte)
              .map((c) => (
                <div key={c.fonte} className="absolute inset-y-0 rounded-[3px]" style={{ left: `${inicio(c.de)}%`, width: `calc(${largura(c.de, c.ate)}% - 3px)`, background: COR[c.fonte!] }} />
              ))}
            <div className="absolute -bottom-2 top-1/2 rounded-b-[3px] opacity-70" style={{ left: `${inicio(2026)}%`, width: `calc(${largura(2026, 2026)}% - 3px)`, background: COR.cmc_prefeitura }} />
          </div>
          <div className="num relative mt-4 h-5 text-xs text-tinta-3">
            {Array.from({ length: anoMax - anoMin + 1 }, (_, i) => anoMin + i).map((a) => (
              <span key={a} className="absolute" style={{ left: `${inicio(a)}%` }}>
                {a}
              </span>
            ))}
          </div>
        </div>
        <ol className="mt-6 grid gap-x-8 gap-y-6 sm:grid-cols-2 lg:grid-cols-5">
          {f.cobertura_curitiba.map((c) => (
            <li key={`${c.de}-${c.fonte}`} className="border-t-[3px] pt-3" style={{ borderColor: c.fonte ? COR[c.fonte] : "var(--color-aco-2)" }}>
              <p className="num font-titulo text-lg font-medium">{c.de === c.ate ? c.de : `${c.de}–${c.ate}`}</p>
              <p className="mt-1 text-[0.95rem]">{c.rotulo}</p>
              {c.detalhe && <p className="mt-1 text-sm text-tinta-3">{c.detalhe}</p>}
              {c.detalhe_tecnico && (
                <details className="mt-1 text-sm text-tinta-3">
                  <summary className="cursor-pointer underline decoration-tinta-3/50 underline-offset-2 hover:text-tinta-2">detalhe técnico</summary>
                  <p className="mt-1">{c.detalhe_tecnico}</p>
                </details>
              )}
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="diarias-cmc" className="mt-16">
        <h2 id="diarias-cmc" className="font-titulo text-2xl font-medium">
          Diárias da Câmara de Curitiba, ano a ano
        </h2>
        <p className="mt-2 max-w-[70ch] text-sm text-tinta-3">
          Vereadores pelo nome nas páginas de cada um; servidores só no total, sem nome. Valores conferidos de cada ano, na fonte
          que cobre aquele ano. O que ficou em revisão não entra na soma: aparece contado na última coluna.
        </p>
        <div className="mt-5 overflow-x-auto">
          <table className="w-full min-w-[520px] text-left text-[0.95rem]">
            <thead className="text-sm text-tinta-3">
              <tr className="border-b border-aco-2">
                <th scope="col" className="py-2 pr-4 font-medium">Ano</th>
                <th scope="col" className="py-2 pr-4 font-medium">Sistema</th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">Vereadores</th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">Servidores (sem nome)</th>
                <th scope="col" className="py-2 text-right font-medium">Em revisão</th>
              </tr>
            </thead>
            <tbody>
              {f.diarias_camara_curitiba.map((d) => {
                const cob = f.cobertura_curitiba.find((c) => c.fonte && d.ano >= c.de && d.ano <= c.ate);
                const fonte = cob?.fonte ?? "cmc_betha";
                const p = { fontes: [fonte], coleta: f.fontes.find((x) => x.id === fonte)?.ultima_coleta?.fim?.slice(0, 10) ?? "", situacao: "soma" as const, nota: `soma das diárias conferidas de ${d.ano}` };
                const anoTodo = d.vereadores === null;
                return (
                  <tr key={d.ano} className="border-b border-aco align-baseline">
                    <td className="num py-2 pr-4">{d.ano}</td>
                    <td className="py-2 pr-4 text-tinta-2">{FONTES[fonte].curto}</td>
                    {anoTodo ? (
                      <td colSpan={2} className="py-2 pr-4 text-right text-tinta-2">
                        <CarimboRevisao /> <span className="ml-2">o ano inteiro, fora dos totais</span>
                      </td>
                    ) : (
                      <>
                        <td className="py-2 pr-4 text-right">
                          <Valor valor={d.vereadores!} p={p} />
                        </td>
                        <td className="py-2 pr-4 text-right">
                          <Valor valor={d.servidores!} p={p} />
                        </td>
                      </>
                    )}
                    <td className="num py-2 text-right text-tinta-3">
                      {d.em_revisao > 0 ? (
                        <a href={`#revisao-${fonte}`} className="underline hover:text-tinta">
                          {contagem(d.em_revisao, "linha", "linhas")}
                        </a>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="fontes" className="mt-16">
        <h2 id="fontes" className="font-titulo text-2xl font-medium">
          Cada fonte, e o que a conferência achou
        </h2>
        <div className="mt-6 divide-y divide-aco border-y border-aco">
          {lista.map((x) => {
            const eq = x.conferencias.find((c) => c.verificacao === "origem_igual_coletado_mais_revisao");
            return (
              <section key={x.id} id={x.id} aria-labelledby={`t-${x.id}`} className="grid scroll-mt-6 gap-6 py-8 lg:grid-cols-[300px_1fr]">
                <div>
                  <h3 id={`t-${x.id}`} className="font-titulo text-xl font-medium leading-tight">
                    {FONTES[x.id]?.curto ?? x.sistema}
                  </h3>
                  <p className="mt-1 text-sm text-tinta-2">
                    {MODO[x.modo]} · {x.fornecedor}
                  </p>
                  <p className="mt-2 text-sm text-tinta-3">{x.o_que_tem}</p>
                  <p className="mt-2 break-all text-sm">
                    <a href={x.endereco} target="_blank" rel="noopener noreferrer" className="text-tinta-2 underline hover:text-carimbo-claro">
                      {x.endereco.replace(/^https?:\/\//, "")}
                    </a>
                  </p>
                  {x.ultima_coleta && (
                    <p className="num mt-2 text-sm text-tinta-3">
                      Última coleta: {data(x.ultima_coleta.fim)} · {contagem(x.inventario.ok ?? 0, "item lido", "itens lidos")}
                      {x.inventario.erro ? `, ${x.inventario.erro} com erro` : ""}
                    </p>
                  )}
                </div>
                <div>
                  {eq && (
                    <p className="num font-titulo text-[1.5rem] font-medium leading-snug">
                      {inteiro(eq.esperado ?? "0")} na origem = {inteiro(eq.obtido ?? "0")} coletadas ou em revisão{" "}
                      <span className={eq.resultado === "confere" ? "text-carimbo-claro" : "text-sepia-claro"}>· {RESULTADO[eq.resultado] ?? eq.resultado}</span>
                    </p>
                  )}
                  {eq?.detalhe && <p className="mt-1 text-sm text-tinta-3">{eq.detalhe}</p>}
                  {(x.situacoes.revisao ?? 0) + x.pendencias_de_leitura > 0 && (
                    <p className="mt-2 text-sm">
                      <a href={`#revisao-${x.id}`} className="text-carimbo-claro underline">
                        Por que {inteiro((x.situacoes.revisao ?? 0) + x.pendencias_de_leitura)} ficaram em revisão
                      </a>
                    </p>
                  )}
                  <details className="mt-4">
                    <summary className="cursor-pointer text-sm text-tinta-2 underline decoration-tinta-3/50 underline-offset-2 hover:text-tinta">
                      Detalhe técnico da conferência
                    </summary>
                  <ul className="mt-3 space-y-1.5 text-[0.92rem]">
                    {resumoConferencias(x)
                      .filter(([v]) => v !== "origem_igual_coletado_mais_revisao")
                      .map(([v, res]) => (
                        <li key={v} className="flex flex-wrap justify-between gap-x-4 border-t border-aco pt-1.5">
                          <span className="text-tinta-2">{rotuloVerificacao(v)}</span>
                          <span className="num text-tinta-3">
                            {[...res.entries()].map(([r, n]) => `${n} ${RESULTADO[r] ?? r}`).join(" · ")}
                          </span>
                        </li>
                      ))}
                  </ul>
                  {x.conferencias
                    .filter((c) => ["observacao", "parcial"].includes(c.resultado) && c.detalhe)
                    .slice(0, 3)
                    .map((c) => (
                      <p key={c.verificacao + c.escopo} className="mt-3 max-w-[70ch] text-sm text-tinta-2">
                        <span className="font-medium text-tinta">{rotuloVerificacao(c.verificacao)}:</span> {c.obtido}. {c.detalhe}.
                      </p>
                    ))}
                  </details>
                </div>
              </section>
            );
          })}
        </div>
      </section>

      <section aria-labelledby="revisao" className="mt-16">
        <h2 id="revisao" className="font-titulo text-2xl font-medium">
          A fila de revisão
        </h2>
        <p className="mt-2 max-w-[70ch] text-tinta-2">
          O que o robô não leu com certeza não é chutado: fica aqui, fora dos totais, até uma pessoa olhar. Cada linha abaixo é um
          motivo. Um item da fila pode ser uma despesa só ou um recorte inteiro (uma categoria num ano), por isso a última coluna
          diz quantas linhas de despesa cada motivo tira dos totais. Cada linha conta num motivo só, e a soma fecha com o total.
        </p>
        <p className="mt-4 font-titulo text-[1.35rem] font-medium leading-snug">
          <span className="num">{inteiro(totalFila)}</span> linhas de despesa em revisão
        </p>
        {fila.map(({ fonte, grupos, linhas }) => (
          <section key={fonte} id={`revisao-${fonte}`} aria-labelledby={`fila-${fonte}`} className="mt-10 scroll-mt-6">
            <h3 id={`fila-${fonte}`} className="flex flex-wrap items-baseline justify-between gap-x-4 font-titulo text-lg font-medium">
              <span>{NOME_FILA[fonte] ?? FONTES[fonte]?.curto ?? fonte}</span>
              <span className="num text-sm font-normal text-tinta-3">{contagem(linhas, "linha de despesa", "linhas de despesa")}</span>
            </h3>
            <table className="mt-3 w-full text-left text-[0.92rem]">
              <caption className="sr-only">Fila de revisão: {NOME_FILA[fonte] ?? FONTES[fonte]?.curto ?? fonte}</caption>
              <thead className="text-sm text-tinta-3">
                <tr className="border-b border-aco-2">
                  <th scope="col" className="py-2 pr-4 font-medium">Motivo</th>
                  <th scope="col" className="py-2 pr-4 text-right font-medium">Itens</th>
                  <th scope="col" className="py-2 text-right font-medium">Linhas de despesa</th>
                </tr>
              </thead>
              <tbody>
                {grupos.map((g) => (
                  <tr key={g.tipo + g.motivo} className="border-b border-aco align-top">
                    <td className="py-2.5 pr-4">
                      <p className="max-w-[70ch]">{motivoDaFila(g)}</p>
                      <details className="mt-1 text-sm text-tinta-3">
                        <summary className="cursor-pointer underline decoration-tinta-3/50 underline-offset-2 hover:text-tinta-2">detalhe técnico</summary>
                        <p className="mt-1 max-w-[70ch] break-words">{g.motivo}</p>
                      </details>
                    </td>
                    <td className="num py-2.5 pr-4 text-right text-tinta-2">{inteiro(g.n)}</td>
                    <td className="num py-2.5 text-right">{g.linhas ? inteiro(g.linhas) : <span className="text-tinta-3">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ))}
        <p className="mt-8 text-sm">
          <a href="/conferencia/" className="text-carimbo-claro underline">
            Abrir o relatório de conferência completo
          </a>
        </p>
      </section>
    </article>
  );
}
