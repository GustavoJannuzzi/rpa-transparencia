"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { ItemIndice } from "@/lib/tipos";

function norm(s: string) {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

/** Quem começa com o termo vem antes de quem só o contém no meio ("zé" acha Zé antes de Trzeciak). */
export function buscar(itens: ItemIndice[], termo: string, limite = 8): ItemIndice[] {
  const t = norm(termo.trim());
  if (t.length < 2) return [];
  const pontos = (nome: string) => {
    const n = norm(nome);
    if (n.startsWith(t)) return 0;
    if (n.split(/[\s-]+/).some((p) => p.startsWith(t))) return 1;
    return n.includes(t) ? 2 : -1;
  };
  return itens
    .map((i, ordem) => ({ i, p: pontos(i.nome), ordem }))
    .filter((x) => x.p >= 0)
    .sort((a, b) => a.p - b.p || a.ordem - b.ordem)
    .slice(0, limite)
    .map((x) => x.i);
}

type Props = {
  /** Se devolver true, a escolha foi tratada (por exemplo, mostrar no grafo) e a busca não navega. */
  aoEscolher?: (item: ItemIndice) => boolean;
  rotulo?: string;
  placeholder?: string;
  className?: string;
};

export default function Busca({ aoEscolher, rotulo = "Buscar deputado ou vereador", placeholder = "Buscar deputado ou vereador", className = "sm:w-80" }: Props) {
  const [itens, setItens] = useState<ItemIndice[] | null>(null);
  const [q, setQ] = useState("");
  const [aberta, setAberta] = useState(false);
  const [ativo, setAtivo] = useState(0);
  const router = useRouter();
  const caixa = useRef<HTMLDivElement>(null);
  const base = useId();
  const idCampo = `${base}-campo`;
  const idLista = `${base}-lista`;
  const idOpcao = (n: number) => `${base}-op-${n}`;

  const carregar = () => {
    if (itens) return;
    fetch("/dados/parlamentares.json")
      .then((r) => r.json())
      .then(setItens)
      .catch(() => setItens([]));
  };

  const achados = useMemo(() => (itens ? buscar(itens, q) : []), [itens, q]);
  const digitou = q.trim().length >= 2;
  const mostrar = aberta && digitou;
  const status = !digitou ? "" : itens === null ? "Abrindo o índice…" : achados.length === 0 ? "Nenhum nome encontrado." : `${achados.length} ${achados.length === 1 ? "resultado" : "resultados"}`;

  useEffect(() => {
    const fora = (e: PointerEvent) => caixa.current && !caixa.current.contains(e.target as Node) && setAberta(false);
    document.addEventListener("pointerdown", fora);
    return () => document.removeEventListener("pointerdown", fora);
  }, []);

  const ir = (item: ItemIndice) => {
    setAberta(false);
    setQ("");
    if (aoEscolher && aoEscolher(item)) return;
    router.push(`/parlamentares/${item.id}/`);
  };

  return (
    <div ref={caixa} className={`relative w-full ${className}`}>
      <label htmlFor={idCampo} className="sr-only">
        {rotulo}
      </label>
      <input
        id={idCampo}
        type="search"
        autoComplete="off"
        spellCheck={false}
        enterKeyHint="search"
        placeholder={`${placeholder}…`}
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
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setAberta(true);
            setAtivo((a) => Math.min(a + 1, achados.length - 1));
          }
          if (e.key === "ArrowUp") {
            e.preventDefault();
            setAtivo((a) => Math.max(a - 1, 0));
          }
          if (e.key === "Enter" && mostrar && achados[ativo]) {
            e.preventDefault();
            ir(achados[ativo]);
          }
          if (e.key === "Escape") setAberta(false);
          if (e.key === "Tab") setAberta(false);
        }}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={mostrar && achados.length > 0}
        aria-controls={idLista}
        aria-activedescendant={mostrar && achados[ativo] ? idOpcao(ativo) : undefined}
        className="h-10 w-full rounded-md border border-contorno bg-gaveta-2 px-3.5 text-[0.95rem] text-tinta placeholder:text-tinta-3 focus:border-carimbo focus:outline-none"
      />
      {/* anúncio para leitor de tela: quantos nomes a busca achou */}
      <p role="status" className="sr-only">
        {mostrar ? status : ""}
      </p>
      <div
        className={`absolute right-0 top-full z-50 mt-1.5 w-full overflow-hidden rounded-md border border-aco-2 bg-gaveta-2 shadow-[0_14px_30px_-10px_rgba(0,0,0,0.7)] ${mostrar ? "" : "hidden"}`}
      >
        {itens === null && <p className="px-3.5 py-2.5 text-sm text-tinta-3">Abrindo o índice…</p>}
        {itens !== null && achados.length === 0 && (
          <p className="px-3.5 py-2.5 text-sm leading-relaxed text-tinta-3">
            Nenhum nome encontrado. A busca cobre os deputados federais da 57ª legislatura e os vereadores de Curitiba. Partidos ficam em{" "}
            <Link href="/partidos/" className="text-tinta-2 underline hover:text-tinta" onClick={() => setAberta(false)}>
              Partidos
            </Link>
            .
          </p>
        )}
        <ul id={idLista} role="listbox" aria-label="Parlamentares encontrados" className={achados.length ? "" : "hidden"}>
          {achados.map((i, n) => (
            <li
              key={i.id}
              id={idOpcao(n)}
              role="option"
              aria-selected={n === ativo}
              onPointerEnter={() => setAtivo(n)}
              // o foco fica no campo: o clique escolhe sem tirar o foco dele
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => ir(i)}
              className={`flex cursor-pointer items-baseline justify-between gap-3 px-3.5 py-2.5 ${n === ativo ? "bg-gaveta-3" : ""}`}
            >
              <span className="min-w-0 text-[0.95rem]">{i.nome}</span>
              <span className="shrink-0 text-xs text-tinta-3">
                {i.partido ?? "sem partido"} · {i.casa === "cmc" ? "Curitiba" : i.uf}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
