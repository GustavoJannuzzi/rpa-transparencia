import type { Metadata } from "next";
import Link from "next/link";
import MapaCobertura, { PadroesMapa } from "@/componentes/MapaCobertura";
import TabelaCobertura from "@/componentes/TabelaCobertura";
import { type Classe, classe, type LinhaCobertura, MOTIVO_FORA } from "@/lib/cobertura";
import { casas, cobertura, mapa } from "@/lib/dados";
import { MODO } from "@/lib/fontes";
import { data, inteiro, listaE } from "@/lib/formato";
import { metadadosDaPagina } from "@/lib/site";
import type { ResumoCasa, SistemaDaCasa } from "@/lib/tipos";

export const metadata: Metadata = metadadosDaPagina({
  title: "Cobertura",
  description:
    "Quais casas legislativas a coleta cobre, em qual sistema cada uma publica os gastos, e por que as outras ficaram de fora: robots.txt, captcha, Cloudflare ou fornecedor ainda sem adaptador.",
  caminho: "/cobertura/",
});

/** O fornecedor de cada câmara no levantamento -> se a coleta já tem adaptador para ele. */
const ADAPTADOR: Record<string, string> = {
  elotech: "adaptador pronto (API)",
  betha: "adaptador pronto (navegador)",
  equiplano: "adaptador pronto (navegador)",
  pronim: "próximo adaptador (navegador)",
  ipm: "fora: robots.txt e Cloudflare",
  inga: "fora: robots.txt",
};
/** O fornecedor do levantamento -> como o adaptador dele assina o sistema de cada casa. */
const FORNECEDOR_DO_SISTEMA: Record<string, string> = {
  elotech: "Elotech",
  betha: "Betha Sistemas",
  equiplano: "Equiplano",
};
const NOME_FORN: Record<string, string> = {
  elotech: "Elotech",
  betha: "Betha Cloud",
  equiplano: "Equiplano",
  pronim: "Govbr Pronim",
  ipm: "IPM Atende.net",
  inga: "Inga Digital",
};

type Sistema = { chave: string; s: SistemaDaCasa; casas: { casa: ResumoCasa; s: SistemaDaCasa }[] };

/** Um robô por sistema: cada sistema com as casas que ele atende. */
function porSistema(lista: ResumoCasa[]): Sistema[] {
  const m = new Map<string, Sistema>();
  for (const c of lista)
    for (const s of c.sistemas) {
      const chave = s.sistema;
      const atual = m.get(chave) ?? { chave, s, casas: [] };
      atual.casas.push({ casa: c, s });
      m.set(chave, atual);
    }
  return [...m.values()].sort((a, b) => b.casas.length - a.casas.length || a.chave.localeCompare(b.chave, "pt-BR"));
}

function anos(de: number, ate: number) {
  return de === ate ? String(de) : `${de}–${ate}`;
}

