"use client";

import { useEffect, useId, useRef, useState } from "react";
import { data, inteiro, reais } from "@/lib/formato";
import { comoFonte, nomeFonte } from "@/lib/fontes";
import type { Procedencia } from "@/lib/tipos";

type Props = {
  valor: string;
  p: Procedencia;
  tamanho?: "pequeno" | "medio" | "grande";
  className?: string;
};

/**
 * Um número em reais com a sua ficha de procedência. Todo valor da plataforma
 * passa por aqui: sem procedência, não há número na tela.
 */
export default function Valor({ valor, p, tamanho = "pequeno", className = "" }: Props) {
  const [aberta, setAberta] = useState(false);
  const [lado, setLado] = useState<"esquerda" | "direita">("esquerda");
  const id = useId();
  const raiz = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!aberta) return;
    const fora = (e: MouseEvent) => {
      if (raiz.current && !raiz.current.contains(e.target as Node)) setAberta(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setAberta(false);
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", fora);
      document.removeEventListener("keydown", esc);
    };
  }, [aberta]);

  const escala =
    tamanho === "grande"
      ? "font-titulo text-[2.4rem] leading-none font-medium tracking-[-0.02em] sm:text-[2.9rem]"
      : tamanho === "medio"
        ? "font-titulo text-xl font-medium"
        : "";

  return (
    <span ref={raiz} className={`relative inline-block ${className}`}>
      <button
        type="button"
        className={`valor num cursor-help whitespace-nowrap rounded-sm text-left underline decoration-tinta-3/50 decoration-dotted underline-offset-4 hover:decoration-carimbo-claro ${escala} ${p.situacao === "fora_da_soma" ? "text-tinta-3 line-through decoration-solid" : ""}`}
        data-fonte={p.fontes.join(" ")}
        data-coleta={p.coleta}
        aria-expanded={aberta}
        aria-controls={id}
        onClick={(e) => {
          // a ficha sai para o lado em que cabe
          const r = e.currentTarget.getBoundingClientRect();
          setLado(r.left + 360 > window.innerWidth - 16 ? "direita" : "esquerda");
          setAberta((a) => !a);
        }}
      >
        {reais(valor)}
      </button>
      {aberta && <Ficha id={id} p={p} lado={lado} fechar={() => setAberta(false)} />}
    </span>
  );
}

function Ficha({ id, p, lado, fechar }: { id: string; p: Procedencia; lado: "esquerda" | "direita"; fechar: () => void }) {
  const carimbo =
    p.situacao === "fora_da_soma" ? "FORA DA SOMA" : p.situacao === "soma" ? "SOMA CONFERIDA" : "CONFERIDO";
  return (
    <span
      id={id}
      role="dialog"
      aria-label="Ficha de procedência"
      className={`ficha-sai absolute ${lado === "direita" ? "right-0" : "left-0"} top-full z-50 mt-2 block w-[min(22rem,calc(100vw-2rem))] rounded-[3px] bg-manilha p-4 text-left font-texto text-sm text-manilha-tinta shadow-[0_14px_30px_-8px_rgba(0,0,0,0.6)]`}
    >
      <span className="flex items-start justify-between gap-3">
        <span className="font-titulo text-[0.95rem] font-semibold leading-snug">De onde vem este número</span>
        <span
          className={`carimbo-bate shrink-0 rounded-[3px] border-2 px-1.5 py-0.5 font-titulo text-[0.68rem] font-semibold tracking-[0.08em] ${p.situacao === "fora_da_soma" ? "border-sepia text-sepia" : "border-carimbo-escuro text-carimbo-escuro"}`}
          style={{ transform: "rotate(-6deg)" }}
        >
          {carimbo}
        </span>
      </span>
      <span className="mt-3 block border-t border-manilha-tinta/20 pt-2">
        {p.fontes.map((f) => (
          <span key={f} className="block leading-snug">
            <span className="font-medium">{nomeFonte(f)}</span>
            <span className="text-manilha-tinta-2"> · {comoFonte(f)}</span>
          </span>
        ))}
      </span>
      <span className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[0.8rem] leading-snug">
        <span className="text-manilha-tinta-2">Coleta</span>
        <span className="num">{data(p.coleta)}</span>
        {p.linhas !== undefined && (
          <>
            <span className="text-manilha-tinta-2">Linhas</span>
            <span className="num">
              {p.linhas === 1 ? "1 despesa conferida" : `soma de ${inteiro(p.linhas)} despesas conferidas`}
            </span>
          </>
        )}
        {p.local && (
          <>
            <span className="text-manilha-tinta-2">No original</span>
            <span>{p.local}</span>
          </>
        )}
        {p.nota && (
          <>
            <span className="text-manilha-tinta-2">Nota</span>
            <span>{p.nota}</span>
          </>
        )}
      </span>
      {p.documento && (
        <a
          href={p.documento}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 inline-block font-medium text-carimbo-escuro underline"
        >
          Abrir o documento oficial
        </a>
      )}
      <button
        type="button"
        onClick={fechar}
        className="absolute bottom-2 right-3 text-[0.75rem] text-manilha-tinta-2 hover:text-manilha-tinta"
      >
        fechar
      </button>
    </span>
  );
}
