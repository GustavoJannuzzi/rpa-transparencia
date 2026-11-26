import GavetaColeta from "@/componentes/GavetaColeta";
import Grafo from "@/componentes/Grafo";
import { fontes } from "@/lib/dados";

export default function Inicio() {
  const f = fontes();
  return (
    <div className="mx-auto grid max-w-[1600px] lg:min-h-[calc(100dvh-4rem)] lg:grid-cols-[1fr_440px]">
      <section aria-labelledby="titulo" className="flex flex-col border-aco lg:border-r">
        <div className="px-4 pt-6 sm:px-8">
          <h1 id="titulo" className="max-w-[24ch] font-titulo text-[2.1rem] font-medium leading-[1.04] tracking-[-0.02em] sm:text-[2.6rem]">
            Quem gastou com quem, e de onde vem cada número
          </h1>
          <p className="mt-3 max-w-[62ch] text-[0.98rem] leading-relaxed text-tinta-2">
            Deputados federais ligados pelos fornecedores que contrataram em comum, e vereadores de Curitiba ligados aos seus
            partidos. Fornecedor em comum não insinua nada: só mostra que duas pessoas contrataram a mesma empresa.
          </p>
        </div>
        <div className="flex-1">
          <Grafo />
        </div>
      </section>
      <aside className="border-t border-aco lg:border-t-0">
        <GavetaColeta fontes={f} />
      </aside>
    </div>
  );
}
