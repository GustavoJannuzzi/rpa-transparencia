import type { Metadata } from "next";
import Link from "next/link";
import { AtividadeDaCasa } from "@/componentes/Atividade";
import Barras, { type ItemBarra } from "@/componentes/Barras";
import { CarimboRevisao } from "@/componentes/EmRevisao";
import Valor from "@/componentes/Valor";
import { casa as lerCasa, casas, categorias } from "@/lib/dados";
import { MODO } from "@/lib/fontes";
import { contagem, data, inteiro } from "@/lib/formato";
import { motivoDaFila } from "@/lib/revisao";
import { metadadosDaPagina } from "@/lib/site";
import type { Casa, Procedencia } from "@/lib/tipos";

export const dynamicParams = false;

export function generateStaticParams() {
  return casas()
    .filter((c) => c.id !== "camara-deputados")
    .map((c) => ({ id: c.id }));
}

function quem(c: Casa) {
  if (c.tipo === "camara_municipal") return ["vereador", "vereadores"];
  if (c.id === "al-df") return ["deputado distrital", "deputados distritais"];
  return ["deputado estadual", "deputados estaduais"];
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const c = lerCasa(id);
  const oque = c.tipo === "camara_municipal" ? "Diárias de vereadores" : "Verba indenizatória dos deputados";
  return metadadosDaPagina({
    title: c.nome,
    description: `${oque} da ${c.nome}, de ${c.de} a ${c.ate}, coletadas de ${c.sistemas.map((s) => s.sistema).join(" e ")}, com a conferência e o que ficou em revisão.`,
    caminho: `/casas/${c.id}/`,
  });
}

/** "origem (…) = 233; coletado = 230; revisão = 3" -> ["230", "3"] */
function partes(detalhe?: string | null): [string, string] | null {
  const m = /coletado = (\d+); revisão = (\d+)/.exec(detalhe ?? "");
  return m ? [m[1], m[2]] : null;
}

const RESULTADO: Record<string, string> = { confere: "confere", diverge: "não fecha", parcial: "fecha em parte", observacao: "observação" };

