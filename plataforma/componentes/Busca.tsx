"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ItemIndice } from "@/lib/tipos";

function norm(s: string) {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

export default function Busca({ aoEscolher }: { aoEscolher?: (id: string) => boolean }) {
  const [itens, setItens] = useState<ItemIndice[] | null>(null);
  const [q, setQ] = useState("");
  const [aberta, setAberta] = useState(false);
  const [ativo, setAtivo] = useState(0);
  const router = useRouter();
  const caixa = useRef<HTMLDivElement>(null);

  const carregar = () => {
    if (itens) return;
    fetch("/dados/parlamentares.json")
      .then((r) => r.json())
      .then(setItens)
      .catch(() => setItens([]));
  };

  const achados = useMemo(() => {
    if (!itens || q.trim().length < 2) return [];
    const t = norm(q.trim());
    return itens.filter((i) => norm(i.nome).includes(t)).slice(0, 8);
  }, [itens, q]);

  useEffect(() => {
    const fora = (e: MouseEvent) => caixa.current && !caixa.current.contains(e.target as Node) && setAberta(false);
    document.addEventListener("mousedown", fora);
    return () => document.removeEventListener("mousedown", fora);
  }, []);

  const ir = (id: string) => {
    setAberta(false);
    setQ("");
    if (aoEscolher && aoEscolher(id)) return;
    router.push(`/parlamentares/${id}/`);
  };

  return (
    <div ref={caixa} className="relative w-full sm:w-80">
      <label htmlFor="busca" className="sr-only">
        Buscar deputado ou vereador
      </label>
      <input
        id="busca"
        type="search"
        autoComplete="off"
        placeholder="Buscar deputado ou vereador"
        value={q}
        onFocus={() => {
          carregar();
          setAberta(true);
        }}
        onChange={(e) => {
          setQ(e.target.value);
          setAtivo(0);
          setAberta(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") setAtivo((a) => Math.min(a + 1, achados.length - 1));
          if (e.key === "ArrowUp") setAtivo((a) => Math.max(a - 1, 0));
          if (e.key === "Enter" && achados[ativo]) ir(achados[ativo].id);
          if (e.key === "Escape") setAberta(false);
        }}
        role="combobox"
        aria-expanded={aberta && achados.length > 0}
        aria-controls="busca-lista"
        className="h-10 w-full rounded-md border border-aco-2 bg-gaveta-2 px-3.5 text-[0.95rem] text-tinta placeholder:text-tinta-3 focus:border-carimbo focus:outline-none"
      />
      {aberta && q.trim().length >= 2 && (
        <ul
          id="busca-lista"
          role="listbox"
          className="absolute right-0 top-full z-50 mt-1.5 w-full overflow-hidden rounded-md border border-aco-2 bg-gaveta-2 shadow-[0_14px_30px_-10px_rgba(0,0,0,0.7)]"
        >
          {itens === null && <li className="px-3.5 py-2.5 text-sm text-tinta-3">Abrindo o índice…</li>}
          {itens !== null && achados.length === 0 && (
            <li className="px-3.5 py-2.5 text-sm text-tinta-3">Nenhum parlamentar com esse nome no índice.</li>
          )}
          {achados.map((i, n) => (
            <li key={i.id} role="option" aria-selected={n === ativo}>
              <button
                type="button"
                onMouseEnter={() => setAtivo(n)}
                onClick={() => ir(i.id)}
                className={`flex w-full items-baseline justify-between gap-3 px-3.5 py-2 text-left ${n === ativo ? "bg-gaveta-3" : ""}`}
              >
                <span className="text-[0.95rem]">{i.nome}</span>
                <span className="shrink-0 text-xs text-tinta-3">
                  {i.partido ?? "sem partido"} · {i.casa === "cmc" ? "Curitiba" : i.uf}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
