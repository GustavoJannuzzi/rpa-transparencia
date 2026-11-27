"use client";

import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import { data, inteiro, reais } from "@/lib/formato";
import { comoFonte, nomeFonte } from "@/lib/fontes";
import { TELA_ESTREITA, useMidia } from "@/lib/midia";
import type { Procedencia } from "@/lib/tipos";

type Props = {
  valor: string;
  p: Procedencia;
  tamanho?: "pequeno" | "medio" | "grande";
  className?: string;
  /** o que aparece no lugar do valor em reais: uma contagem (atividade nas sessões), já formatada */
  texto?: string;
};

/**
 * Um número em reais com a sua ficha de procedência. Todo valor da plataforma
 * passa por aqui: sem procedência, não há número na tela.
 *
 * A ficha é desenhada fora do fluxo (portal no body), para nunca ficar presa
 * num contêiner com rolagem: no computador, sai ao lado do número sem passar da
 * borda da tela; no celular, sobe da base da tela como uma folha.
 */
export default function Valor({ valor, p, tamanho = "pequeno", className = "", texto }: Props) {
  const [aberta, setAberta] = useState(false);
  const id = useId();
  const botao = useRef<HTMLButtonElement>(null);

  const fechar = useCallback((devolverFoco: boolean) => {
    setAberta(false);
    if (devolverFoco) botao.current?.focus();
  }, []);

  const escala =
    tamanho === "grande"
      ? "font-titulo text-[2.4rem] leading-none font-medium tracking-[-0.02em] sm:text-[2.9rem]"
      : tamanho === "medio"
        ? "font-titulo text-xl font-medium"
        : "";

  return (
    <span className={`inline-block ${className}`}>
      <button
        ref={botao}
        type="button"
        className={`valor num cursor-help whitespace-nowrap rounded-sm text-left underline decoration-tinta-3/50 decoration-dotted underline-offset-4 hover:decoration-carimbo-claro ${escala} ${p.situacao === "fora_da_soma" ? "text-tinta-3 line-through decoration-solid" : ""}`}
        data-fonte={p.fontes.join(" ")}
        data-coleta={p.coleta}
        aria-expanded={aberta}
        aria-haspopup="dialog"
        aria-controls={aberta ? id : undefined}
        aria-describedby="dica-ficha"
        onClick={() => setAberta((a) => !a)}
      >
        {texto ?? reais(valor)}
      </button>
      {aberta && <Ficha id={id} p={p} ancora={botao} fechar={fechar} />}
    </span>
  );
}

