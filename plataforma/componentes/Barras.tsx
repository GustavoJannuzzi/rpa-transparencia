import Valor from "@/componentes/Valor";
import { proporcao } from "@/lib/formato";
import type { Procedencia } from "@/lib/tipos";

export type ItemBarra = { chave: string; valor: string; p: Procedencia };

/** Barras horizontais: o comprimento é só desenho; o número exibido é o texto
 * exato, e cada barra leva a procedência da sua própria soma. */
export default function Barras({ itens, rotulos }: { itens: ItemBarra[]; rotulos?: Record<string, string> }) {
  const naoNegativos = itens.filter((i) => !i.valor.startsWith("-"));
  const max = naoNegativos.reduce((m, i) => (Number(i.valor) > Number(m) ? i.valor : m), "0");
  return (
    <ul className="space-y-2.5">
      {itens.map((i) => (
        <li key={i.chave} className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-4">
          <span className="text-[0.92rem] text-tinta-2">{rotulos?.[i.chave] ?? i.chave}</span>
          <Valor valor={i.valor} p={i.p} />
          <span className="col-span-2 mt-1 block h-1.5 rounded-full bg-gaveta-3">
            <span className="block h-full rounded-full bg-manilha/80" style={{ width: `${Math.max(0.6, proporcao(i.valor, max) * 100)}%` }} />
          </span>
        </li>
      ))}
    </ul>
  );
}
