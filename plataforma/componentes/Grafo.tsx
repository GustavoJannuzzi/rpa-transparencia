"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type GraphT from "graphology";
import type SigmaT from "sigma";
import { ABA_DEMAIS, paletaPartidos } from "@/lib/cores";

type No = { id: string; rotulo: string; partido: string | null; uf?: string; grau?: number; tipo?: string; total?: string; x: number; y: number };
type Aresta = { a: string; b: string; peso?: number; atual?: boolean; periodo?: string; base?: string; fornecedores?: { doc: string; nome: string | null }[] };
type DadosGrafo = { nos: No[]; arestas: Aresta[]; partidos: string[]; regra: string };
type Vista = "brasil" | "parana";

const APAGADO = "#2b3532";

export default function Grafo() {
  const [vista, setVista] = useState<Vista>("brasil");
  const [dados, setDados] = useState<DadosGrafo | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [selecionado, setSelecionado] = useState<string | null>(null);
  const [partidoFoco, setPartidoFoco] = useState<string | null>(null);
  const [emLista, setEmLista] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<SigmaT | null>(null);
  const grafoRef = useRef<GraphT | null>(null);
  const estado = useRef<{ hover: string | null; sel: string | null; partido: string | null }>({ hover: null, sel: null, partido: null });

  // Carrega os dados da vista
  useEffect(() => {
    let cancelado = false;
    setDados(null);
    setErro(null);
    setSelecionado(null);
    setPartidoFoco(null);
    fetch(`/dados/grafo-${vista}.json`)
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((d: DadosGrafo) => !cancelado && setDados(d))
      .catch(() => !cancelado && setErro("Não foi possível abrir os dados do grafo."));
    return () => {
      cancelado = true;
    };
  }, [vista]);

  const cores = useMemo(() => {
    const cont = new Map<string, number>();
    dados?.nos.forEach((n) => n.partido && n.tipo !== "partido" && cont.set(n.partido, (cont.get(n.partido) ?? 0) + 1));
    return paletaPartidos(cont);
  }, [dados]);

  const legenda = useMemo(() => {
    const cont = new Map<string, number>();
    dados?.nos.forEach((n) => n.partido && n.tipo !== "partido" && cont.set(n.partido, (cont.get(n.partido) ?? 0) + 1));
    return [...cont.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  }, [dados]);

  // Monta o sigma
  useEffect(() => {
    if (!dados || emLista || !caixa.current) return;
    let sigma: SigmaT | null = null;
    let morto = false;
    (async () => {
      const [{ default: Graph }, { default: Sigma }] = await Promise.all([import("graphology"), import("sigma")]);
      if (morto || !caixa.current) return;
      const g = new Graph({ type: "undirected", multi: false });
      // a família de verdade que o next/font registrou (no canvas, var() não vale)
      const familia = getComputedStyle(document.documentElement).getPropertyValue("--fonte-archivo").trim() || "Archivo, sans-serif";
      const membrosPorPartido = new Map<string, number>();
      dados.nos.forEach((n) => n.tipo !== "partido" && n.partido && membrosPorPartido.set(n.partido, (membrosPorPartido.get(n.partido) ?? 0) + 1));
      // em tela estreita o ponto precisa ser menor, senão a rede vira uma bola só
      const escalaNo = caixa.current.clientWidth < 640 ? 0.55 : 1;
      for (const n of dados.nos) {
        const ehPartido = n.tipo === "partido";
        // na vista Brasil, quem não divide fornecedor com ninguém fica só na lista
        if (vista === "brasil" && !n.grau) continue;
        const tamanho = ehPartido ? 7 : vista === "brasil" ? 2.4 + Math.min(n.grau ?? 0, 60) / 16 : n.tipo === "deputado" ? 5.5 : 4;
        g.addNode(n.id, {
          x: n.x,
          y: -n.y,
          size: tamanho * escalaNo,
          label: n.rotulo,
          color: ehPartido ? "#d8c79f" : (n.partido && cores.get(n.partido)) || ABA_DEMAIS,
          zIndex: ehPartido ? 1 : 0,
          partido: n.partido,
          tipo: n.tipo ?? "deputado",
          forceLabel: ehPartido,
        });
      }
      for (const a of dados.arestas) {
        if (!g.hasNode(a.a) || !g.hasNode(a.b) || g.hasEdge(a.a, a.b)) continue;
        g.addEdge(a.a, a.b, {
          size: vista === "brasil" ? 0.25 + Math.min(a.peso ?? 1, 30) / 40 : a.atual ? 0.9 : 0.5,
          // cores opacas e escuras: o sigma não mistura transparência, e linha clara cruzada vira mancha
          color: vista === "brasil" ? "#34403c" : a.atual ? "#6e6650" : "#3d3b33",
        });
      }
      grafoRef.current = g;
      // placas de rótulo de partido já desenhadas neste quadro: a próxima desvia delas
      const placas: { x: number; y: number; w: number; h: number }[] = [];
      const bate = (r: { x: number; y: number; w: number; h: number }) =>
        placas.some((q) => r.x < q.x + q.w && q.x < r.x + r.w && r.y < q.y + q.h && q.y < r.y + r.h);
      sigma = new Sigma(g, caixa.current, {
        renderEdgeLabels: false,
        labelFont: familia,
        labelColor: { color: "#e8e2d2" },
        labelSize: 12,
        labelWeight: "500",
        labelDensity: 0.6,
        labelGridCellSize: 110,
        labelRenderedSizeThreshold: vista === "brasil" ? 6.5 : 7.5,
        defaultEdgeColor: "#34403c",
        zIndex: true,
        minCameraRatio: 0.08,
        maxCameraRatio: 3,
        // rótulo de partido sobre uma placa escura, por cima dos pontos; o das pessoas, simples
        defaultDrawNodeLabel: (ctx, d, s) => {
          if (!d.label) return;
          const ehPartido = (d as unknown as { tipo?: string }).tipo === "partido";
          const tam = ehPartido ? s.labelSize : s.labelSize - 1;
          ctx.font = `${ehPartido ? 600 : 500} ${tam}px ${familia}`;
          const w = ctx.measureText(d.label).width;
          let x = d.x + d.size + 4;
          let y = d.y + tam / 3;
          if (ehPartido) {
            // à direita; se bater noutra placa, à esquerda; depois embaixo; depois em cima
            const opcoes = [
              { x, y },
              { x: d.x - d.size - 4 - w, y },
              { x: d.x - w / 2, y: d.y + d.size + tam + 4 },
              { x: d.x - w / 2, y: d.y - d.size - 6 },
              { x: d.x - w / 2, y: d.y + d.size + 2 * tam + 10 },
              { x: d.x - w / 2, y: d.y - d.size - tam - 12 },
              { x: d.x + d.size + 4, y: d.y + tam + 8 },
              { x: d.x - d.size - 4 - w, y: d.y - tam - 6 },
            ];
            const placa = (o: { x: number; y: number }) => ({ x: o.x - 3, y: o.y - tam - 1, w: w + 6, h: tam + 6 });
            const escolhida = opcoes.find((o) => !bate(placa(o))) ?? opcoes[0];
            x = escolhida.x;
            y = escolhida.y;
            const r = placa(escolhida);
            placas.push(r);
            ctx.fillStyle = "rgba(27,34,32,0.88)";
            ctx.fillRect(r.x, r.y, r.w, r.h);
            ctx.fillStyle = "#e6d9b8";
          } else {
            ctx.fillStyle = "#bdb8aa";
          }
          ctx.fillText(d.label, x, y);
        },
        defaultDrawNodeHover: (ctx, d, s) => {
          // rótulo de foco: tinta creme sobre a gaveta, sem caixa branca
          const tam = s.labelSize + 2;
          ctx.font = `600 ${tam}px ${familia}`;
          const w = ctx.measureText(d.label ?? "").width;
          ctx.fillStyle = "rgba(27,34,32,0.92)";
          ctx.fillRect(d.x + d.size + 4, d.y - tam / 2 - 5, w + 12, tam + 10);
          ctx.fillStyle = "#e8e2d2";
          ctx.fillText(d.label ?? "", d.x + d.size + 10, d.y + tam / 3);
          ctx.beginPath();
          ctx.arc(d.x, d.y, d.size + 3, 0, Math.PI * 2);
          ctx.strokeStyle = "#b3a0ea";
          ctx.lineWidth = 2;
          ctx.stroke();
        },
        nodeReducer: (no, attr) => {
          const { hover, sel, partido } = estado.current;
          const foco = hover ?? sel;
          const r = { ...attr };
          if (partido && attr.partido !== partido && attr.tipo !== "partido") {
            r.color = APAGADO;
            r.label = "";
          }
          if (partido && attr.tipo === "partido" && attr.partido !== partido) r.color = "#5b6762";
          if (foco) {
            if (no === foco) {
              r.highlighted = true;
              r.zIndex = 2;
            } else if (!g.areNeighbors(no, foco)) {
              r.color = APAGADO;
              r.label = attr.tipo === "partido" ? attr.label : "";
            } else {
              r.zIndex = 1;
            }
          }
          return r;
        },
        edgeReducer: (aresta, attr) => {
          const { hover, sel, partido } = estado.current;
          const foco = hover ?? sel;
          const r = { ...attr };
          if (foco) {
            if (g.hasExtremity(aresta, foco)) {
              r.color = "#8a6fd1";
              r.zIndex = 1;
            } else r.hidden = true;
          } else if (partido) {
            const [a, b] = g.extremities(aresta);
            if (g.getNodeAttribute(a, "partido") !== partido && g.getNodeAttribute(b, "partido") !== partido) r.hidden = true;
          }
          return r;
        },
      });
      sigma.on("beforeRender", () => {
        placas.length = 0;
      });
      sigma.on("enterNode", ({ node }) => {
        estado.current.hover = node;
        sigma?.refresh({ skipIndexation: true });
        caixa.current!.style.cursor = "pointer";
      });
      sigma.on("leaveNode", () => {
        estado.current.hover = null;
        sigma?.refresh({ skipIndexation: true });
        caixa.current!.style.cursor = "";
      });
      sigma.on("clickNode", ({ node }) => setSelecionado(node));
      sigma.on("clickStage", () => setSelecionado(null));
      sigmaRef.current = sigma;
      sigma.refresh();
    })();
    return () => {
      morto = true;
      sigma?.kill();
      sigmaRef.current = null;
    };
  }, [dados, emLista, cores, vista]);

  // Estado -> sigma
  useEffect(() => {
    estado.current.sel = selecionado;
    estado.current.partido = partidoFoco;
    const s = sigmaRef.current;
    if (!s) return;
    s.refresh({ skipIndexation: true });
    if (selecionado && grafoRef.current?.hasNode(selecionado)) {
      const pos = s.getNodeDisplayData(selecionado);
      if (pos) s.getCamera().animate({ x: pos.x, y: pos.y, ratio: Math.min(s.getCamera().ratio, 0.55) }, { duration: 450 });
    }
  }, [selecionado, partidoFoco]);

  const escolher = useCallback((id: string) => {
    setEmLista(false);
    setSelecionado(id);
  }, []);

  const noSel = dados?.nos.find((n) => n.id === selecionado) ?? null;
  const ligacoes = useMemo(() => {
    if (!dados || !selecionado) return [];
    return dados.arestas
      .filter((a) => a.a === selecionado || a.b === selecionado)
      .map((a) => ({ ...a, outro: dados.nos.find((n) => n.id === (a.a === selecionado ? a.b : a.a))! }))
      .filter((a) => a.outro)
      .sort((x, y) => (y.peso ?? 0) - (x.peso ?? 0));
  }, [dados, selecionado]);

  return (
    <div className="relative flex h-full min-h-[560px] flex-col">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 pt-4 sm:px-8">
        <div role="tablist" aria-label="Vista do grafo" className="flex gap-1.5">
          {(
            [
              ["brasil", "Brasil", " · fornecedores em comum"],
              ["parana", "Paraná", " · partidos"],
            ] as [Vista, string, string][]
          ).map(([v, r, resto]) => (
            <button
              key={v}
              role="tab"
              aria-selected={vista === v}
              onClick={() => setVista(v)}
              className={`rounded-t-[5px] px-3 pb-1.5 pt-2 font-titulo text-[0.9rem] font-medium ${vista === v ? "bg-manilha text-manilha-tinta" : "bg-gaveta-3 text-tinta-2 hover:text-tinta"}`}
            >
              {r}
              <span className="hidden sm:inline">{resto}</span>
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setEmLista((l) => !l)}
          className="ml-auto text-sm text-tinta-2 underline hover:text-tinta"
          aria-pressed={emLista}
        >
          {emLista ? "Voltar ao grafo" : "Ver em lista"}
        </button>
      </div>

      <div className="relative mx-4 min-h-[440px] flex-1 overflow-hidden border-t-2 border-manilha bg-gaveta-2 sm:mx-8">
        {erro && <p className="p-6 text-tinta-2">{erro}</p>}
        {!dados && !erro && <p className="p-6 text-tinta-3">Abrindo o grafo…</p>}
        {dados && !emLista && <div ref={caixa} className="absolute inset-0" aria-label="Grafo de parlamentares; use a lista para navegar pelo teclado" role="img" />}
        {dados && emLista && <Lista dados={dados} escolher={escolher} vista={vista} />}

        {noSel && !emLista && (
          <aside className="ficha-sai absolute bottom-4 left-4 z-10 w-[min(26rem,calc(100%-2rem))] rounded-[3px] bg-manilha p-4 text-manilha-tinta shadow-[0_18px_36px_-12px_rgba(0,0,0,0.7)]">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="font-titulo text-lg font-semibold leading-tight">{noSel.rotulo}</h3>
                <p className="text-sm text-manilha-tinta-2">
                  {noSel.tipo === "partido"
                    ? "Partido"
                    : `${noSel.partido ?? "sem partido"} · ${noSel.tipo === "vereador" ? "vereador(a) de Curitiba" : `deputado(a) · ${noSel.uf ?? "PR"}`}`}
                </p>
              </div>
              <button type="button" onClick={() => setSelecionado(null)} className="text-sm text-manilha-tinta-2 hover:text-manilha-tinta">
                fechar
              </button>
            </div>
            {vista === "brasil" && ligacoes.length > 0 && (
              <div className="mt-3 border-t border-manilha-tinta/20 pt-2 text-sm">
                <p className="text-manilha-tinta-2">Contratou os mesmos fornecedores que:</p>
                <ul className="mt-1 space-y-1">
                  {ligacoes.slice(0, 4).map((l) => (
                    <li key={l.outro.id}>
                      <button type="button" onClick={() => setSelecionado(l.outro.id)} className="font-medium underline">
                        {l.outro.rotulo}
                      </button>
                      <span className="text-manilha-tinta-2"> ({l.outro.partido ?? "—"}/{l.outro.uf})</span>
                      {l.fornecedores && l.fornecedores.length > 0 && (
                        <span className="block truncate text-[0.78rem] text-manilha-tinta-2">
                          {l.fornecedores.map((f) => f.nome ?? f.doc).join(" · ")}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {vista === "parana" && noSel.tipo !== "partido" && (
              <p className="mt-2 text-sm text-manilha-tinta-2">
                Ligado aos partidos pelos quais teve mandato; a linha mais forte é o partido atual.
              </p>
            )}
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm">
              {noSel.tipo === "partido" ? (
                <Link href={`/partidos/${slug(noSel.rotulo)}/`} className="font-medium text-carimbo-escuro underline">
                  Abrir o partido {noSel.rotulo}
                </Link>
              ) : (
                <Link href={`/parlamentares/${noSel.id}/`} className="font-medium text-carimbo-escuro underline">
                  Abrir as despesas de {noSel.rotulo}
                </Link>
              )}
            </div>
          </aside>
        )}
      </div>

      <div className="px-4 pb-4 pt-3 sm:px-8">
        <p className="sr-only">Legenda: cor do ponto = partido.</p>
        <ul className="flex flex-wrap gap-1.5" aria-label="Partidos; clique para destacar">
          {legenda.slice(0, 10).map(([sigla, n]) => (
            <li key={sigla}>
              <button
                type="button"
                onClick={() => setPartidoFoco((p) => (p === sigla ? null : sigla))}
                aria-pressed={partidoFoco === sigla}
                className={`flex items-center gap-1.5 rounded-[3px] px-2 py-1 text-[0.8rem] ${partidoFoco === sigla ? "bg-gaveta-3 text-tinta ring-1 ring-carimbo-claro" : "text-tinta-2 hover:text-tinta"}`}
              >
                <span className="inline-block h-2 w-3.5 rounded-t-[3px]" style={{ background: cores.get(sigla) }} />
                {sigla} <span className="num text-tinta-3">{n}</span>
              </button>
            </li>
          ))}
          {legenda.length > 10 && (
            <li className="flex items-center gap-1.5 px-2 py-1 text-[0.8rem] text-tinta-3">
              <span className="inline-block h-2 w-3.5 rounded-t-[3px]" style={{ background: ABA_DEMAIS }} />
              demais {legenda.length - 10} partidos
            </li>
          )}
        </ul>
        {dados && <p className="mt-2 max-w-[80ch] text-[0.82rem] leading-relaxed text-tinta-3">{dados.regra}</p>}
      </div>
    </div>
  );
}

function slug(s: string) {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function Lista({ dados, escolher, vista }: { dados: DadosGrafo; escolher: (id: string) => void; vista: Vista }) {
  const nos = dados.nos.filter((n) => n.tipo !== "partido").sort((a, b) => a.rotulo.localeCompare(b.rotulo, "pt-BR"));
  const fora = (n: No) => vista === "brasil" && !n.grau;
  return (
    <div className="absolute inset-0 overflow-auto">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Parlamentares no grafo {vista === "brasil" ? "Brasil" : "Paraná"}</caption>
        <thead className="sticky top-0 bg-gaveta-2 text-tinta-3">
          <tr>
            <th scope="col" className="px-4 py-2 font-medium">Nome</th>
            <th scope="col" className="px-4 py-2 font-medium">Partido</th>
            <th scope="col" className="px-4 py-2 font-medium">{vista === "brasil" ? "UF" : "Casa"}</th>
            <th scope="col" className="px-4 py-2 font-medium">No grafo</th>
          </tr>
        </thead>
        <tbody>
          {nos.map((n) => (
            <tr key={n.id} className="border-t border-aco">
              <td className="px-4 py-1.5">
                <Link href={`/parlamentares/${n.id}/`} className="underline hover:text-carimbo-claro">
                  {n.rotulo}
                </Link>
              </td>
              <td className="px-4 py-1.5 text-tinta-2">{n.partido ?? "—"}</td>
              <td className="px-4 py-1.5 text-tinta-2">{vista === "brasil" ? n.uf : n.tipo === "vereador" ? "Curitiba" : "Câmara dos Deputados"}</td>
              <td className="px-4 py-1.5">
                {fora(n) ? (
                  <span className="text-tinta-3">sem fornecedor em comum acima do corte</span>
                ) : (
                  <button type="button" onClick={() => escolher(n.id)} className="text-tinta-2 underline hover:text-tinta">
                    mostrar no grafo
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
