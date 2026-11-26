import Link from "next/link";
import { FONTES, MODO } from "@/lib/fontes";
import { data, inteiro } from "@/lib/formato";
import type { Fonte, Fontes } from "@/lib/tipos";

function equacao(f: Fonte) {
  const eq = f.conferencias.find((c) => c.verificacao === "origem_igual_coletado_mais_revisao");
  const erros = f.conferencias.find((c) => c.verificacao === "erros_em_aberto");
  const revisao = (f.situacoes.revisao ?? 0) + f.pendencias_de_leitura;
  const publicadas = (f.situacoes.ok ?? 0) + (f.situacoes.fora_da_soma ?? 0);
  const cruzada = f.situacoes.conferencia_cruzada ?? 0;
  return { eq, revisao, publicadas, cruzada, semErro: erros?.resultado === "confere" };
}

const COMO = "/como-os-dados-chegam-aqui/";

/** A gaveta da coleta: uma ficha por fonte, com a equação da conferência. Cada
 * ficha leva à fonte em "Como os dados chegam aqui"; o carimbo de revisão, à fila
 * daquela fonte. */
export default function GavetaColeta({ fontes }: { fontes: Fontes }) {
  const publicadas = fontes.fontes.reduce((s, f) => s + (f.situacoes.ok ?? 0) + (f.situacoes.fora_da_soma ?? 0), 0);
  const ultimaColeta = fontes.fontes.map((f) => f.ultima_coleta?.fim ?? "").sort().at(-1) ?? "";
  const ordem = ["camara_deputados", "cmc_legado", "cmc_elotech", "cmc_prefeitura", "cmc_betha", "tse"];
  const lista = ordem.map((id) => fontes.fontes.find((f) => f.id === id)).filter(Boolean) as Fonte[];
  return (
    <section aria-labelledby="coleta-titulo" className="px-4 pb-8 pt-5 sm:px-8 lg:px-6">
      <h2 id="coleta-titulo" className="font-titulo text-2xl font-medium">
        A coleta
      </h2>
      <p className="mt-1 text-sm text-tinta-3">
        <span className="num">{inteiro(publicadas)}</span> despesas passaram na conferência · última coleta em{" "}
        <span className="num">{data(ultimaColeta)}</span>
      </p>
      <ol className="mt-5 space-y-3">
        {lista.map((f, i) => {
          const { eq, revisao, publicadas, cruzada, semErro } = equacao(f);
          const confere = eq ? eq.resultado === "confere" && semErro : semErro;
          // a conta fecha, mas nada foi publicado: o carimbo confere a conta, não valores
          const carimbo = !confere ? "VER CONFERÊNCIA" : eq && publicadas === 0 ? "CONTA FECHADA" : "CONFERIDO";
          return (
            <li
              key={f.id}
              className="group relative rounded-[3px] bg-manilha px-4 py-3.5 text-manilha-tinta transition-transform duration-200 ease-out hover:-translate-y-0.5"
              style={{ marginLeft: `${(i % 2) * 6}px` }}
            >
              <div className="pr-28">
                <h3 className="font-titulo text-[1.02rem] font-semibold leading-tight">
                  {/* a ficha inteira é o link para a fonte; o carimbo de revisão fica por cima, com o seu próprio link */}
                  <Link
                    href={`${COMO}#${f.id}`}
                    className="underline decoration-manilha-tinta/30 underline-offset-[3px] after:absolute after:inset-0 after:rounded-[3px] group-hover:decoration-manilha-tinta"
                  >
                    {FONTES[f.id]?.curto ?? f.sistema}
                  </Link>
                </h3>
                <p className="mt-0.5 text-[0.8rem] text-manilha-tinta-2">
                  {MODO[f.modo]} · {f.cobre_de === f.cobre_ate ? f.cobre_de : `${f.cobre_de}–${f.cobre_ate}`}
                </p>
              </div>
              {eq ? (
                <p className="num mt-2 text-[0.86rem] leading-snug">
                  <span className="font-titulo text-[1.35rem] font-semibold">{inteiro(eq.esperado ?? "0")}</span> linhas na origem
                  <span className="text-manilha-tinta-2">
                    {" "}
                    = {inteiro(publicadas)} publicadas
                    {cruzada > 0 && <> + {inteiro(cruzada)} usadas só para conferir 2026 com o Betha</>} + {inteiro(revisao)} em revisão
                  </span>
                </p>
              ) : (
                <p className="mt-2 text-[0.86rem] text-manilha-tinta-2">{f.o_que_tem}</p>
              )}
              <span className="pointer-events-none absolute right-3 top-3 flex flex-col items-end gap-1.5">
                <span
                  className={`rounded-[3px] border-2 px-1.5 py-0.5 font-titulo text-[0.66rem] font-semibold tracking-[0.08em] ${confere ? "border-carimbo-escuro text-carimbo-escuro" : "border-sepia text-sepia"}`}
                  style={{ transform: "rotate(-6deg)" }}
                >
                  {carimbo}
                </span>
                {revisao > 0 && (
                  <Link
                    href={`${COMO}#revisao-${f.id}`}
                    className="pointer-events-auto relative z-10 rounded-[3px] border-2 border-sepia px-1.5 py-0.5 font-titulo text-[0.62rem] font-semibold tracking-[0.06em] text-sepia hover:bg-manilha-2"
                    style={{ transform: "rotate(-3deg)" }}
                    aria-label={`${inteiro(revisao)} em revisão: ver a fila de revisão de ${FONTES[f.id]?.curto ?? f.sistema}`}
                  >
                    {inteiro(revisao)} EM REVISÃO
                  </Link>
                )}
              </span>
            </li>
          );
        })}
      </ol>
      <p className="mt-5 text-sm">
        <Link href={COMO} className="text-carimbo-claro underline">
          Como os dados chegam aqui: os quatro sistemas de Curitiba, a conferência e a fila de revisão
        </Link>
      </p>
      <p className="mt-2 text-sm">
        <Link href="/cobertura/" className="text-carimbo-claro underline">
          Cobertura: as outras casas (assembleias e câmaras do PR), em que sistema, e por que as que faltam ficaram de fora
        </Link>
      </p>
    </section>
  );
}
