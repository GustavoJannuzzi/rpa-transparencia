"use client";

import { useEffect, useMemo, useState } from "react";
import Valor from "@/componentes/Valor";
import { data } from "@/lib/formato";
import { nomeFonte } from "@/lib/fontes";
import type { ArquivoAno } from "@/lib/tipos";

const POR_PAGINA = 60;

function documento(arq: ArquivoAno, d: string | null): string | null {
  if (!d) return null;
  const m = /^(\d+):(.*)$/.exec(d);
  if (m && !d.startsWith("http")) return arq.prefixos_documento[Number(m[1])] + m[2];
  return d;
}

export default function TabelaDespesas({ id, anos, rotulos }: { id: string; anos: number[]; rotulos: Record<string, string> }) {
  const [ano, setAno] = useState(anos[0]);
  const [arq, setArq] = useState<ArquivoAno | null>(null);
  const [erro, setErro] = useState(false);
  const [mostrar, setMostrar] = useState(POR_PAGINA);
  const [categoria, setCategoria] = useState<string>("");

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

  const linhas = useMemo(() => {
    if (!arq) return [];
    return arq.linhas.filter((l) => !categoria || arq.categorias[l[1]] === categoria);
  }, [arq, categoria]);

  if (!anos.length) return <p className="text-tinta-3">Nenhuma despesa publicada para esta pessoa.</p>;

  return (
    <div>
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1 text-sm text-tinta-3">
          Ano
          <select value={ano} onChange={(e) => setAno(Number(e.target.value))} className="h-9 rounded-md border border-aco-2 bg-gaveta-2 px-2 text-tinta">
            {anos.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
        {arq && arq.categorias.length > 1 && (
          <label className="flex flex-col gap-1 text-sm text-tinta-3">
            Categoria
            <select value={categoria} onChange={(e) => setCategoria(e.target.value)} className="h-9 max-w-[18rem] rounded-md border border-aco-2 bg-gaveta-2 px-2 text-tinta">
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
          <p className="num pb-2 text-sm text-tinta-3">
            {linhas.length} despesa{linhas.length === 1 ? "" : "s"}
          </p>
        )}
      </div>

      {erro && <p className="mt-4 text-tinta-2">Não foi possível abrir as despesas de {ano}.</p>}
      {!arq && !erro && <p className="mt-4 text-tinta-3">Abrindo as fichas de {ano}…</p>}
      {arq && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-[0.92rem]">
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
              {linhas.slice(0, mostrar).map((l, i) => {
                const [dt, ic, iforn, valor, doc, ik, info] = l;
                const forn = iforn >= 0 ? arq.fornecedores[iforn] : null;
                const coleta = arq.coletas[ik];
                const url = documento(arq, doc) ?? info?.src ?? null;
                const fora = Boolean(info?.s);
                return (
                  <tr key={i} className={`border-b border-aco align-top ${fora ? "text-tinta-3" : ""}`}>
                    <td className="num py-2 pr-4 whitespace-nowrap">{data(dt)}</td>
                    <td className="py-2 pr-4 text-right">
                      <Valor
                        valor={valor}
                        p={{
                          fontes: [coleta.fonte],
                          coleta: coleta.coletado_em,
                          documento: url,
                          local: info?.loc ?? null,
                          situacao: fora ? "fora_da_soma" : "conferido",
                          nota: info?.s ?? info?.o ?? null,
                        }}
                      />
                    </td>
                    <td className="py-2 pr-4">{rotulos[arq.categorias[ic] ?? ""] ?? arq.categorias[ic] ?? "—"}</td>
                    <td className="py-2 pr-4">
                      {forn ? (
                        <>
                          <span>{forn[1]}</span>
                          {forn[0] && <span className="num block text-[0.78rem] text-tinta-3">{forn[0]}</span>}
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
                              hospedagem <Valor valor={info.hosp} p={{ fontes: [coleta.fonte], coleta: coleta.coletado_em, documento: url, local: info.loc ?? null, situacao: "conferido" }} />
                            </>
                          )}
                          {info.hosp && info.tran ? "; " : ""}
                          {info.tran && (
                            <>
                              transporte <Valor valor={info.tran} p={{ fontes: [coleta.fonte], coleta: coleta.coletado_em, documento: url, local: info.loc ?? null, situacao: "conferido" }} />
                            </>
                          )}
                        </span>
                      )}
                    </td>

                    <td className="py-2">
                      {url ? (
                        <a href={url} target="_blank" rel="noopener noreferrer" className="text-tinta-2 underline hover:text-carimbo-claro">
                          {coleta.fonte === "camara_deputados" ? "nota" : "original"}
                        </a>
                      ) : (
                        <span className="text-tinta-3" title={`${nomeFonte(coleta.fonte)} não publica link deste documento`}>
                          sem link
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {linhas.length > mostrar && (
            <button type="button" onClick={() => setMostrar((m) => m + POR_PAGINA * 2)} className="mt-4 rounded-md border border-aco-2 px-4 py-2 text-sm text-tinta-2 hover:text-tinta">
              Mostrar mais {Math.min(POR_PAGINA * 2, linhas.length - mostrar)} de {linhas.length - mostrar}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