export default function PaginaCobertura() {
  const cob = cobertura();
  const lista = casas();
  const sistemas = porSistema(lista);
  const coletadas = lista.filter((c) => c.situacao === "coletada").length;
  const camaras = lista.filter((c) => c.tipo === "camara_municipal");
  const assembleias = lista.filter((c) => c.tipo === "assembleia");
  const coleta = lista.map((c) => c.p.coleta).sort().at(-1) ?? "";
  const lev = cob.levantamento;
  const camarasDo = (k: string) => camaras.filter((c) => c.sistemas.some((s) => s.fornecedor === FORNECEDOR_DO_SISTEMA[k])).length;

  const classesPr = new Map<string, Classe>(cob.camaras_pr.map((c) => [String(c.ibge), classe(c.situacao, c.motivo)]));
  const classesBr = new Map<string, Classe>(cob.assembleias.map((a) => [a.uf, classe(a.situacao, a.motivo)]));

  const linhas: LinhaCobertura[] = [
    ...cob.federal.map((f) => ({
      grupo: "federal" as const,
      id: f.id,
      nome: f.nome,
      onde: "Brasil",
      fornecedor: f.id === "camara-deputados" ? "Dados abertos da Câmara (API e arquivo anual)" : null,
      classe: classe(f.situacao, f.motivo),
      situacao: f.situacao,
      motivo: f.motivo ?? null,
      detalhe: null,
      href: f.id === "camara-deputados" ? "/parlamentares/#casa-camara-deputados" : null,
      parlamentares: f.parlamentares,
      linhas: f.linhas,
    })),
    ...cob.assembleias.map((a) => ({
      grupo: "assembleia" as const,
      id: `al-${a.uf.toLowerCase()}`,
      nome: a.nome,
      onde: `${a.sigla} · ${inteiro(a.cadeiras)} cadeiras`,
      fornecedor: a.sistema,
      classe: classe(a.situacao, a.motivo),
      situacao: a.situacao,
      motivo: a.motivo,
      detalhe: a.detalhe,
      href: a.casa ? `/casas/${a.casa}/` : null,
      parlamentares: a.parlamentares,
      linhas: a.linhas,
    })),
    ...cob.camaras_pr.map((c) => ({
      grupo: "camara" as const,
      id: String(c.ibge),
      nome: `Câmara de ${c.municipio}`,
      onde: "",
      fornecedor: c.fornecedor,
      classe: classe(c.situacao, c.motivo),
      situacao: c.situacao,
      motivo: c.motivo,
      detalhe: c.detalhe ?? null,
      href: c.casa ? `/casas/${c.casa}/` : null,
      parlamentares: c.parlamentares,
      linhas: c.linhas,
    })),
  ];

  return (
    <div className="mx-auto max-w-[1180px] px-4 py-8 sm:px-8 sm:py-10">
      <PadroesMapa />
      <header className="max-w-[72ch]">
        <h1 className="font-titulo text-[2.4rem] font-medium leading-[1.04] tracking-[-0.02em] sm:text-[3.2rem]">Cobertura</h1>
        <p className="mt-3 text-[1.05rem] leading-relaxed text-tinta-2">
          Cada casa legislativa publica os gastos num sistema diferente, e muitas casas usam o mesmo fornecedor. O robô tem um adaptador por
          sistema, e cada adaptador atende todas as casas daquele sistema. Esta página mostra quais casas já estão aqui, por qual sistema, e
          por que as outras ainda não estão.
        </p>
      </header>

      <p className="mt-8 max-w-[34ch] text-balance font-titulo text-[1.7rem] font-medium leading-[1.15] tracking-[-0.01em] sm:text-[2.1rem]">
        <span className="num">{inteiro(coletadas)}</span> casas coletadas, em <span className="num">{inteiro(sistemas.length)}</span> sistemas
        diferentes.
      </p>
      <p className="num mt-3 max-w-[70ch] text-tinta-2">
        A Câmara dos Deputados, {assembleias.length === 1 ? "1 assembleia" : `${assembleias.length} assembleias`} ({listaE(assembleias.map((a) => a.uf))}) e{" "}
        {camaras.length} câmaras municipais do Paraná: {inteiro(cob.medidas.parlamentares)} parlamentares e {inteiro(cob.medidas.linhas)} linhas
        de despesa que passaram na conferência. Coleta de {data(coleta)}.
      </p>

      <section aria-labelledby="sistemas" className="mt-14">
        <h2 id="sistemas" className="font-titulo text-2xl font-medium">
          Um robô por sistema
        </h2>
        <p className="mt-1 max-w-[70ch] text-sm text-tinta-3">
          Cada ficha é um adaptador da coleta: o sistema, como ele é lido, e as casas que ele atende. Casa nova num sistema que já tem adaptador
          é uma linha na configuração, sem código novo.
        </p>
        <ol className="mt-5 grid gap-3 md:grid-cols-2">
          {sistemas.map((g, i) => (
            <li
              key={g.chave}
              className={`rounded-[3px] bg-manilha px-4 py-3.5 text-manilha-tinta ${g.casas.length > 3 ? "md:col-span-2" : ""}`}
              style={{ marginLeft: `${(i % 2) * 6}px` }}
            >
              <h3 className="font-titulo text-[1.05rem] font-semibold leading-tight">{g.s.sistema}</h3>
              <p className="mt-0.5 text-[0.8rem] text-manilha-tinta-2">
                {g.s.fornecedor} · {MODO[g.s.modo] ?? g.s.modo} · {g.casas.length === 1 ? "1 casa" : `${g.casas.length} casas`}
              </p>
              <ul className={`mt-2.5 text-[0.88rem] ${g.casas.length > 3 ? "columns-1 gap-6 sm:columns-2 lg:columns-3" : ""}`}>
                {g.casas.map(({ casa: c, s }) => (
                  <li key={`${c.id}-${s.fonte}`} className="break-inside-avoid py-0.5">
                    {c.id === "camara-deputados" ? (
                      <span>Câmara dos Deputados</span>
                    ) : (
                      <Link href={`/casas/${c.id}/`} className="underline decoration-manilha-tinta/35 underline-offset-[3px] hover:decoration-manilha-tinta">
                        {c.tipo === "camara_municipal" ? c.municipio : c.nome}
                      </Link>
                    )}{" "}
                    <span className="num text-manilha-tinta-2">{anos(s.de, s.ate)}</span>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="mapas" className="mt-16">
        <h2 id="mapas" className="font-titulo text-2xl font-medium">
          Onde estão
        </h2>
        <div className="mt-5 grid gap-x-12 gap-y-10 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <div>
            <h3 className="font-titulo text-lg font-medium">Paraná, câmara por câmara</h3>
            <p className="mt-1 text-sm text-tinta-3">
              As <span className="num">{inteiro(cob.camaras_pr.length)}</span> câmaras municipais. O fornecedor de cada uma vem do levantamento de{" "}
              {data(lev.data)}; a situação das coletadas, da coleta.
            </p>
            <MapaCobertura
              className="mt-4"
              mapa={mapa("pr")}
              arquivo="/mapas/pr.svg"
              classes={classesPr}
              descricao={`Mapa do Paraná por município: ${camaras.length} câmaras coletadas; as demais estão na tabela abaixo, com o motivo.`}
            />
          </div>
          <div>
            <h3 className="font-titulo text-lg font-medium">Brasil, assembleia por assembleia</h3>
            <p className="mt-1 text-sm text-tinta-3">As 27 casas legislativas estaduais, pelo levantamento de {data(lev.data)}.</p>
            <MapaCobertura
              className="mt-4 max-w-[420px]"
              mapa={mapa("br")}
              arquivo="/mapas/br.svg"
              classes={classesBr}
              descricao={`Mapa do Brasil por estado: ${assembleias.length} assembleias coletadas; as demais estão na tabela abaixo, com o motivo.`}
            />
          </div>
        </div>
      </section>

      <section aria-labelledby="levantamento" className="mt-16">
        <h2 id="levantamento" className="font-titulo text-2xl font-medium">
          O levantamento das câmaras do Paraná
        </h2>
        <p className="mt-1 max-w-[70ch] text-sm text-tinta-3">
          Antes de construir os adaptadores, um levantamento de {data(lev.data)} procurou o fornecedor do portal de transparência de cada uma
          das {inteiro(lev.camaras_pr.total)} câmaras: pelo endereço que os fornecedores usam, pela página inicial de cada site e pelas listas
          dos próprios fornecedores. São contagens do levantamento, não da coleta: a coleta só diz das câmaras acima.
        </p>
        <table className="mt-5 w-full max-w-[760px] text-left text-[0.92rem]">
          <caption className="sr-only">Câmaras do Paraná por fornecedor do portal, no levantamento</caption>
          <thead className="text-[0.78rem] text-tinta-3">
            <tr className="border-b border-aco-2">
              <th scope="col" className="py-2 pr-4 font-normal">
                Fornecedor do portal
              </th>
              <th scope="col" className="py-2 pr-4 text-right font-normal">
                Câmaras
              </th>
              <th scope="col" className="py-2 font-normal">
                Na coleta
              </th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(lev.camaras_pr.por_fornecedor).map(([k, n]) => (
              <tr key={k} className="border-b border-aco">
                <td className="py-2 pr-4 text-tinta">{NOME_FORN[k] ?? k}</td>
                <td className="num py-2 pr-4 text-right text-tinta">{inteiro(n)}</td>
                <td className="py-2 text-tinta-2">
                  {FORNECEDOR_DO_SISTEMA[k] ? `${ADAPTADOR[k]}: ${camarasDo(k)} câmaras coletadas` : ADAPTADOR[k]}
                </td>
              </tr>
            ))}
            <tr className="border-b border-aco">
              <td className="py-2 pr-4 text-tinta">Sem fornecedor identificado</td>
              <td className="num py-2 pr-4 text-right text-tinta">{inteiro(lev.camaras_pr.sem_fornecedor_identificado)}</td>
              <td className="py-2 text-tinta-2">{MOTIVO_FORA.nao_identificado}</td>
            </tr>
          </tbody>
        </table>
        <p className="mt-3 max-w-[70ch] text-sm text-tinta-3">
          Além disso, <span className="num">{inteiro(lev.camaras_pr.robots_proibe_tudo)}</span> câmaras têm um robots.txt que proíbe qualquer
          robô no site inteiro, e ficam de fora por isso. O levantamento nomeia o fornecedor de{" "}
          <span className="num">{inteiro(lev.camaras_com_fornecedor_nomeado)}</span> câmaras, município a município; as outras aparecem na
          tabela como “não identificado”.
        </p>
      </section>

      <section aria-labelledby="todas" className="mt-16">
        <h2 id="todas" className="font-titulo text-2xl font-medium">
          Todas as casas
        </h2>
        <p className="mt-1 max-w-[70ch] text-sm text-tinta-3">
          Captcha, Cloudflare e login nunca são contornados, e o robots.txt de cada portal é respeitado: a casa que barra o robô fica de fora,
          com o motivo.
        </p>
        <div className="mt-5">
          <TabelaCobertura linhas={linhas} />
        </div>
      </section>
    </div>
  );
}
