"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type GraphT from "graphology";
import type SigmaT from "sigma";
import Busca from "@/componentes/Busca";
import { ABA_DEMAIS } from "@/lib/cores";
import {
  APAGADO,
  corDaAresta,
  corDoNo,
  coresDaVista,
  entraNoGrafo,
  escalaDoNo,
  normalizar,
  tamanhoDaAresta,
  tamanhoDoNo,
  type DadosGrafo,
  type No,
  type Vista,
} from "@/lib/grafo";
import { TELA_ESTREITA, useMidia } from "@/lib/midia";
import type { ItemIndice } from "@/lib/tipos";

// A biblioteca do grafo começa a baixar junto com a página, em paralelo com os
// dados (que o HTML já pede com <link rel="preload">), e não depois deles.
const bibliotecas = typeof window === "undefined" ? null : Promise.all([import("graphology"), import("sigma")]);

const cacheDados = new Map<Vista, Promise<DadosGrafo>>();
declare global {
  interface Window {
    /** o pedido que o script inline da página inicial já fez, antes do JavaScript */
    __grafoInicial?: { vista: Vista; dados: Promise<unknown> };
  }
}
function carregarDados(vista: Vista) {
  if (!cacheDados.has(vista)) {
    const inicial = window.__grafoInicial;
    const bruto =
      inicial?.vista === vista
        ? inicial.dados
        : fetch(`/dados/grafo-${vista}.json`).then((r) => {
            if (!r.ok) throw new Error(String(r.status));
            return r.json();
          });
    if (inicial?.vista === vista) window.__grafoInicial = undefined;
    const p = bruto.then((d) => normalizar(d as Parameters<typeof normalizar>[0]));
    p.catch(() => cacheDados.delete(vista));
    cacheDados.set(vista, p);
  }
  return cacheDados.get(vista)!;
}

// os nomes dos fornecedores ficam num arquivo à parte: só vêm quando alguém abre um ponto
let cacheFornecedores: Promise<[string, string | null][]> | null = null;
function carregarFornecedores() {
  cacheFornecedores ??= fetch("/dados/grafo-brasil-fornecedores.json")
    .then((r) => (r.ok ? r.json() : Promise.reject()))
    .then((d: { fornecedores: [string, string | null][] }) => d.fornecedores)
    .catch(() => {
      cacheFornecedores = null;
      return [];
    });
  return cacheFornecedores;
}

const ABAS: [Vista, string, string][] = [
  ["brasil", "Brasil", " · fornecedores em comum"],
  ["parana", "Paraná", " · partidos"],
];

/** O estado do grafo mora na URL: voltar de uma página devolve o grafo como estava,
 * e dá para mandar o link de "fulano no grafo". */
type EstadoUrl = { vista: Vista | null; no: string | null; lista: boolean; partido: string | null };
function lerUrl(): EstadoUrl {
  const q = new URLSearchParams(window.location.search);
  const v = q.get("vista");
  return {
    vista: v === "brasil" || v === "parana" ? v : null,
    no: q.get("no"),
    lista: q.get("lista") === "1",
    partido: q.get("partido"),
  };
}

