"use client";

import { useEffect, useMemo, useState } from "react";
import Valor from "@/componentes/Valor";
import { data } from "@/lib/formato";
import { nomeFonte } from "@/lib/fontes";
import { TELA_ESTREITA, useMidia } from "@/lib/midia";
import type { ArquivoAno, InfoLinha, Procedencia } from "@/lib/tipos";

const POR_PAGINA = 60;

function documento(arq: ArquivoAno, d: string | null): string | null {
  if (!d) return null;
  const m = /^(\d+):(.*)$/.exec(d);
  if (m && !d.startsWith("http")) return arq.prefixos_documento[Number(m[1])] + m[2];
  return d;
}

type Linha = {
  data: string;
  valor: string;
  p: Procedencia;
  categoria: string;
  fornecedor: [string | null, string] | null;
  info: InfoLinha | null;
  url: string | null;
  fonte: string;
  coleta: string;
  fora: boolean;
};

export default function TabelaDespesas({ id, anos, rotulos }: { id: string; anos: number[]; rotulos: Record<string, string> }) {
  const [ano, setAno] = useState(anos[0]);
  const [arq, setArq] = useState<ArquivoAno | null>(null);
  const [erro, setErro] = useState(false);
  const [mostrar, setMostrar] = useState(POR_PAGINA);
  const [categoria, setCategoria] = useState<string>("");
  const estreita = useMidia(TELA_ESTREITA);

  useEffect(() => {
    if (!ano) return;
    setArq(null);
    setErro(false);
    setMostrar(POR_PAGINA);
    setCategoria("");
    fetch(`/dados/parlamentares/${id}/${ano}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setArq)
      .catch(() => setErro(true));
  }, [id, ano]);

  const linhas = useMemo<Linha[]>(() => {
    if (!arq) return [];
    return arq.linhas
      .filter((l) => !categoria || arq.categorias[l[1]] === categoria)
      .map(([dt, ic, iforn, valor, doc, ik, info]) => {
        const coleta = arq.coletas[ik];
        const url = documento(arq, doc) ?? info?.src ?? coleta.src ?? null;
        const fora = Boolean(info?.s);
        return {
          data: dt,
          valor,
          categoria: rotulos[arq.categorias[ic] ?? ""] ?? arq.categorias[ic] ?? "—",
          fornecedor: iforn >= 0 ? arq.fornecedores[iforn] : null,
          info,
          url,
          fonte: coleta.fonte,
          coleta: coleta.coletado_em,
          fora,
          p: {
            fontes: [coleta.fonte],
            coleta: coleta.coletado_em,
            documento: url,
            local: info?.loc ?? null,
            situacao: fora ? "fora_da_soma" : "conferido",
            nota: info?.s ?? info?.o ?? null,
          },
        };
      });
  }, [arq, categoria, rotulos]);

  if (!anos.length) return <p className="text-tinta-3">Nenhuma despesa conferida para mostrar aqui.</p>;

  const campo = "h-10 rounded-md border border-contorno bg-gaveta-2 px-2 text-tinta";

  return (
    <div>
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1 text-sm text-tinta-3">
          Ano
          <select value={ano} onChange={(e) => setAno(Number(e.target.value))} className={campo}>
            {anos.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
        {arq && arq.categorias.length > 1 && (
          <label className="flex min-w-0 flex-col gap-1 text-sm text-tinta-3">
            Categoria
            <select value={categoria} onChange={(e) => setCategoria(e.target.value)} className={`${campo} max-w-[18rem]`}>
              <option value="">Todas</option>
              {arq.categorias.filter(Boolean).map((c) => (
                <option key={c} value={c!}>
                  {rotulos[c!] ?? c}
                </option>
              ))}
            </select>
          </label>
        )}
        {arq && (
          <p className="num pb-2.5 text-sm text-tinta-3" role="status">
            {linhas.length} despesa{linhas.length === 1 ? "" : "s"}
          </p>
        )}
      </div>

      {erro && <p className="mt-4 text-tinta-2">Não foi possível abrir as despesas de {ano}. Recarregue a página para tentar de novo.</p>}
      {!arq && !erro && <p className="mt-4 text-tinta-3">Abrindo as fichas de {ano}…</p>}
      {arq &&
        (estreita ? (
          <ul className="mt-3" aria-label={`Despesas de ${ano}`}>
            {linhas.slice(0, mostrar).map((l, i) => (
              <li key={i} className={`border-b border-aco py-3 ${l.fora ? "text-tinta-3" : ""}`}>
                <div className="flex items-baseline justify-between gap-3">
                  <p className="min-w-0 text-[0.9rem] text-tinta-2">
                    <span className="num">{data(l.data)}</span> · {l.categoria}
                  </p>
                  <Valor valor={l.valor} p={l.p} className="shrink-0" />
                </div>
                <div className="mt-1 flex items-start justify-between gap-3">
                  <div className="min-w-0 break-words text-[0.92rem]">
                    <Descricao l={l} />
                  </div>
                  <Documento l={l} />
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <table className="mt-4 w-full text-left text-[0.92rem]">
            <caption className="sr-only">Despesas de {ano}</caption>
            <thead className="text-[0.8rem] text-tinta-3">
              <tr className="border-b border-aco-2">
                <th scope="col" className="py-2 pr-4 font-medium">Data</th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">Valor</th>
                <th scope="col" className="py-2 pr-4 font-medium">Categoria</th>
                <th scope="col" className="py-2 pr-4 font-medium">Fornecedor ou descrição</th>
                <th scope="col" className="py-2 font-medium">Documento</th>
              </tr>
            </thead>
            <tbody>
              {linhas.slice(0, mostrar).map((l, i) => (
                <tr key={i} className={`border-b border-aco align-top ${l.fora ? "text-tinta-3" : ""}`}>
                  <td className="num whitespace-nowrap py-2 pr-4">{data(l.data)}</td>
                  <td className="py-2 pr-4 text-right">
                    <Valor valor={l.valor} p={l.p} />
                  </td>
                  <td className="py-2 pr-4">{l.categoria}</td>
                  <td className="min-w-0 break-words py-2 pr-4">
                    <Descricao l={l} />
                  </td>
                  <td className="py-2">
                    <Documento l={l} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}
      {arq && linhas.length > mostrar && (
        <button
          type="button"
          onClick={() => setMostrar((m) => m + POR_PAGINA * 2)}
          className="mt-4 min-h-11 rounded-md border border-contorno px-4 py-2 text-sm text-tinta-2 hover:text-tinta"
        >
          Mostrar mais {Math.min(POR_PAGINA * 2, linhas.length - mostrar)} de {linhas.length - mostrar}
        </button>
      )}
    </div>
  );
}

/** Fornecedor (com CNPJ) ou a descrição da diária, e as notas da fonte. */
function Descricao({ l }: { l: Linha }) {
  const { info } = l;
  const procExtra: Procedencia = { fontes: [l.fonte], coleta: l.coleta, documento: l.url, local: info?.loc ?? null, situacao: "conferido" };
  return (
    <>
      {l.fornecedor ? (
        <>
          <span>{l.fornecedor[1]}</span>
          {l.fornecedor[0] && <span className="num block text-[0.78rem] text-tinta-3">{l.fornecedor[0]}</span>}
        </>
      ) : (
        <span>{info?.x ?? "—"}</span>
      )}
      {info?.s && <span className="block text-[0.78rem] text-sepia-claro">Não somada: {info.s}</span>}
      {!info?.s && info?.o && <span className="block text-[0.78rem] text-tinta-3">{info.o}</span>}
      {(info?.hosp || info?.tran) && (
        <span className="block text-[0.78rem] text-tinta-3">
          Na mesma viagem, informados pela fonte e fora desta soma:{" "}
          {info.hosp && (
            <>
              hospedagem <Valor valor={info.hosp} p={procExtra} />
            </>
          )}
          {info.hosp && info.tran ? "; " : ""}
          {info.tran && (
            <>
              transporte <Valor valor={info.tran} p={procExtra} />
            </>
          )}
        </span>
      )}
    </>
  );
}

function Documento({ l }: { l: Linha }) {
  if (!l.url)
    return (
      <span className="shrink-0 text-tinta-3" title={`${nomeFonte(l.fonte)} não publica link deste documento`}>
        sem link
      </span>
    );
  return (
    <a
      href={l.url}
      target="_blank"
      rel="noopener noreferrer"
      className="-my-2 inline-block shrink-0 py-2 text-tinta-2 underline hover:text-carimbo-claro"
    >
      {l.fonte === "camara_deputados" ? "nota" : "original"}
      <span className="sr-only"> (abre o documento oficial)</span>
    </a>
  );
}
