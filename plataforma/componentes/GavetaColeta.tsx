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

/** A gaveta da coleta: uma ficha por fonte, com a equação da conferência. */
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
          return (
            <li key={f.id} className="relative rounded-[3px] bg-manilha px-4 py-3.5 text-manilha-tinta" style={{ marginLeft: `${(i % 2) * 6}px` }}>
              <div className="pr-24">
                <h3 className="font-titulo text-[1.02rem] font-semibold leading-tight">{FONTES[f.id]?.curto ?? f.sistema}</h3>
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
                    {cruzada > 0 && <> + {inteiro(cruzada)} só para conferir a fronteira</>} + {inteiro(revisao)} em revisão
                  </span>
                </p>
              ) : (
                <p className="mt-2 text-[0.86rem] text-manilha-tinta-2">{f.o_que_tem}</p>
              )}
              <span className="absolute right-3 top-3 flex flex-col items-end gap-1.5">
                <span
                  className={`rounded-[3px] border-2 px-1.5 py-0.5 font-titulo text-[0.66rem] font-semibold tracking-[0.08em] ${confere ? "border-carimbo-escuro text-carimbo-escuro" : "border-sepia text-sepia"}`}
                  style={{ transform: "rotate(-6deg)" }}
                >
                  {confere ? "CONFERIDO" : "VER CONFERÊNCIA"}
                </span>
                {revisao > 0 && (
                  <span
                    className="rounded-[3px] border-2 border-sepia px-1.5 py-0.5 font-titulo text-[0.62rem] font-semibold tracking-[0.06em] text-sepia"
                    style={{ transform: "rotate(-3deg)" }}
                  >
                    {inteiro(revisao)} EM REVISÃO
                  </span>
                )}
              </span>
            </li>
          );
        })}
      </ol>
      <p className="mt-5 text-sm">
        <Link href="/como-os-dados-chegam-aqui/" className="text-carimbo-claro underline">
          Como os dados chegam aqui: os quatro sistemas de Curitiba, a conferência e a fila de revisão
        </Link>
      </p>
    </section>
  );
}
