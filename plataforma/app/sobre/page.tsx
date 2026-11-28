import type { Metadata } from "next";
import Link from "next/link";
import { revisao } from "@/lib/dados";
import { MODO } from "@/lib/fontes";
import { contagem, listaE } from "@/lib/formato";
import { assembleias, camarasPorSistema } from "@/lib/resumo";
import { metadadosDaPagina } from "@/lib/site";

export const metadata: Metadata = metadadosDaPagina({
  title: "Sobre",
  description: "Plataforma independente e não oficial: de onde vêm os dados, as regras da conferência e o que ficou de fora.",
  caminho: "/sobre/",
});

export default function Sobre() {
  // as casas e os sistemas vêm dos dados publicados: casa nova entra sem editar esta página
  const camaras = camarasPorSistema();
  const outrasCamaras = camaras.reduce((s, c) => s + c.camaras, 0);
  const porModo = new Map<string, string[]>();
  for (const a of assembleias()) porModo.set(a.modo, [...(porModo.get(a.modo) ?? []), a.uf]);
  const divergentes = revisao()
    .grupos.filter((g) => g.tipo === "api_x_arquivo")
    .flatMap((g) => g.exemplos.map((e) => e.chave))
    .concat()
    .sort()
    .map((c) => {
      const [cat, ano] = c.split("/");
      return `${cat.replace(/\.$/, "").toLowerCase()} (${ano})`;
    });
  return (
    <article className="mx-auto max-w-[760px] px-4 py-8 sm:px-8 sm:py-12">
      <h1 className="font-titulo text-[2.4rem] font-medium leading-tight tracking-[-0.02em]">Sobre</h1>
      <div className="mt-6 space-y-5 text-[1.03rem] leading-relaxed text-tinta-2 [&_h2]:mt-10 [&_h2]:font-titulo [&_h2]:text-xl [&_h2]:font-medium [&_h2]:text-tinta [&_strong]:font-medium [&_strong]:text-tinta">
        <p>
          Esta é uma plataforma <strong>independente e não oficial</strong>. Não tem vínculo com a Câmara dos Deputados, com as
          assembleias, com as câmaras municipais, com as prefeituras nem com o TSE. Usa só dados que esses órgãos publicam.
        </p>

        <h2>De onde vêm os dados</h2>
        <ul className="list-disc space-y-2 pl-5">
          <li>Câmara dos Deputados: API de Dados Abertos (lista de deputados) e arquivo anual da cota parlamentar (despesas).</li>
          <li>
            Câmara Municipal de Curitiba: o portal legado (relatórios em PDF, 2013–2016), o Elotech (API pública, 2017–2023), o
            portal de transparência da Prefeitura (2024–2025) e o Betha (2026).
          </li>
          <li>
            Mais {contagem(outrasCamaras, "câmara municipal", "câmaras municipais")} do Paraná, um adaptador por sistema, cada câmara
            configurada pela sua entidade:{" "}
            {listaE(camaras.map((c) => `${c.sistema} (${contagem(c.camaras, "câmara", "câmaras")}, ${MODO[c.modo] ?? c.modo})`))}.
          </li>
          <li>
            Assembleias legislativas (o período de cada uma está na Cobertura):{" "}
            {listaE([...porModo.entries()].map(([modo, ufs]) => `${listaE(ufs)} por ${MODO[modo] ?? modo}`))}.
          </li>
          <li>Atividade nas sessões (presença, ausência e voto): o SAPL (Interlegis) das câmaras que o publicam e os relatórios de frequência da Câmara de Curitiba.</li>
          <li>TSE: dados abertos de candidaturas, para o partido de cada vereador na eleição do mandato.</li>
        </ul>
        <p>
          Que casas estão aqui, por qual sistema, e por que as outras ainda não estão:{" "}
          <Link href="/cobertura/" className="text-carimbo-claro underline">
            Cobertura
          </Link>
          .
        </p>
        <p>
          O passo a passo, a conferência de cada fonte e a fila de revisão estão em{" "}
          <Link href="/como-os-dados-chegam-aqui/" className="text-carimbo-claro underline">
            Como os dados chegam aqui
          </Link>
          .
        </p>

        <h2>Regras</h2>
        <ul className="list-disc space-y-2 pl-5">
          <li>Só aparece o que passou na conferência. O que não fecha vai para a fila de revisão, fora dos totais.</li>
          <li>Nenhum número é completado nem arredondado. Todo valor tem a ficha: fonte, data da coleta e documento oficial.</li>
          <li>
            Neutralidade: não há ranking de quem gasta mais, nem adjetivo. Fornecedor em comum não insinua nada; só mostra que
            duas pessoas contrataram a mesma empresa.
          </li>
          <li>
            Pessoas: parlamentar aparece pelo nome. Assessor e servidor aparecem só em totais (custo do gabinete, diárias de
            servidores), nunca pelo nome. Fornecedor pessoa física aparece com o CPF mascarado e não entra no grafo.
          </li>
          <li>
            Coleta educada: uma requisição por vez em cada portal, com pausa, respeitando o robots.txt. Portal com captcha ou
            login fica de fora; captcha nunca é contornado.
          </li>
        </ul>

        <h2>O que ficou de fora, e por quê</h2>
        <ul className="list-disc space-y-2 pl-5">
          <li>Assembleia Legislativa do Paraná: a consulta da verba pede “Não sou um robô”, e o robots.txt proíbe a API.</li>
          <li>
            Câmaras que usam o IPM Atende.net (Colombo, Araucária, Cascavel e outras): o robots.txt proíbe a consulta, e ela ainda
            passa por um desafio da Cloudflare. As do Inga Digital: o robots.txt proíbe o portal inteiro.
          </li>
          <li>Londrina e outras câmaras: o robots.txt do site proíbe qualquer robô.</li>
          <li>Pessoal de gabinete dos deputados federais: as páginas estão bloqueadas pelo robots.txt da Câmara.</li>
        </ul>

        <h2>Limites que vale saber</h2>
        <ul className="list-disc space-y-2 pl-5">
          <li>O partido de vereador é o da eleição que deu o mandato; troca de partido no meio do mandato não está na fonte.</li>
          <li>
            Deputado estadual: o partido é o da lista de deputados da própria assembleia (a CLDF não publica partido). A ALESP
            publica a despesa já somada por fornecedor, tipo e mês: cada linha de São Paulo é uma soma, não uma nota.
          </li>
          <li>O Betha publica o valor previsto da diária; o portal da Prefeitura, o valor empenhado. Cada um aparece com o seu rótulo.</li>
          {divergentes.length > 0 && (
            <li>
              Na conferência por amostra, o arquivo anual e a API da Câmara não bateram nestas categorias, que ficam em revisão
              e fora dos totais: {divergentes.join("; ")}.
            </li>
          )}
        </ul>
      </div>
    </article>
  );
}
