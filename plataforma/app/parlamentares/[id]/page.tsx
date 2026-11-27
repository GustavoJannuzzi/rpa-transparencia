import type { Metadata } from "next";
import Link from "next/link";
import { AtividadeDoParlamentar } from "@/componentes/Atividade";
import Barras, { type ItemBarra } from "@/componentes/Barras";
import { ForaDaSoma, SecaoEmRevisao } from "@/componentes/EmRevisao";
import TabelaDespesas from "@/componentes/TabelaDespesas";
import Valor from "@/componentes/Valor";
import { casaDe, categorias, indice, parlamentar, vistaNoGrafo } from "@/lib/dados";
import { nomeFonte } from "@/lib/fontes";
import { cargoNome, casaNome, contagem, data, mes, tipoDaCasa } from "@/lib/formato";
import { metadadosDaPagina } from "@/lib/site";
import type { Procedencia } from "@/lib/tipos";

export const dynamicParams = false;

export function generateStaticParams() {
  return indice().map((i) => ({ id: i.id }));
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const p = parlamentar(id);
  const quem = cargoNome(p.casa, p.municipio, p.uf).toLowerCase();
  const [de, ate] = [Math.min(...p.anos), Math.max(...p.anos)];
  const periodo = !p.anos.length ? "" : de === ate ? `, ${de}` : `, de ${de} a ${ate}`;
  const oque = tipoDaCasa(p.casa) === "municipal" ? "Diárias conferidas" : "Despesas conferidas";
  return metadadosDaPagina({
    title: p.nome,
    description: `${oque} de ${p.nome}, ${quem}${p.partido ? ` (${p.partido})` : ""}${periodo}, com a fonte de cada número e o que ficou em revisão.`,
    caminho: `/parlamentares/${p.id}/`,
  });
}

