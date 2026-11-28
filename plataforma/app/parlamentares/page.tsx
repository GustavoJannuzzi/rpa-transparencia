import type { Metadata } from "next";
import Link from "next/link";
import ListaRecolhida, { ABRIR_LISTA_DO_ENDERECO } from "@/componentes/ListaRecolhida";
import { casas, indice } from "@/lib/dados";
import { inteiro } from "@/lib/formato";
import { frasesDasAssembleias } from "@/lib/resumo";
import { metadadosDaPagina } from "@/lib/site";
import type { ItemIndice } from "@/lib/tipos";

export const metadata: Metadata = metadadosDaPagina({
  title: "Parlamentares",
  description:
    `Deputados federais da 57ª legislatura, ${frasesDasAssembleias().texto} e vereadores das câmaras do Paraná que a coleta cobre, em ordem alfabética, casa por casa.`,
  caminho: "/parlamentares/",
});

const ORDEM_TIPO = { camara_federal: 0, senado: 1, assembleia: 2, camara_municipal: 3 } as const;

export default function Parlamentares() {
  const todos = indice();
  const porCasa = new Map<string, ItemIndice[]>();
  for (const i of todos) porCasa.set(i.casa, [...(porCasa.get(i.casa) ?? []), i]);
  // federal, depois as assembleias, depois as câmaras; dentro de cada tipo, pelo nome da casa
  const grupos = casas()
    .filter((c) => porCasa.has(c.id))
    .sort((a, b) => ORDEM_TIPO[a.tipo] - ORDEM_TIPO[b.tipo] || (a.municipio ?? a.nome).localeCompare(b.municipio ?? b.nome, "pt-BR"));
  const titulo = (c: (typeof grupos)[number]) =>
    c.tipo === "camara_federal"
      ? "Deputados federais (57ª legislatura)"
      : c.tipo === "assembleia"
        ? `${c.id === "al-df" ? "Deputados distritais" : "Deputados estaduais"}: ${c.nome}`
        : `Vereadores de ${c.municipio}`;
  return (
    <div className="mx-auto max-w-[1180px] px-4 py-8 sm:px-8 sm:py-10">
      <h1 className="font-titulo text-[2.4rem] font-medium leading-tight tracking-[-0.02em]">Parlamentares</h1>
      <p className="mt-2 max-w-[65ch] text-tinta-2">
        Em ordem alfabética, casa por casa: abra a casa para ver os nomes. Esta lista é o mesmo índice do grafo e da busca, para quem prefere
        navegar sem eles. Que casas
        entram, e por que outras ficam de fora, está em{" "}
        <Link href="/cobertura/" className="underline hover:text-tinta">
          Cobertura
        </Link>
        .
      </p>
      <nav aria-label="Casas nesta página" className="mt-6 flex flex-wrap gap-x-4 gap-y-1.5 text-sm">
        {grupos.map((c) => (
          <a key={c.id} href={`#casa-${c.id}`} className="text-tinta-2 underline hover:text-tinta">
            {c.tipo === "camara_municipal" ? c.municipio : c.tipo === "camara_federal" ? "Câmara dos Deputados" : c.uf}
          </a>
        ))}
      </nav>
      {grupos.map((c) => {
        const itens = porCasa.get(c.id) ?? [];
        return (
          <section key={c.id} className="mt-10 scroll-mt-6" id={`casa-${c.id}`} aria-labelledby={`titulo-${c.id}`}>
            <h2 id={`titulo-${c.id}`} className="font-titulo text-xl font-medium">
              {titulo(c)} <span className="num text-tinta-3">({inteiro(itens.length)})</span>
            </h2>
            <p className="mt-1 text-sm">
              <Link href={`/casas/${c.id}/`} className="text-tinta-3 underline hover:text-tinta">
                A casa: sistema, totais e o que ficou em revisão
              </Link>
            </p>
            <ListaRecolhida
              rotulo={itens.length === 1 ? "Mostrar o nome" : `Mostrar os ${inteiro(itens.length)} nomes`}
              className="mt-4 columns-1 gap-8 sm:columns-2 lg:columns-3"
            >
              {itens.map((i) => (
                <li key={i.id} className="break-inside-avoid border-t border-aco py-1.5">
                  <Link href={`/parlamentares/${i.id}/`} prefetch={false} className="hover:text-carimbo-claro hover:underline">
                    {i.nome}
                  </Link>
                  <span className="text-sm text-tinta-3">
                    {" "}
                    · {i.partido ?? (c.tipo === "assembleia" ? "partido não informado" : "partido em revisão")}
                    {i.casa === "camara-deputados" ? ` · ${i.uf}` : ""}
                  </span>
                </li>
              ))}
            </ListaRecolhida>
          </section>
        );
      })}
      {/* abre a lista da casa do endereço (#casa-…): script em linha, sem componente de cliente */}
      <script dangerouslySetInnerHTML={{ __html: ABRIR_LISTA_DO_ENDERECO }} />
    </div>
  );
}