export default async function PaginaCasa({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const c = lerCasa(id);
  const rot = categorias();
  const municipal = c.tipo === "camara_municipal";
  const [um, varios] = quem(c);
  const proc = (nota?: string, linhas?: number): Procedencia => ({ fontes: c.p.fontes, coleta: c.p.coleta, situacao: "soma", nota, linhas });
  const cats: ItemBarra[] = Object.entries(c.por_categoria).map(([k, v]) => ({ chave: k, valor: v, p: proc(`soma da categoria nas despesas conferidas da casa`) }));
  const agregado = c.id === "al-sp";
  const revisaoTotal = c.em_revisao_por_motivo.reduce((s, m) => s + m.linhas, 0);
  // o mesmo motivo de leigo junta anotações diferentes do robô (uma linha pode ter dois motivos)
  const porMotivo = new Map<string, { linhas: number; anotacoes: string[] }>();
  for (const m of c.em_revisao_por_motivo) {
    const leigo = motivoDaFila({ tipo: "despesa", motivo: m.motivo, fonte: m.fonte });
    const atual = porMotivo.get(leigo) ?? { linhas: 0, anotacoes: [] };
    atual.linhas += m.linhas;
    atual.anotacoes.push(m.motivo.replace(/R\$\s?/g, ""));
    porMotivo.set(leigo, atual);
  }
  const motivos = [...porMotivo.entries()].sort((a, b) => b[1].linhas - a[1].linhas);

  return (
    <article className="mx-auto max-w-[1180px] px-4 py-8 sm:px-8 sm:py-10">
      <p className="text-sm text-tinta-3">
        <Link href="/cobertura/" className="underline hover:text-tinta">
          Cobertura
        </Link>{" "}
        / {municipal ? `Câmaras do ${c.uf}` : "Assembleias"}
      </p>
      <header className="mt-3 grid gap-6 border-b border-aco pb-8 md:grid-cols-[1fr_auto] md:items-end">
        <div>
          <h1 className="max-w-[22ch] font-titulo text-[2.2rem] font-medium leading-[1.04] tracking-[-0.02em] sm:text-[3rem]">{c.nome}</h1>
          <p className="mt-2 text-tinta-2">
            {municipal ? `${c.municipio}, ${c.uf}` : c.uf} · {c.de === c.ate ? c.de : `${c.de} a ${c.ate}`} ·{" "}
            <Link href={`/parlamentares/#casa-${c.id}`} className="underline hover:text-tinta">
              {contagem(c.parlamentares, um, varios)}
              {municipal ? "" : " no período"}
            </Link>
            {c.com_despesa !== c.parlamentares && <span className="text-tinta-3"> ({inteiro(c.com_despesa)} com {municipal ? "diária" : "despesa"} conferida)</span>}
          </p>
        </div>
        <div className="md:text-right">
          {c.linhas > 0 ? (
            <>
              <p className="text-sm text-tinta-3">{municipal ? "Diárias de vereadores conferidas" : "Total conferido"}, {c.de === c.ate ? c.de : `${c.de}–${c.ate}`}</p>
              <Valor valor={c.total} p={proc(`soma das despesas conferidas dos ${varios} da casa`, c.linhas)} tamanho="grande" />
              <p className="num mt-1 text-sm text-tinta-3">{contagem(c.linhas, agregado ? "linha agregada" : municipal ? "diária" : "nota", agregado ? "linhas agregadas" : municipal ? "diárias" : "notas")}</p>
            </>
          ) : (
            <p className="font-titulo text-2xl text-tinta-3">Nenhuma despesa conferida</p>
          )}
        </div>
        {revisaoTotal > 0 && (
          <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[0.92rem] text-tinta-2 md:col-span-2">
            <CarimboRevisao />
            <span>
              Fora desta soma, em revisão: <span className="num">{contagem(revisaoTotal, "linha lida", "linhas lidas")}</span> da fonte.{" "}
              <a href="#em-revisao" className="whitespace-nowrap text-carimbo-claro underline">
                Por quê
              </a>
            </span>
          </p>
        )}
        {agregado && (
          <p className="max-w-[72ch] text-[0.92rem] text-tinta-2 md:col-span-2">
            A ALESP publica a despesa já somada por fornecedor, tipo e mês. Cada linha é uma soma feita pela própria fonte, não uma nota: não
            tem data nem número de documento.
          </p>
        )}
      </header>

      <section aria-labelledby="de-onde" className="mt-8">
        <h2 id="de-onde" className="font-titulo text-2xl font-medium">
          De onde vem
        </h2>
        <ol className="mt-4 grid gap-3 md:grid-cols-2">
          {c.sistemas.map((s, i) => {
            const eq = c.conferencia.find((x) => x.fonte === s.fonte);
            const fecha = eq?.resultado === "confere" && (eq.erros ?? "0") === "0";
            return (
              <li key={s.fonte} className="relative rounded-[3px] bg-manilha px-4 py-3.5 text-manilha-tinta" style={{ marginLeft: `${(i % 2) * 6}px` }}>
                <div className="pr-28">
                  <h3 className="font-titulo text-[1.02rem] font-semibold leading-tight">{s.sistema}</h3>
                  <p className="mt-0.5 text-[0.8rem] text-manilha-tinta-2">
                    {s.fornecedor} · {MODO[s.modo] ?? s.modo} · {s.de === s.ate ? s.de : `${s.de}–${s.ate}`}
                  </p>
                </div>
                {eq?.esperado && (
                  <p className="num mt-2 text-[0.86rem] leading-snug">
                    <span className="font-titulo text-[1.35rem] font-semibold">{inteiro(eq.esperado)}</span> linhas na origem
                    {partes(eq.detalhe) && (
                      <span className="text-manilha-tinta-2">
                        {" "}
                        = {inteiro(partes(eq.detalhe)![0])} publicadas + {inteiro(partes(eq.detalhe)![1])} em revisão
                      </span>
                    )}
                  </p>
                )}
                <p className="mt-2 text-[0.8rem]">
                  <a href={s.endereco} className="break-all text-carimbo-escuro underline underline-offset-[3px]" rel="noreferrer">
                    {s.endereco.replace(/^https?:\/\//, "")}
                  </a>
                </p>
                <span
                  className={`pointer-events-none absolute right-3 top-3 rounded-[3px] border-2 px-1.5 py-0.5 font-titulo text-[0.66rem] font-semibold tracking-[0.08em] ${fecha ? "border-carimbo-escuro text-carimbo-escuro" : "border-sepia text-sepia"}`}
                  style={{ transform: "rotate(-6deg)" }}
                >
                  {fecha ? "CONFERIDO" : "VER CONFERÊNCIA"}
                </span>
              </li>
            );
          })}
        </ol>
      </section>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-10 py-10 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-12">
          <section aria-labelledby="ano-a-ano">
            <h2 id="ano-a-ano" className="font-titulo text-2xl font-medium">
              Ano a ano
            </h2>
            {municipal && (
              <p className="mt-1 max-w-[70ch] text-sm text-tinta-3">
                Diária de vereador aparece com o nome. Diária de servidor e de quem mais viajou pela Câmara entra só na soma, sem o nome de
                ninguém.
              </p>
            )}
            <table className="mt-4 w-full text-left text-[0.92rem]">
              <caption className="sr-only">{municipal ? "Diárias por ano: vereadores e servidores" : "Despesas conferidas por ano"}</caption>
              <thead className="text-[0.78rem] text-tinta-3">
                <tr className="border-b border-aco-2">
                  <th scope="col" className="py-2 pr-4 font-normal">
                    Ano
                  </th>
                  <th scope="col" className="py-2 pr-4 text-right font-normal">
                    {municipal ? "Vereadores" : "Deputados"}
                  </th>
                  {municipal && (
                    <th scope="col" className="py-2 text-right font-normal">
                      Servidores e outros, só a soma
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {c.por_ano.map((a) => (
                  <tr key={a.ano} className="border-b border-aco">
                    <th scope="row" className="num py-2 pr-4 text-left font-normal text-tinta">
                      {a.ano}
                    </th>
                    {a.fonte_nao_publica && !a.linhas ? (
                      <td colSpan={municipal ? 2 : 1} className="py-2 text-right text-tinta-3">
                        a fonte não publica diária nenhuma neste ano
                      </td>
                    ) : (
                      <>
                        <td className="py-2 pr-4 text-right">
                          {(municipal ? a.vereadores : a.total) ? (
                            <Valor valor={(municipal ? a.vereadores : a.total)!} p={proc(`soma conferida de ${a.ano}`, municipal ? a.linhas_vereadores : undefined)} />
                          ) : (
                            <span className="text-tinta-3">—</span>
                          )}
                        </td>
                        {municipal && (
                          <td className="py-2 text-right">
                            {a.servidores && a.linhas !== a.linhas_vereadores ? (
                              <Valor valor={a.servidores} p={proc(`soma das diárias de servidores e outros em ${a.ano}, sem nome`, (a.linhas ?? 0) - (a.linhas_vereadores ?? 0))} />
                            ) : (
                              <span className="text-tinta-3">—</span>
                            )}
                          </td>
                        )}
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          {c.em_revisao_por_motivo.length > 0 && (
            <section id="em-revisao" aria-labelledby="em-revisao-t" className="scroll-mt-6">
              <h2 id="em-revisao-t" className="font-titulo text-2xl font-medium">
                Em revisão, fora da soma
              </h2>
              <p className="mt-1 max-w-[70ch] text-sm text-tinta-3">
                O que o robô não leu com certeza não entra nos totais nem é completado. Fica aqui, contado, com o motivo.
              </p>
              <ul className="mt-4 space-y-3 text-[0.92rem]">
                {motivos.map(([leigo, m]) => (
                  <li key={leigo} className="border-t border-aco pt-2.5">
                    <p className="text-tinta">
                      {leigo} <span className="num text-tinta-3">· {contagem(m.linhas, "linha", "linhas")}</span>
                    </p>
                    <details className="mt-1 text-sm text-tinta-3">
                      <summary className="cursor-pointer hover:text-tinta-2">Como o robô anotou</summary>
                      {/* a anotação do robô pode citar um valor da fonte; o número fica, o "R$" não (todo R$ da tela tem ficha) */}
                      <ul className="mt-1 space-y-1 break-words">
                        {m.anotacoes.map((a) => (
                          <li key={a}>{a}</li>
                        ))}
                      </ul>
                    </details>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section aria-labelledby="membros">
            <h2 id="membros" className="font-titulo text-2xl font-medium">
              {varios.charAt(0).toUpperCase() + varios.slice(1)}
            </h2>
            <p className="mt-1 text-sm text-tinta-3">Em ordem alfabética.</p>
            <ul className="mt-4 columns-1 gap-8 sm:columns-2">
              {c.membros.map((m) => (
                <li key={m.id} className="flex break-inside-avoid items-baseline justify-between gap-3 border-t border-aco py-1.5">
                  <span className="min-w-0">
                    <Link href={`/parlamentares/${m.id}/`} className="hover:text-carimbo-claro hover:underline">
                      {m.nome}
                    </Link>
                    <span className="text-sm text-tinta-3"> · {m.partido ?? (municipal ? "partido em revisão" : "partido não informado")}</span>
                  </span>
                  {m.linhas > 0 ? (
                    <Valor valor={m.total} p={proc(`soma conferida de ${m.nome}`, m.linhas)} className="shrink-0 text-sm" />
                  ) : (
                    <span className="shrink-0 text-sm text-tinta-3">sem {municipal ? "diária" : "despesa"}</span>
                  )}
                </li>
              ))}
            </ul>
          </section>
        </div>

        <aside aria-label="Resumo da casa" className="min-w-0 space-y-10">
          {cats.length > 0 && !municipal && (
            <section aria-labelledby="por-cat">
              <h2 id="por-cat" className="font-titulo text-lg font-medium">
                Por categoria
              </h2>
              <div className="mt-3">
                <Barras itens={cats} rotulos={rot} />
              </div>
            </section>
          )}
          {c.subsidio && (
            <section aria-labelledby="subsidio">
              <h2 id="subsidio" className="font-titulo text-lg font-medium">
                Subsídio
              </h2>
              <p className="mt-1 text-sm text-tinta-3">
                O que o cadastro de pessoal da Câmara mostra para {contagem(c.subsidio.pessoas, "vereador ativo", "vereadores ativos")} em{" "}
                {c.subsidio.datas.map(data).join(", ")}. Retrato de um dia; a página de cada vereador traz o seu.
              </p>
              <p className="mt-3 text-[0.95rem] text-tinta-2">
                {c.subsidio.min === c.subsidio.max ? (
                  <Valor valor={c.subsidio.min} tamanho="medio" p={{ fontes: c.subsidio.fontes, coleta: c.p.coleta, situacao: "conferido", nota: "remuneração no cadastro de pessoal" }} />
                ) : (
                  <>
                    de <Valor valor={c.subsidio.min} p={{ fontes: c.subsidio.fontes, coleta: c.p.coleta, situacao: "conferido", nota: "menor remuneração de vereador no cadastro" }} /> a{" "}
                    <Valor valor={c.subsidio.max} p={{ fontes: c.subsidio.fontes, coleta: c.p.coleta, situacao: "conferido", nota: "maior remuneração de vereador no cadastro (a presidência costuma receber mais)" }} />
                  </>
                )}
              </p>
            </section>
          )}
          {c.outras_conferencias.length > 0 && (
            <section aria-labelledby="conferencias">
              <h2 id="conferencias" className="font-titulo text-lg font-medium">
                O que mais foi conferido
              </h2>
              <ul className="mt-3 space-y-2.5 text-sm">
                {c.outras_conferencias.map((x) => (
                  <li key={`${x.fonte}-${x.verificacao}-${x.escopo}`} className="border-t border-aco pt-2">
                    <p className="text-tinta">
                      {x.detalhe ?? x.verificacao.replaceAll("_", " ")} <span className="text-tinta-3">· {RESULTADO[x.resultado] ?? x.resultado}</span>
                    </p>
                    {(x.esperado || x.obtido) && (
                      <p className="num mt-0.5 break-words text-tinta-3">
                        {x.esperado && <>esperado: {x.esperado}</>}
                        {x.esperado && x.obtido && " · "}
                        {x.obtido && <>obtido: {x.obtido}</>}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
          {c.fornecedores_comuns.length > 0 && (
            <section aria-labelledby="fornecedores">
              <h2 id="fornecedores" className="font-titulo text-lg font-medium">
                Fornecedores pagos por mais de um
              </h2>
              <p className="mt-1 text-sm text-tinta-3">
                O mesmo CNPJ pago por vários {varios}. É o que liga um ponto a outro no grafo, e não insinua nada.
              </p>
              <ul className="mt-3 space-y-1.5 text-sm">
                {c.fornecedores_comuns.map((f) => (
                  <li key={f.doc} className="flex justify-between gap-3 border-t border-aco pt-1.5">
                    <span className="min-w-0 text-tinta-2">
                      {f.nome ?? f.doc} <span className="num block text-[0.78rem] text-tinta-3">{f.doc}</span>
                    </span>
                    <span className="num shrink-0 text-tinta-3">{contagem(f.parlamentares, um, varios)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </aside>
      </div>

      <AtividadeDaCasa atividade={c.atividade ?? []} />
    </article>
  );
}