function slug(s: string) {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

export default async function PaginaParlamentar({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const p = parlamentar(id);
  const vereador = tipoDaCasa(p.casa) === "municipal";
  const casa = casaDe(p.casa);
  const agregado = p.granularidade === "agregado";
  const unidade = vereador ? ["diária", "diárias"] : agregado ? ["linha agregada", "linhas agregadas"] : ["despesa", "despesas"];
  const noGrafo = vistaNoGrafo(p.id);
  const rot = categorias();
  const coleta = Object.values(p.p.coleta).sort().at(-1) ?? "";
  const proc: Procedencia = { fontes: p.fontes, coleta, situacao: "soma", linhas: p.linhas };
  // cada soma parcial com as fontes e as linhas que de fato entraram nela
  const recorte = (r: { fontes: string[]; linhas: number } | undefined): Procedencia => ({
    fontes: r?.fontes ?? p.fontes,
    coleta: (r?.fontes ?? p.fontes).map((f) => p.p.coleta[f] ?? "").sort().at(-1) ?? coleta,
    situacao: "soma",
    linhas: r?.linhas,
  });
  const cats: ItemBarra[] = Object.entries(p.por_categoria)
    .filter(([k]) => k && k !== "null")
    .map(([k, v]) => ({ chave: k, valor: v, p: recorte(p.procedencia_categoria?.[k]) }));
  const anos: ItemBarra[] = Object.entries(p.por_ano)
    .sort(([a], [b]) => Number(b) - Number(a))
    .map(([k, v]) => ({ chave: k, valor: v, p: recorte(p.procedencia_ano?.[k]) }));

  return (
    <article className="mx-auto max-w-[1180px] px-4 py-8 sm:px-8 sm:py-10">
      <p className="text-sm text-tinta-3">
        <Link href="/parlamentares/" className="underline hover:text-tinta">
          Parlamentares
        </Link>{" "}
        /{" "}
        {casa && p.casa !== "camara-deputados" ? (
          <Link href={`/casas/${p.casa}/`} className="underline hover:text-tinta">
            {casa.nome}
          </Link>
        ) : (
          (p.uf ?? casaNome(p.casa, p.municipio))
        )}
      </p>
      <header className="mt-3 grid gap-6 border-b border-aco pb-8 md:grid-cols-[1fr_auto] md:items-end">
        <div>
          <h1 className="font-titulo text-[2.4rem] font-medium leading-[1.02] tracking-[-0.02em] sm:text-[3.2rem]">{p.nome}</h1>
          <p className="mt-2 text-tinta-2">
            {cargoNome(p.casa, p.municipio, p.uf)}
            {p.casa === "camara-deputados" && p.uf ? ` · ${p.uf}` : ""}
            {p.partido ? (
              <>
                {" · "}
                <Link href={`/partidos/${slug(p.partido)}/`} className="underline hover:text-tinta">
                  {p.partido}
                </Link>
              </>
            ) : vereador || p.casa === "camara-deputados" ? (
              " · partido em revisão"
            ) : (
              " · a fonte não informa o partido"
            )}
            {p.nome_civil && p.nome_civil !== p.nome ? ` · nome civil: ${p.nome_civil}` : ""}
          </p>
          {noGrafo && (
            <p className="mt-2 text-sm">
              <Link href={`/?vista=${noGrafo}&no=${p.id}`} className="text-carimbo-claro underline">
                Ver {p.nome} no grafo
              </Link>
            </p>
          )}
        </div>
        <div className="md:text-right">
          {p.linhas > 0 ? (
            <>
              <p className="text-sm text-tinta-3">
                {vereador ? "Diárias conferidas" : "Total conferido"}
                {p.anos.length ? `, ${Math.min(...p.anos)}–${Math.max(...p.anos)}` : ""}
              </p>
              <Valor valor={p.total} p={proc} tamanho="grande" />
              <p className="num mt-1 text-sm text-tinta-3">
                {contagem(p.linhas, unidade[0], unidade[1])} · {p.fontes.map(nomeFonte).join(" · ")}
              </p>
            </>
          ) : (
            <p className="font-titulo text-2xl text-tinta-3">{vereador ? "Nenhuma diária conferida" : "Nenhuma despesa conferida"}</p>
          )}
          {agregado && (
            <p className="mt-2 max-w-[44ch] text-sm leading-relaxed text-tinta-3 md:ml-auto">
              A fonte publica a despesa já somada por fornecedor, tipo e mês. Cada linha é uma soma feita pela fonte, não uma nota.
            </p>
          )}
        </div>
        <ForaDaSoma p={p} />
      </header>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-10 py-8 lg:grid-cols-[minmax(0,1fr)_340px]">
        <aside aria-label="Resumo" className="min-w-0 space-y-10 lg:col-start-2 lg:row-start-1">
          {anos.length > 0 && (
            <section aria-labelledby="por-ano">
              <h2 id="por-ano" className="font-titulo text-lg font-medium">
                Por ano
              </h2>
              <div className="mt-3">
                <Barras itens={anos} />
              </div>
            </section>
          )}
          {cats.length > 0 && (
            <section aria-labelledby="por-cat">
              <h2 id="por-cat" className="font-titulo text-lg font-medium">
                Por categoria
              </h2>
              <div className="mt-3">
                <Barras itens={cats} rotulos={rot} />
              </div>
            </section>
          )}
          <SecaoEmRevisao p={p} />
          <AtividadeDoParlamentar atividade={p.atividade ?? []} nome={p.nome} />
          {(p.subsidio?.length ?? 0) > 0 && (
            <section aria-labelledby="subsidio">
              <h2 id="subsidio" className="font-titulo text-lg font-medium">
                Subsídio
              </h2>
              <p className="mt-1 text-sm text-tinta-3">
                O que o cadastro de pessoal da Câmara diz que o vereador recebe, na data da coleta. Retrato de um dia, não a soma do ano.
              </p>
              <ul className="mt-3 space-y-3">
                {p.subsidio!.map((s) => (
                  <li key={`${s.fonte}-${s.competencia}`} className="border-t border-aco pt-3">
                    <p className="text-sm text-tinta-2">
                      {s.rotulo} · {data(s.data_referencia)}
                    </p>
                    <Valor
                      valor={s.valor}
                      tamanho="medio"
                      p={{ fontes: [s.fonte], coleta: s.k, documento: s.src, local: s.loc, situacao: "conferido", nota: `${s.cargo ?? "vereador"} no cadastro de pessoal em ${data(s.data_referencia)}` }}
                    />
                  </li>
                ))}
              </ul>
            </section>
          )}
          {p.gabinete.length > 0 && (
            <section aria-labelledby="gabinete">
              <h2 id="gabinete" className="font-titulo text-lg font-medium">
                Custo do gabinete
              </h2>
              <p className="mt-1 text-sm text-tinta-3">
                Soma do que recebe quem está lotado no gabinete, sem o nome de ninguém.
                {p.gabinete.length > 1
                  ? " Os dois sistemas da Câmara medem coisas diferentes, por isso aparecem os dois, cada um com o seu rótulo."
                  : p.gabinete[0]?.nota
                    ? ` ${p.gabinete[0].nota.charAt(0).toUpperCase()}${p.gabinete[0].nota.slice(1)}.`
                    : ""}
              </p>
              <ul className="mt-3 space-y-3">
                {p.gabinete.map((g) => (
                  <li key={g.fonte} className="border-t border-aco pt-3">
                    <p className="text-sm text-tinta-2">
                      {g.rotulo} ({nomeFonte(g.fonte).split(" — ")[1] ?? nomeFonte(g.fonte)}) · {mes(g.competencia)}
                    </p>
                    <Valor
                      valor={g.custo}
                      tamanho="medio"
                      p={{ fontes: [g.fonte], coleta: g.k, documento: g.src, situacao: "soma", nota: `${g.pessoas} pessoas lotadas em "${g.lotacao}" em ${data(g.data_referencia)}` }}
                    />
                    <p className="num text-sm text-tinta-3">{g.pessoas} pessoas</p>
                  </li>
                ))}
              </ul>
            </section>
          )}
          <section aria-labelledby="partidos-hist">
            <h2 id="partidos-hist" className="font-titulo text-lg font-medium">
              Partido ao longo do tempo
            </h2>
            {p.filiacoes.length ? (
              <ul className="mt-3 space-y-2 text-sm">
                {p.filiacoes.map((f, i) => (
                  <li key={i} className="border-t border-aco pt-2">
                    <span className="font-medium text-tinta">{f.partido}</span>{" "}
                    <span className="num text-tinta-3">
                      {f.desde ? mes(f.desde) : "?"} a {f.ate ? mes(f.ate) : "?"}
                    </span>
                    <span className="block text-tinta-3">{f.base}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-sm text-tinta-3">
                {vereador
                  ? "Partido em revisão: o nome não fechou com o cadastro do TSE."
                  : p.casa === "camara-deputados"
                    ? "Partido em revisão."
                    : "A fonte desta casa não informa o partido do deputado."}
              </p>
            )}
          </section>
          {p.top_fornecedores.length > 0 && (
            <section aria-labelledby="fornecedores">
              <h2 id="fornecedores" className="font-titulo text-lg font-medium">
                Fornecedores mais frequentes
              </h2>
              <ul className="mt-3 space-y-1.5 text-sm">
                {p.top_fornecedores.map((f) => (
                  <li key={f.doc} className="flex justify-between gap-3 border-t border-aco pt-1.5">
                    <span className="text-tinta-2">{f.nome ?? f.doc}</span>
                    <span className="num shrink-0 text-tinta-3">
                      {f.linhas} {agregado ? (f.linhas === 1 ? "linha" : "linhas") : f.linhas === 1 ? "nota" : "notas"}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </aside>

        <section aria-labelledby="despesas" className="min-w-0 lg:col-start-1 lg:row-start-1">
          <h2 id="despesas" className="font-titulo text-2xl font-medium">
            {agregado ? "Despesas, como a fonte publica" : "Despesas, uma a uma"}
          </h2>
          <p className="mt-1 max-w-[70ch] text-sm text-tinta-3">
            Clique num valor para ver a ficha: fonte, data da coleta e o documento oficial. Linhas que a conferência mandou
            para revisão não aparecem aqui
            {p.em_revisao.length || p.periodos_em_revisao?.length ? (
              <>
                {" "}
                (estão contadas em{" "}
                <a href="#em-revisao" className="underline hover:text-tinta">
                  Em revisão
                </a>
                )
              </>
            ) : null}
            ; as que a própria fonte não soma aparecem riscadas.
          </p>
          <div className="mt-5">
            <TabelaDespesas id={p.id} anos={p.anos} rotulos={rot} />
          </div>
        </section>
      </div>
    </article>
  );
}
