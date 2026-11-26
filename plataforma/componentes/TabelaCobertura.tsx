"use client";

import Link from "next/link";
import { useEffect, useId, useMemo, useState } from "react";
import { Amostra } from "@/componentes/MapaCobertura";
import { type Classe, type LinhaCobertura, MOTIVO_FORA, ORDEM_CLASSE, ROTULO_CLASSE } from "@/lib/cobertura";
import { inteiro } from "@/lib/formato";

const GRUPOS: { id: LinhaCobertura["grupo"]; titulo: string }[] = [
  { id: "federal", titulo: "Congresso" },
  { id: "assembleia", titulo: "Assembleias legislativas" },
  { id: "camara", titulo: "Câmaras municipais do Paraná" },
];

function norm(s: string) {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

/** A tabela de todas as casas, com filtro por situação e por nome. Sem filtro, mostra
 * tudo: são poucas centenas de linhas, já no HTML. */
export default function TabelaCobertura({ linhas }: { linhas: LinhaCobertura[] }) {
  const [filtro, setFiltro] = useState<"todas" | Classe>("todas");
  const [q, setQ] = useState("");
  const idBusca = useId();
  const idSituacao = useId();
  // o filtro fica na URL (?situacao=…&casa=…): dá para mandar o link da tabela já filtrada
  useEffect(() => {
    const u = new URLSearchParams(window.location.search);
    const s = u.get("situacao");
    if (s && linhas.some((l) => l.classe === s)) setFiltro(s as Classe);
    if (u.get("casa")) setQ(u.get("casa") ?? "");
  }, [linhas]);
  useEffect(() => {
    const u = new URLSearchParams(window.location.search);
    if (filtro === "todas") u.delete("situacao");
    else u.set("situacao", filtro);
    if (q.trim()) u.set("casa", q.trim());
    else u.delete("casa");
    const busca = u.toString();
    window.history.replaceState(window.history.state, "", `${window.location.pathname}${busca ? `?${busca}` : ""}${window.location.hash}`);
  }, [filtro, q]);
  const visiveis = useMemo(() => {
    const t = norm(q.trim());
    return linhas.filter(
      (l) => (filtro === "todas" || l.classe === filtro) && (!t || norm(`${l.nome} ${l.onde} ${l.fornecedor ?? ""}`).includes(t)),
    );
  }, [linhas, filtro, q]);
  const classes = useMemo(() => {
    const c = new Map<Classe, number>();
    for (const l of linhas) c.set(l.classe, (c.get(l.classe) ?? 0) + 1);
    return c;
  }, [linhas]);

  return (
    <div>
      <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
        <div className="flex flex-col gap-1">
          <label htmlFor={idBusca} className="text-[0.8rem] text-tinta-3">
            Casa, município ou fornecedor
          </label>
          <input
            id={idBusca}
            name="casa"
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Ex.: Maringá, Betha, SP…"
            autoComplete="off"
            className="h-10 w-[min(22rem,80vw)] rounded-md border border-contorno bg-gaveta-2 px-3.5 text-[0.95rem] text-tinta placeholder:text-tinta-3 focus:border-carimbo focus:outline-none"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor={idSituacao} className="text-[0.8rem] text-tinta-3">
            Situação
          </label>
          <select
            id={idSituacao}
            name="situacao"
            value={filtro}
            onChange={(e) => setFiltro(e.target.value as "todas" | Classe)}
            className="h-10 rounded-md border border-contorno bg-gaveta-2 px-3 text-[0.95rem] text-tinta focus:border-carimbo focus:outline-none"
          >
            <option value="todas">Todas ({inteiro(linhas.length)})</option>
            {ORDEM_CLASSE
              .filter((c) => classes.get(c))
              .map((c) => (
                <option key={c} value={c}>
                  {ROTULO_CLASSE[c]} ({inteiro(classes.get(c) ?? 0)})
                </option>
              ))}
          </select>
        </div>
        <p role="status" className="num pb-2 text-sm text-tinta-3">
          {visiveis.length === linhas.length ? `${inteiro(linhas.length)} casas` : `${inteiro(visiveis.length)} de ${inteiro(linhas.length)} casas`}
        </p>
      </div>

      {GRUPOS.map((g) => {
        const doGrupo = visiveis.filter((l) => l.grupo === g.id);
        if (!doGrupo.length) return null;
        return (
          <section
            key={g.id}
            aria-labelledby={`grupo-${g.id}`}
            className="mt-8"
            // centenas de linhas: o navegador só desenha o grupo quando ele chega perto da tela
            style={doGrupo.length > 60 ? { contentVisibility: "auto", containIntrinsicSize: `auto ${doGrupo.length * 52}px` } : undefined}
          >
            <h3 id={`grupo-${g.id}`} className="font-titulo text-lg font-medium">
              {g.titulo} <span className="num text-tinta-3">({inteiro(doGrupo.length)})</span>
            </h3>
            <table className="mt-3 w-full table-fixed text-left text-[0.9rem]">
              <caption className="sr-only">{`${g.titulo}: casa, sistema do portal e situação na coleta`}</caption>
              <thead className="text-[0.78rem] text-tinta-3">
                <tr className="border-b border-aco-2">
                  <th scope="col" className="w-[34%] py-2 pr-3 font-normal">
                    Casa
                  </th>
                  <th scope="col" className="w-[24%] py-2 pr-3 font-normal">
                    Sistema do portal
                  </th>
                  <th scope="col" className="py-2 font-normal">
                    Situação
                  </th>
                </tr>
              </thead>
              <tbody>
                {doGrupo.map((l) => (
                  <tr key={l.id} className="border-b border-aco align-top">
                    <td className="py-2 pr-3">
                      {l.href ? (
                        <Link href={l.href} className="text-tinta underline decoration-tinta-3 underline-offset-[3px] hover:text-carimbo-claro">
                          {l.nome}
                        </Link>
                      ) : (
                        <span className="text-tinta">{l.nome}</span>
                      )}
                      {l.onde && <span className="block text-[0.8rem] text-tinta-3">{l.onde}</span>}
                    </td>
                    <td className="break-words py-2 pr-3 text-tinta-2">{l.fornecedor ?? <span className="text-tinta-3">não identificado</span>}</td>
                    <td className="py-2">
                      <span className="flex items-start gap-1.5">
                        <span className="mt-[3px]">
                          <Amostra classe={l.classe} />
                        </span>
                        <span>
                          <span className="text-tinta">{ROTULO_CLASSE[l.classe]}</span>
                          {l.classe === "coletada" || l.classe === "em_revisao" ? (
                            <span className="num block text-[0.8rem] text-tinta-3">
                              {inteiro(l.parlamentares ?? 0)} parlamentares · {inteiro(l.linhas ?? 0)} linhas de despesa
                            </span>
                          ) : (
                            <span className="block text-[0.8rem] leading-snug text-tinta-3">
                              {(l.motivo && MOTIVO_FORA[l.motivo]) ?? MOTIVO_FORA.outro}
                              {l.detalhe ? ` ${l.detalhe}` : ""}
                            </span>
                          )}
                        </span>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        );
      })}
      {visiveis.length === 0 && <p className="mt-8 text-tinta-3">Nenhuma casa com esse filtro.</p>}
    </div>
  );
}
