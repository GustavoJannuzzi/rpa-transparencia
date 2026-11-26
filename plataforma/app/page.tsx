import GavetaColeta from "@/componentes/GavetaColeta";
import Grafo from "@/componentes/Grafo";
import { fontes, grafo } from "@/lib/dados";
import { TELA_ESTREITA } from "@/lib/telas";

export default function Inicio() {
  const f = fontes();
  // a regra de cada vista vai no HTML: o texto sob o quadro não chega depois e não muda o tamanho dele
  const regras = {
    brasil: { regra: grafo("brasil").regra, tecnica: grafo("brasil").regra_tecnica },
    parana: { regra: grafo("parana").regra, tecnica: grafo("parana").regra_tecnica },
  };
  return (
    <div className="mx-auto grid max-w-[1600px] lg:min-h-[calc(100dvh-4rem)] lg:grid-cols-[1fr_440px]">
      {/* os dados do grafo saem junto com a página, antes do JavaScript dela: a vista da URL,
          ou o Paraná no celular e o Brasil no computador */}
      <script
        dangerouslySetInnerHTML={{
          __html: `(function(){try{var q=new URLSearchParams(location.search).get("vista");var v=q==="brasil"||q==="parana"?q:matchMedia(${JSON.stringify(TELA_ESTREITA)}).matches?"parana":"brasil";var p=fetch("/dados/grafo-"+v+".json").then(function(r){if(!r.ok)throw new Error(r.status);return r.json()});p.catch(function(){});window.__grafoInicial={vista:v,dados:p}}catch(e){}})()`,
        }}
      />
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
          <Grafo regras={regras} />
        </div>
      </section>
      <aside className="border-t border-aco lg:border-t-0">
        <GavetaColeta fontes={f} />
      </aside>
    </div>
  );
}