export default function Grafo() {
  const estreita = useMidia(TELA_ESTREITA);
  const [iniciado, setIniciado] = useState(false);
  const [vista, setVista] = useState<Vista>("brasil");
  const [dados, setDados] = useState<DadosGrafo | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [desenhado, setDesenhado] = useState(false);
  const [selecionado, setSelecionado] = useState<string | null>(null);
  const [partidoFoco, setPartidoFoco] = useState<string | null>(null);
  const [emLista, setEmLista] = useState(false);
  const [aviso, setAviso] = useState<{ id: string; nome: string } | null>(null);
  const [fornecedores, setFornecedores] = useState<[string, string | null][] | null>(null);
  const caixa = useRef<HTMLDivElement>(null);
  const quadro = useRef<HTMLDivElement>(null);
  const ficha = useRef<HTMLElement>(null);
  const tituloFicha = useRef<HTMLHeadingElement>(null);
  const sigmaRef = useRef<SigmaT | null>(null);
  const grafoRef = useRef<GraphT | null>(null);
  const estado = useRef<{ hover: string | null; sel: string | null; partido: string | null }>({ hover: null, sel: null, partido: null });
  // quem pedir um ponto antes de os dados chegarem (a URL, a busca do grafo) espera aqui
  const pendente = useRef<string | null>(null);
  // depois de "mostrar no grafo" ou da busca, o foco vai para a ficha do ponto
  const focarFicha = useRef(false);
  const ultimoToque = useRef(false);
  const padrao: Vista = estreita ? "parana" : "brasil";

  // 1. A URL decide o estado inicial; sem nada nela, o celular abre no Paraná, que é leve e legível
  useEffect(() => {
    const u = lerUrl();
    const celular = window.matchMedia(TELA_ESTREITA).matches;
    setVista(u.vista ?? (celular ? "parana" : "brasil"));
    setEmLista(u.lista);
    setPartidoFoco(u.partido);
    pendente.current = u.no;
    setIniciado(true);
  }, []);

  // 2. Dados da vista
  useEffect(() => {
    if (!iniciado) return;
    let cancelado = false;
    setDados(null);
    setErro(null);
    setDesenhado(false);
    carregarDados(vista)
      .then((d) => {
        if (cancelado) return;
        setDados(d);
        const id = pendente.current;
        if (id) {
          pendente.current = null;
          const no = d.nos.find((n) => n.id === id);
          if (no && entraNoGrafo(vista, no)) setSelecionado(id);
          else if (no) setAviso({ id, nome: no.rotulo });
        }
      })
      .catch(() => !cancelado && setErro("Não foi possível abrir os dados do grafo. Recarregue a página para tentar de novo."));
    return () => {
      cancelado = true;
    };
  }, [vista, iniciado]);

  // 3. Estado -> URL (replaceState: não enche o histórico, e o Voltar devolve o grafo como estava)
  useEffect(() => {
    if (!iniciado) return;
    const q = new URLSearchParams();
    if (vista !== padrao || selecionado || emLista || partidoFoco) q.set("vista", vista);
    if (selecionado) q.set("no", selecionado);
    if (emLista) q.set("lista", "1");
    if (partidoFoco) q.set("partido", partidoFoco);
    const url = q.size ? `/?${q.toString()}` : "/";
    if (window.location.pathname + window.location.search !== url) window.history.replaceState(window.history.state, "", url);
  }, [iniciado, vista, selecionado, emLista, partidoFoco, padrao]);

  const { cores, legenda } = useMemo(() => (dados ? coresDaVista(dados) : { cores: new Map<string, string>(), legenda: [] as [string, number][] }), [dados]);

  // 4. Monta o sigma
  useEffect(() => {
    if (!dados || emLista || !caixa.current || !bibliotecas) return;
    let sigma: SigmaT | null = null;
    let morto = false;
    (async () => {
      const [{ default: Graph }, { default: Sigma }] = await bibliotecas;
      if (morto || !caixa.current) return;
      const g = new Graph({ type: "undirected", multi: false });
      // a família de verdade que o next/font registrou (no canvas, var() não vale)
      const familia = getComputedStyle(document.documentElement).getPropertyValue("--fonte-archivo").trim() || "Archivo, sans-serif";
      const escala = escalaDoNo(caixa.current.clientWidth);
      for (const n of dados.nos) {
        if (!entraNoGrafo(vista, n)) continue;
        const ehPartido = n.tipo === "partido";
        g.addNode(n.id, {
          x: n.x,
          y: -n.y,
          size: tamanhoDoNo(vista, n, escala),
          label: n.rotulo,
          color: corDoNo(n, cores),
          zIndex: ehPartido ? 1 : 0,
          partido: n.partido,
          tipo: n.tipo ?? "deputado",
          forceLabel: ehPartido,
        });
      }
      for (const a of dados.arestas) {
        if (!g.hasNode(a.a) || !g.hasNode(a.b) || g.hasEdge(a.a, a.b)) continue;
        g.addEdge(a.a, a.b, { size: tamanhoDaAresta(vista, a), color: corDaAresta(vista, a) });
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
      sigma.once("afterRender", () => setDesenhado(true));
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
      // o ponto é pequeno demais para o dedo: um toque perto de um ponto vale como toque nele
      sigma.on("clickStage", ({ event }) => {
        const s = sigma!;
        const raio = ultimoToque.current ? 22 : 8;
        let melhor: string | null = null;
        let dist = raio;
        g.forEachNode((id) => {
          const d = s.getNodeDisplayData(id);
          if (!d || d.hidden) return;
          const p = s.framedGraphToViewport(d);
          const dd = Math.hypot(p.x - event.x, p.y - event.y) - s.scaleSize(d.size);
          if (dd < dist) {
            dist = dd;
            melhor = id;
          }
        });
        setSelecionado(melhor);
      });
      sigmaRef.current = sigma;
      sigma.refresh();
    })();
    return () => {
      morto = true;
      sigma?.kill();
      sigmaRef.current = null;
    };
  }, [dados, emLista, cores, vista]);

  // 5. Estado -> sigma: destaque e câmera no ponto escolhido (no celular, acima da folha da ficha)
  useEffect(() => {
    estado.current.sel = selecionado;
    estado.current.partido = partidoFoco;
    const s = sigmaRef.current;
    if (!s) return;
    s.refresh({ skipIndexation: true });
    if (!selecionado || !grafoRef.current?.hasNode(selecionado)) return;
    const quadroAtual = quadro.current;
    const quadro0 = requestAnimationFrame(() => {
      const d = s.getNodeDisplayData(selecionado);
      if (!d) return;
      const cam = s.getCamera();
      const alvo = { ...cam.getState(), x: d.x, y: d.y, ratio: Math.min(cam.ratio, 0.55) };
      // onde a folha vai parar (a animação de subida ainda está no começo: a medida tem de ser a final)
      const topoFolha = estreita && ficha.current ? window.innerHeight - ficha.current.offsetHeight : null;
      if (topoFolha !== null && quadroAtual) {
        // a folha cobre a base da tela: rola até o quadro aparecer e põe o ponto no meio do que sobra dele
        let q = quadroAtual.getBoundingClientRect();
        if (Math.min(q.bottom, topoFolha) - Math.max(q.top, 0) < q.height * 0.45) {
          window.scrollTo({ top: window.scrollY + q.top - 8 });
          q = quadroAtual.getBoundingClientRect();
        }
        const visivel = (Math.max(q.top, 0) + Math.min(q.bottom, topoFolha)) / 2 - q.top;
        const { height } = s.getDimensions();
        const meio = height / 2;
        const desejo = Math.max(24, Math.min(visivel, height - 24));
        const p = s.viewportToFramedGraph({ x: s.getDimensions().width / 2, y: meio + (meio - desejo) }, { cameraState: alvo });
        alvo.x = p.x;
        alvo.y = p.y;
      } else if (ficha.current) {
        // no computador a ficha fica à esquerda, dentro do quadro: o ponto vai para o meio do que sobra à direita
        const { width, height } = s.getDimensions();
        const direitaDaFicha = ficha.current.offsetLeft + ficha.current.offsetWidth;
        if (width - direitaDaFicha > 160) {
          const desejo = (direitaDaFicha + width) / 2;
          const p = s.viewportToFramedGraph({ x: width / 2 + (width / 2 - desejo), y: height / 2 }, { cameraState: alvo });
          alvo.x = p.x;
          alvo.y = p.y;
        }
      }
      cam.animate(alvo, { duration: 450 });
    });
    return () => cancelAnimationFrame(quadro0);
  }, [selecionado, partidoFoco, estreita, desenhado]);

  // 6. Foco na ficha quando o ponto veio da lista ou da busca do grafo; Esc fecha a ficha
  useEffect(() => {
    if (selecionado && focarFicha.current && tituloFicha.current) {
      focarFicha.current = false;
      tituloFicha.current.focus({ preventScroll: true });
    }
  }, [selecionado, emLista, dados]);
  useEffect(() => {
    if (!selecionado) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && !e.defaultPrevented && setSelecionado(null);
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [selecionado]);

  // 7. Os nomes dos fornecedores chegam quando a primeira ficha da vista Brasil abre
  useEffect(() => {
    if (vista !== "brasil" || !selecionado || fornecedores) return;
    let vivo = true;
    carregarFornecedores().then((f) => vivo && setFornecedores(f));
    return () => {
      vivo = false;
    };
  }, [vista, selecionado, fornecedores]);

  const trocarVista = useCallback((v: Vista) => {
    setVista((atual) => {
      if (atual !== v) {
        setSelecionado(null);
        setPartidoFoco(null);
        setAviso(null);
      }
      return v;
    });
  }, []);

  const escolher = useCallback((id: string) => {
    focarFicha.current = true;
    setAviso(null);
    setEmLista(false);
    setSelecionado(id);
  }, []);

  // a busca do grafo acha a pessoa na vista em que ela está, ou avisa que ela não está no grafo
  const achar = useCallback(
    (item: ItemIndice) => {
      const no = dados?.nos.find((n) => n.id === item.id);
      if (no && entraNoGrafo(vista, no)) {
        escolher(item.id);
        return true;
      }
      const naOutra: Vista | null =
        vista === "brasil" ? (item.casa === "cmc" || item.uf === "PR" ? "parana" : null) : item.casa === "camara-deputados" ? "brasil" : null;
      if (naOutra) {
        focarFicha.current = true;
        pendente.current = item.id;
        setEmLista(false);
        trocarVista(naOutra);
        return true;
      }
      setAviso({ id: item.id, nome: item.nome });
      return true;
    },
    [dados, vista, escolher, trocarVista],
  );

  const camera = (acao: "mais" | "menos" | "centro") => {
    const c = sigmaRef.current?.getCamera();
    if (!c) return;
    if (acao === "mais") c.animatedZoom({ duration: 250 });
    else if (acao === "menos") c.animatedUnzoom({ duration: 250 });
    else {
      setSelecionado(null);
      c.animatedReset({ duration: 300 });
    }
  };

  // abas de verdade: setas, Home e End trocam a vista e levam o foco junto
  const teclaNasAbas = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const i = ABAS.findIndex(([v]) => v === vista);
    const prox =
      e.key === "ArrowRight" ? (i + 1) % ABAS.length : e.key === "ArrowLeft" ? (i - 1 + ABAS.length) % ABAS.length : e.key === "Home" ? 0 : e.key === "End" ? ABAS.length - 1 : -1;
    if (prox < 0) return;
    e.preventDefault();
    trocarVista(ABAS[prox][0]);
    document.getElementById(`aba-${ABAS[prox][0]}`)?.focus();
  };

  const noSel = (selecionado && dados?.nos.find((n) => n.id === selecionado)) || null;
  const ligacoes = useMemo(() => {
    if (!dados || !selecionado) return [];
    return dados.arestas
      .filter((a) => a.a === selecionado || a.b === selecionado)
      .map((a) => ({ ...a, outro: dados.nos.find((n) => n.id === (a.a === selecionado ? a.b : a.a))! }))
      .filter((a) => a.outro)
      .sort((x, y) => (y.peso ?? 0) - (x.peso ?? 0));
  }, [dados, selecionado]);

  const carregando = !erro && (!dados || (!emLista && !desenhado));
  const classeDesenho = "pointer-events-none absolute inset-0 h-full w-full p-[30px]";

  return (
    <div className="relative flex h-full min-h-[560px] flex-col">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 pt-4 sm:px-8">
        <div role="tablist" aria-label="Vista do grafo" className="flex gap-1.5" onKeyDown={teclaNasAbas}>
          {ABAS.map(([v, r, resto]) => (
            <button
              key={v}
              id={`aba-${v}`}
              type="button"
              role="tab"
              aria-selected={vista === v}
              aria-controls="painel-grafo"
              tabIndex={vista === v ? 0 : -1}
              onClick={() => trocarVista(v)}
              className={`min-h-10 rounded-t-[5px] px-3 pb-1.5 pt-2 font-titulo text-[0.9rem] font-medium ${vista === v ? "bg-manilha text-manilha-tinta" : "bg-gaveta-3 text-tinta-2 hover:text-tinta"}`}
            >
              {r}
              <span className="hidden sm:inline">{resto}</span>
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setEmLista((l) => !l)}
          className="-my-2 ml-auto py-2 text-sm text-tinta-2 underline hover:text-tinta"
          aria-pressed={emLista}
        >
          {emLista ? "Voltar ao grafo" : "Ver em lista"}
        </button>
      </div>
      <p className="px-4 pb-2 pt-2 text-[0.82rem] text-tinta-3 sm:px-8">
        Toque ou passe o mouse num ponto para ver com quem ele se liga; aproxime com + e −.
      </p>

      <div className="relative mx-4 flex flex-1 flex-col sm:mx-8">
        <div
          ref={quadro}
          id="painel-grafo"
          role="tabpanel"
          aria-labelledby={`aba-${vista}`}
          className="relative min-h-[440px] flex-1 overflow-hidden border-t-2 border-manilha bg-gaveta-2"
        >
          {/* o desenho do grafo, gerado no build, enquanto o canvas carrega */}
          {carregando && !emLista && (
            <>
              {iniciado ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={`/grafo/${vista}.svg`} alt="" aria-hidden="true" className={classeDesenho} />
              ) : (
                <picture>
                  <source media={TELA_ESTREITA} srcSet="/grafo/parana.svg" />
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src="/grafo/brasil.svg" alt="" aria-hidden="true" className={classeDesenho} />
                </picture>
              )}
              <p role="status" className="absolute bottom-3 left-3 z-10 rounded-[3px] bg-gaveta/90 px-2.5 py-1 text-[0.82rem] text-tinta-3">
                Abrindo o grafo…
              </p>
            </>
          )}
          {erro && <p className="relative p-6 text-tinta-2">{erro}</p>}
          {dados && !emLista && (
            <div
              ref={caixa}
              className={`absolute inset-0 ${desenhado ? "" : "opacity-0"}`}
              aria-label={`Grafo ${vista === "brasil" ? "Brasil, por fornecedor em comum" : "Paraná, por partido"}. Use a busca do grafo ou a lista para navegar pelo teclado.`}
              role="img"
              onPointerDown={(e) => {
                ultimoToque.current = e.pointerType !== "mouse";
              }}
            />
          )}
          {dados && emLista && <Lista dados={dados} escolher={escolher} vista={vista} />}

          {!emLista && (
            <>
              <div className="absolute left-3 right-[3.75rem] top-3 z-20 sm:right-auto sm:w-72">
                <Busca aoEscolher={achar} rotulo="Achar alguém no grafo" placeholder="Achar alguém no grafo" className="" />
                {aviso && (
                  <p role="status" className="mt-1.5 rounded-[3px] bg-gaveta/95 px-2.5 py-1.5 text-[0.82rem] leading-snug text-tinta-2">
                    {aviso.nome} não aparece {vista === "brasil" ? "nesta vista: não divide fornecedor com outro deputado acima do corte" : "nesta vista"}.{" "}
                    <Link href={`/parlamentares/${aviso.id}/`} className="text-carimbo-claro underline">
                      Abrir as despesas
                    </Link>
                  </p>
                )}
              </div>
              <div className="absolute right-3 top-3 z-10 flex flex-col overflow-hidden rounded-md border border-contorno bg-gaveta/90">
                {(
                  [
                    ["mais", "Aproximar", "M10 4v12M4 10h12"],
                    ["menos", "Afastar", "M4 10h12"],
                    ["centro", "Ver o grafo inteiro", "M4 8V4h4M12 4h4v4M16 12v4h-4M8 16H4v-4"],
                  ] as const
                ).map(([acao, nome, d], i) => (
                  <button
                    key={acao}
                    type="button"
                    onClick={() => camera(acao)}
                    aria-label={nome}
                    title={nome}
                    disabled={!desenhado}
                    className={`grid size-10 place-items-center text-tinta-2 hover:bg-gaveta-3 hover:text-tinta disabled:text-tinta-3/50 ${i > 0 ? "border-t border-contorno" : ""}`}
                  >
                    <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <path d={d} />
                    </svg>
                  </button>
                ))}
              </div>
            </>
          )}

          {noSel && !emLista && (
            <aside
              ref={ficha}
              aria-labelledby="ficha-no-titulo"
              className={
                estreita
                  ? "ficha-sobe fixed inset-x-0 bottom-0 z-40 max-h-[55dvh] overflow-y-auto overscroll-contain rounded-t-[3px] bg-manilha px-4 pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-4 text-manilha-tinta shadow-[0_-14px_30px_-8px_rgba(0,0,0,0.6)]"
                  : "ficha-sai absolute bottom-4 left-4 z-30 max-h-[calc(100%-5.5rem)] w-[min(26rem,calc(100%-2rem))] overflow-y-auto overscroll-contain rounded-[3px] bg-manilha p-4 text-manilha-tinta shadow-[0_18px_36px_-12px_rgba(0,0,0,0.7)]"
              }
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 id="ficha-no-titulo" ref={tituloFicha} tabIndex={-1} className="font-titulo text-lg font-semibold leading-tight focus:outline-none">
                    {noSel.rotulo}
                  </h2>
                  <p className="text-sm text-manilha-tinta-2">
                    {noSel.tipo === "partido"
                      ? "Partido"
                      : `${noSel.partido ?? "sem partido"} · ${noSel.tipo === "vereador" ? "vereador(a) de Curitiba" : `deputado(a) · ${noSel.uf ?? "PR"}`}`}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setSelecionado(null)}
                  className="-mr-2 -mt-2 min-h-11 shrink-0 px-2 text-sm text-manilha-tinta-2 hover:text-manilha-tinta hover:underline"
                >
                  fechar
                </button>
              </div>
              {vista === "brasil" && ligacoes.length > 0 && (
                <div className="mt-3 border-t border-manilha-tinta/20 pt-2 text-sm">
                  <p className="text-manilha-tinta-2">Contratou os mesmos fornecedores que:</p>
                  <ul className="mt-1 space-y-2">
                    {ligacoes.map((l) => (
                      <li key={l.outro.id}>
                        <button type="button" onClick={() => setSelecionado(l.outro.id)} className="text-left font-medium underline">
                          {l.outro.rotulo}
                        </button>
                        <span className="text-manilha-tinta-2">
                          {" "}
                          ({l.outro.partido ?? "—"}/{l.outro.uf})
                        </span>
                        {l.f && l.f.length > 0 && (
                          <span className="block text-[0.78rem] leading-snug text-manilha-tinta-2">
                            {fornecedores ? l.f.map((i) => fornecedores[i]?.[1] ?? fornecedores[i]?.[0]).join(" · ") : "abrindo os nomes dos fornecedores…"}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {vista === "parana" && noSel.tipo !== "partido" && (
                <p className="mt-2 text-sm text-manilha-tinta-2">Ligado aos partidos pelos quais teve mandato; a linha mais forte é o partido atual.</p>
              )}
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm">
                {noSel.tipo === "partido" ? (
                  <Link href={`/partidos/${slug(noSel.rotulo)}/`} className="inline-block py-1 font-medium text-carimbo-escuro underline">
                    Abrir o partido {noSel.rotulo}
                  </Link>
                ) : (
                  <Link href={`/parlamentares/${noSel.id}/`} className="inline-block py-1 font-medium text-carimbo-escuro underline">
                    Abrir as despesas de {noSel.rotulo}
                  </Link>
                )}
              </div>
            </aside>
          )}
        </div>

        {/* legenda: embaixo do quadro no celular; dentro dele, no canto, no computador */}
        <div className="pt-3 lg:pointer-events-none lg:absolute lg:bottom-3 lg:right-3 lg:z-10 lg:max-w-[23rem] lg:pt-0">
          <ul
            className="flex flex-wrap gap-1.5 lg:pointer-events-auto lg:justify-end lg:rounded-[3px] lg:bg-gaveta/90 lg:p-1.5"
            aria-label="Partidos; clique para destacar"
          >
            {legenda.slice(0, 10).map(([sigla, n]) => (
              <li key={sigla}>
                <button
                  type="button"
                  onClick={() => setPartidoFoco((p) => (p === sigla ? null : sigla))}
                  aria-pressed={partidoFoco === sigla}
                  className={`flex min-h-8 items-center gap-1.5 rounded-[3px] px-2 py-1 text-[0.8rem] ${partidoFoco === sigla ? "bg-gaveta-3 text-tinta ring-1 ring-carimbo-claro" : "text-tinta-2 hover:text-tinta"}`}
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
        </div>
      </div>

      <div className="px-4 pb-4 pt-3 sm:px-8">
        <p className="sr-only">Legenda: cor do ponto = partido.</p>
        {dados && (
          <div className="max-w-[80ch] text-[0.82rem] leading-relaxed text-tinta-3">
            <p>{dados.regra}</p>
            {dados.regra_tecnica && (
              <details className="mt-1">
                <summary className="cursor-pointer underline decoration-tinta-3/50 underline-offset-2 hover:text-tinta-2">a conta, em detalhe</summary>
                <p className="mt-1">{dados.regra_tecnica}</p>
              </details>
            )}
          </div>
        )}
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
  const fora = (n: No) => !entraNoGrafo(vista, n);
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
