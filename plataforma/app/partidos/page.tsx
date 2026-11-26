import type { Metadata } from "next";
import Link from "next/link";
import { partidos } from "@/lib/dados";
import { metadadosDaPagina } from "@/lib/site";

export const metadata: Metadata = metadadosDaPagina({
  title: "Partidos",
  description: "Os partidos dos deputados federais e dos vereadores de Curitiba, com as despesas conferidas de quem passou por cada um.",
  caminho: "/partidos/",
});

export default function Partidos() {
  const lista = partidos().sort((a, b) => a.sigla.localeCompare(b.sigla, "pt-BR"));
  return (
    <div className="mx-auto max-w-[1180px] px-4 py-8 sm:px-8 sm:py-10">
      <h1 className="font-titulo text-[2.4rem] font-medium leading-tight tracking-[-0.02em]">Partidos</h1>
      <p className="mt-2 max-w-[68ch] text-tinta-2">
        Em ordem alfabética, sem comparação de gasto entre partidos: o tamanho de uma bancada muda tudo, e um total lado a
        lado diz mais sobre o número de cadeiras do que sobre qualquer outra coisa.
      </p>
      <table className="mt-8 w-full text-left">
        <caption className="sr-only">Partidos com parlamentares na plataforma</caption>
        <thead className="text-sm text-tinta-3">
          <tr className="border-b border-aco-2">
            <th scope="col" className="py-2 pr-4 font-medium">Partido</th>
            <th scope="col" className="py-2 pr-4 font-medium">Deputados federais</th>
            <th scope="col" className="py-2 pr-4 font-medium">Deputados estaduais</th>
            <th scope="col" className="py-2 font-medium">Vereadores</th>
          </tr>
        </thead>
        <tbody>
          {lista.map((p) => (
            <tr key={p.sigla} className="border-b border-aco">
              <td className="py-2 pr-4">
                <Link href={`/partidos/${p.slug}/`} className="font-titulo font-medium underline decoration-tinta-3 hover:text-carimbo-claro">
                  {p.sigla}
                </Link>
              </td>
              <td className="num py-2 pr-4 text-tinta-2">{p.federal || "—"}</td>
              <td className="num py-2 pr-4 text-tinta-2">{p.estadual || "—"}</td>
              <td className="num py-2 text-tinta-2">{p.municipal || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-4 text-sm text-tinta-3">Contagem pelo partido atual de cada parlamentar.</p>
    </div>
  );
}
