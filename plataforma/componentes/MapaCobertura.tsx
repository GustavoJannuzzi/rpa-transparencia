import { type Classe, ORDEM_CLASSE, PREENCHIMENTO, ROTULO_CLASSE } from "@/lib/cobertura";
import { inteiro } from "@/lib/formato";
import type { Mapa } from "@/lib/tipos";

/** As hachuras do mapa e da legenda: sépia para revisão, contorno para o portal que barra o robô. */
export function PadroesMapa() {
  return (
    <svg width="0" height="0" aria-hidden="true" focusable="false" className="absolute">
      <defs>
        <pattern id="hachura-revisao" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="5" height="5" fill="var(--color-gaveta-3)" />
          <line x1="0" y1="0" x2="0" y2="5" stroke="var(--color-sepia-claro)" strokeWidth="2.2" />
        </pattern>
        <pattern id="hachura-barrada" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">
          <rect width="5" height="5" fill="var(--color-gaveta-3)" />
          <line x1="0" y1="0" x2="0" y2="5" stroke="var(--color-contorno)" strokeWidth="1.4" />
        </pattern>
      </defs>
    </svg>
  );
}

export function Amostra({ classe }: { classe: Classe }) {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" focusable="false" className="shrink-0">
      <rect x="0.5" y="0.5" width="13" height="13" rx="2" fill={PREENCHIMENTO[classe]} stroke="var(--color-aco-2)" />
    </svg>
  );
}

/** Mapa estático (a malha do IBGE vira caminho de SVG no publicar). Não é interativo:
 * a tabela abaixo é a forma de navegar, e o mapa diz por extenso o que mostra. */
export default function MapaCobertura({
  mapa,
  classes,
  nomes,
  titulo,
  descricao,
  className = "",
}: {
  mapa: Mapa;
  classes: Map<string, Classe>;
  nomes: Map<string, string>;
  titulo: string;
  descricao: string;
  className?: string;
}) {
  const contagem = new Map<Classe, number>();
  for (const a of mapa.areas) {
    const c = classes.get(String(a.id)) ?? "outra";
    contagem.set(c, (contagem.get(c) ?? 0) + 1);
  }
  const idTitulo = `mapa-${titulo.replace(/[^a-z]/gi, "").toLowerCase()}`;
  return (
    <figure className={className}>
      <svg viewBox={mapa.viewBox} role="img" aria-labelledby={idTitulo} className="h-auto w-full" preserveAspectRatio="xMidYMid meet">
        <title id={idTitulo}>{`${titulo}. ${descricao}`}</title>
        {mapa.areas.map((a) => {
          const c = classes.get(String(a.id)) ?? "outra";
          return (
            <path
              key={a.id}
              d={a.d}
              fill={PREENCHIMENTO[c]}
              stroke={c === "coletada" ? "var(--color-gaveta)" : "var(--color-aco)"}
              strokeWidth={c === "coletada" ? 1.2 : 0.6}
              strokeLinejoin="round"
            >
              <title>{`${nomes.get(String(a.id)) ?? a.id}: ${ROTULO_CLASSE[c].toLowerCase()}`}</title>
            </path>
          );
        })}
      </svg>
      <figcaption className="mt-3">
        <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-[0.82rem] text-tinta-2">
          {ORDEM_CLASSE.filter((c) => contagem.get(c)).map((c) => (
            <li key={c} className="flex items-center gap-1.5">
              <Amostra classe={c} />
              <span>
                {ROTULO_CLASSE[c]} <span className="num text-tinta-3">({inteiro(contagem.get(c) ?? 0)})</span>
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-[0.78rem] text-tinta-3">
          Malha: {mapa.fonte}, baixada em {mapa.baixado_em.split("-").reverse().join("/")}.
        </p>
      </figcaption>
    </figure>
  );
}