function Ficha({
  id,
  p,
  ancora,
  fechar,
}: {
  id: string;
  p: Procedencia;
  ancora: RefObject<HTMLButtonElement | null>;
  fechar: (devolverFoco: boolean) => void;
}) {
  const estreita = useMidia(TELA_ESTREITA);
  const caixa = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  // no computador: ao lado do número, presa na página, sem sair da tela
  useLayoutEffect(() => {
    if (estreita) return;
    const medir = () => {
      const b = ancora.current?.getBoundingClientRect();
      const c = caixa.current;
      if (!b || !c) return;
      const w = c.offsetWidth;
      const h = c.offsetHeight;
      const vw = document.documentElement.clientWidth;
      // começa na borda esquerda do número; se não couber, alinha pela direita; nunca a menos de 16 px da borda
      let left = b.left + w > vw - 16 ? b.right - w : b.left;
      left = Math.min(Math.max(16, left), vw - w - 16);
      // abre embaixo; se não couber embaixo e couber em cima, abre em cima
      let top = b.bottom + 8;
      if (top + h > window.innerHeight - 8 && b.top - h - 8 > 8) top = b.top - h - 8;
      setPos({ top: top + window.scrollY, left: left + window.scrollX });
    };
    medir();
    window.addEventListener("resize", medir);
    return () => window.removeEventListener("resize", medir);
  }, [estreita, ancora]);

  // a ficha recebe o foco quando já está no lugar (escondida, ela não aceita foco)
  const pronta = estreita || pos !== null;
  const focada = useRef(false);
  useEffect(() => {
    if (!pronta || focada.current) return;
    focada.current = true;
    caixa.current?.focus({ preventScroll: true });
  }, [pronta]);

  // Esc, clique fora ou sair dela com o Tab a fecham
  useEffect(() => {
    const fora = (e: PointerEvent) => {
      const alvo = e.target as Node;
      if (caixa.current?.contains(alvo) || ancora.current?.contains(alvo)) return;
      fechar(false);
    };
    const tecla = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        fechar(true);
      }
    };
    document.addEventListener("pointerdown", fora);
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("pointerdown", fora);
      document.removeEventListener("keydown", tecla);
    };
  }, [ancora, fechar]);

  // a ficha está no fim do documento: o Tab que sai dela volta para o número que a abriu
  const tab = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "Tab" || !caixa.current) return;
    const focaveis = [...caixa.current.querySelectorAll<HTMLElement>("a[href], button")];
    const primeiro = focaveis[0];
    const ultimo = focaveis.at(-1);
    const ativo = document.activeElement;
    if ((!e.shiftKey && ativo === ultimo) || (e.shiftKey && (ativo === primeiro || ativo === caixa.current))) {
      e.preventDefault();
      fechar(true);
    }
  };

  const carimbo =
    p.situacao === "fora_da_soma"
      ? "FORA DA SOMA"
      : p.situacao === "soma"
        ? "SOMA CONFERIDA"
        : p.situacao === "contagem"
          ? "CONTAGEM CONFERIDA"
          : p.situacao === "da_fonte"
            ? "NÚMERO DA FONTE"
            : "CONFERIDO";

  const conteudo = (
    <div
      ref={caixa}
      id={id}
      role="dialog"
      aria-label="Ficha de procedência"
      tabIndex={-1}
      onKeyDown={tab}
      style={estreita ? undefined : { top: pos?.top ?? 0, left: pos?.left ?? 0, visibility: pos ? "visible" : "hidden" }}
      className={
        estreita
          ? "ficha-sobe fixed inset-x-0 bottom-0 z-50 max-h-[85dvh] overflow-y-auto overscroll-contain rounded-t-[3px] bg-manilha px-4 pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-4 text-left font-texto text-[0.95rem] text-manilha-tinta shadow-[0_-14px_30px_-8px_rgba(0,0,0,0.6)] focus:outline-none"
          : "ficha-sai absolute z-50 w-[22rem] max-w-[calc(100vw-2rem)] rounded-[3px] bg-manilha p-4 text-left font-texto text-sm text-manilha-tinta shadow-[0_14px_30px_-8px_rgba(0,0,0,0.6)] focus:outline-none"
      }
    >
      <div className="flex items-start justify-between gap-3">
        <h2 className="font-titulo text-[0.95rem] font-semibold leading-snug">
          De onde vem este número
        </h2>
        <span
          className={`carimbo-bate shrink-0 rounded-[3px] border-2 px-1.5 py-0.5 font-titulo text-[0.68rem] font-semibold tracking-[0.08em] ${p.situacao === "fora_da_soma" ? "border-sepia text-sepia" : "border-carimbo-escuro text-carimbo-escuro"}`}
          style={{ transform: "rotate(-6deg)" }}
        >
          {carimbo}
        </span>
      </div>
      <div className="mt-3 border-t border-manilha-tinta/20 pt-2">
        {p.fontes.map((f) => (
          <p key={f} className="leading-snug">
            <span className="font-medium">{nomeFonte(f)}</span>
            <span className="text-manilha-tinta-2"> · {comoFonte(f)}</span>
          </p>
        ))}
      </div>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[0.8rem] leading-snug">
        <dt className="text-manilha-tinta-2">Coleta</dt>
        <dd className="num">{data(p.coleta)}</dd>
        {p.registros && (
          <>
            <dt className="text-manilha-tinta-2">Registros</dt>
            <dd className="num">{p.registros}</dd>
          </>
        )}
        {p.linhas !== undefined && (
          <>
            <dt className="text-manilha-tinta-2">Linhas</dt>
            <dd className="num">{p.linhas === 1 ? "1 despesa conferida" : `soma de ${inteiro(p.linhas)} despesas conferidas`}</dd>
          </>
        )}
        {p.local && (
          <>
            <dt className="text-manilha-tinta-2">No original</dt>
            <dd className="break-words">{p.local}</dd>
          </>
        )}
        {p.nota && (
          <>
            <dt className="text-manilha-tinta-2">Nota</dt>
            <dd className="break-words">{p.nota}</dd>
          </>
        )}
      </dl>
      <div className="mt-2 flex items-center justify-between gap-4">
        {p.documento ? (
          <a
            href={p.documento}
            target="_blank"
            rel="noopener noreferrer"
            className="-my-1 inline-block py-2 font-medium text-carimbo-escuro underline"
          >
            Abrir o documento oficial
          </a>
        ) : (
          <span />
        )}
        <button
          type="button"
          onClick={() => fechar(true)}
          className="-my-1 -mr-2 min-h-11 px-2 text-[0.8rem] text-manilha-tinta-2 underline-offset-2 hover:text-manilha-tinta hover:underline sm:min-h-0 sm:py-1"
        >
          fechar
        </button>
      </div>
    </div>
  );

  return createPortal(conteudo, document.body);
}
