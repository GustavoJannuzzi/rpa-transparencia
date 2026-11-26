import type { Metadata } from "next";
import Link from "next/link";
import { indice } from "@/lib/dados";
import { inteiro } from "@/lib/formato";
import { metadadosDaPagina } from "@/lib/site";

export const metadata: Metadata = metadadosDaPagina({
  title: "Parlamentares",
  description: "Deputados federais da 57ª legislatura e vereadores de Curitiba, em ordem alfabética, com as despesas conferidas de cada um.",
  caminho: "/parlamentares/",
});

export default function Parlamentares() {
  const todos = indice();
  const grupos = [
    { id: "vereadores", titulo: "Vereadores de Curitiba", itens: todos.filter((i) => i.casa === "cmc") },
    { id: "deputados", titulo: "Deputados federais (57ª legislatura)", itens: todos.filter((i) => i.casa === "camara-deputados") },
  ];
  return (
    <div className="mx-auto max-w-[1180px] px-4 py-8 sm:px-8 sm:py-10">
      <h1 className="font-titulo text-[2.4rem] font-medium leading-tight tracking-[-0.02em]">Parlamentares</h1>
      <p className="mt-2 max-w-[65ch] text-tinta-2">
        Em ordem alfabética. Esta lista é o mesmo índice do grafo, para quem prefere navegar sem ele.
      </p>
      {grupos.map((g) => (
        <section key={g.id} className="mt-10" aria-labelledby={g.id}>
          <h2 id={g.id} className="font-titulo text-xl font-medium">
            {g.titulo} <span className="num text-tinta-3">({inteiro(g.itens.length)})</span>
          </h2>
          <ul className="mt-4 columns-1 gap-8 sm:columns-2 lg:columns-3">
            {g.itens.map((i) => (
              <li key={i.id} className="break-inside-avoid border-t border-aco py-1.5">
                <Link href={`/parlamentares/${i.id}/`} className="hover:text-carimbo-claro hover:underline">
                  {i.nome}
                </Link>
                <span className="text-sm text-tinta-3">
                  {" "}
                  · {i.partido ?? "partido em revisão"}
                  {i.casa === "camara-deputados" ? ` · ${i.uf}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
