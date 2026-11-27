import Link from "next/link";
import { CarimboRevisao } from "@/componentes/EmRevisao";
import Valor from "@/componentes/Valor";
import { MODO } from "@/lib/fontes";
import { contagem, data, inteiro, listaE } from "@/lib/formato";
import type {
  AtividadeDoParlamentar,
  AtividadeFrequencia,
  AtividadeSapl,
  CasaAtividade,
  CasaAtividadeFrequencia,
  CasaAtividadeSapl,
  Procedencia,
  Rotulado,
} from "@/lib/tipos";

/**
 * Atividade nas sessões: presença, ausência com o motivo que a fonte der e voto
 * nominal por tipo. Só contagem bruta, cada número com a sua ficha. Não há taxa,
 * ordem por quem falta mais, cor de alerta nem adjetivo: a lista é alfabética e o
 * texto diz por que um número pode ser menor (posse ou saída no meio do período).
 *
 * O que a coleta ainda não leu nunca aparece como zero: aparece "ainda não lido".
 */

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

/** "2026-10" → "out/2026"; "2019" → "2019" (relatório anual). */
export function periodo(p: string | null | undefined): string {
  if (!p) return "—";
  const [a, m] = p.split("-");
  return m ? `${MESES[Number(m) - 1]}/${a}` : a;
}

const ROTULO_FREQ = {
  presenca_ou_falta_justificada: "Presença ou falta justificada",
  falta_descontada: "Falta descontada",
  licenca: "Licença",
} as const;
type ColunaFreq = keyof typeof ROTULO_FREQ;
const COLUNAS = Object.keys(ROTULO_FREQ) as ColunaFreq[];

/** Um número da atividade com a ficha de procedência (o mesmo gesto do valor em reais). */
function Contagem({ n, p, tamanho, className }: { n: number; p: Procedencia; tamanho?: "pequeno" | "medio" | "grande"; className?: string }) {
  return <Valor valor={String(n)} texto={inteiro(n)} p={p} tamanho={tamanho} className={className} />;
}

/** O lugar de um número que a coleta ainda não leu. Sem ficha: não há número. */
function NaoLido({ className = "" }: { className?: string }) {
  return <span className={`text-sm text-tinta-3 ${className}`}>ainda não lido</span>;
}

function ehSapl(a: AtividadeDoParlamentar): a is AtividadeSapl {
  return "presencas" in a;
}

function ehSaplCasa(a: CasaAtividade): a is CasaAtividadeSapl {
  return "presencas" in a;
}

function Parcial({ presenca, votos, ausencias }: { presenca: string | null; votos: string | null; ausencias: boolean }) {
  const lido = [
    presenca ? `a presença até ${data(presenca)}` : null,
    votos ? `os votos até ${data(votos)}` : null,
    ausencias ? "as ausências justificadas" : null,
  ].filter((x): x is string => Boolean(x));
  return (
    <p className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm text-tinta-2">
      <CarimboRevisao>COLETA PARCIAL</CarimboRevisao>
      <span>
        O robô ainda está lendo esta câmara, uma página por minuto. Até agora entrou {lido.length ? listaE(lido) : "só a lista de sessões"}; o
        resto aparece como &ldquo;ainda não lido&rdquo;.
      </span>
    </p>
  );
}

function ListaRotulos({ itens, p, vazio }: { itens: Rotulado[]; p: (r: Rotulado) => Procedencia; vazio: string }) {
  if (!itens.length) return <p className="mt-1 text-sm text-tinta-3">{vazio}</p>;
  return (
    <ul className="mt-1.5 space-y-1 text-sm">
      {itens.map((r) => (
        <li key={r.rotulo} className="flex items-baseline justify-between gap-3 border-t border-aco pt-1">
          <span className="min-w-0 text-tinta-2">{r.rotulo}</span>
          <Contagem n={r.n} p={p(r)} className="shrink-0" />
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------- parlamentar

export function AtividadeDoParlamentar({ atividade, nome }: { atividade: AtividadeDoParlamentar[]; nome: string }) {
  if (!atividade.length) return null;
  return (
    <section aria-labelledby="nas-sessoes">
      <h2 id="nas-sessoes" className="font-titulo text-lg font-medium">
        Nas sessões
      </h2>
      {atividade.map((a) => (ehSapl(a) ? <SaplDoParlamentar key={a.fonte} a={a} nome={nome} /> : <FrequenciaDoParlamentar key={a.fonte} a={a} />))}
    </section>
  );
}

function Bloco({ titulo, total, children }: { titulo: string; total?: number | null; children: React.ReactNode }) {
  return (
    <div className="mt-3 border-t border-aco pt-3">
      <p className="text-sm text-tinta-2">
        {titulo}
        {total ? <span className="num text-tinta-3"> · {inteiro(total)}</span> : null}
      </p>
      {children}
    </div>
  );
}

function SaplDoParlamentar({ a, nome }: { a: AtividadeSapl; nome: string }) {
  const proc = (registros: string, nota: string, ate: string | null): Procedencia => ({
    fontes: [a.fonte],
    coleta: a.coleta,
    documento: a.documento,
    situacao: "contagem",
    registros,
    local: `sessões de ${data(a.de)} a ${data(ate ?? a.ate)}, no cadastro do parlamentar no SAPL da Câmara`,
    nota,
  });
  const votos = a.votos.reduce((s, v) => s + v.n, 0);
  const ausencias = a.ausencias.reduce((s, v) => s + v.n, 0);
  return (
    <div className="mt-1">
      <p className="text-sm text-tinta-3">
        O que o sistema legislativo da Câmara (SAPL) registra
        {a.situacao === "completa" ? ` de ${data(a.de)} a ${data(a.ate)}` : ` desde ${data(a.de)}`}, contado registro a registro.
      </p>
      {a.situacao === "parcial" && <Parcial presenca={a.presenca_ate} votos={a.votos_ate} ausencias={a.ausencias_lidas} />}
      <Bloco titulo="Presença registrada">
        {a.presenca_ate === null ? (
          <NaoLido className="mt-0.5 block" />
        ) : (
          <>
            <p className="mt-0.5">
              <Contagem
                n={a.presencas}
                tamanho="medio"
                p={proc(contagem(a.presencas, "registro de presença", "registros de presença"), `sessões em que ${nome} consta como presente`, a.presenca_ate)}
              />{" "}
              <span className="text-sm text-tinta-3">{a.presencas === 1 ? "sessão" : "sessões"}</span>
            </p>
            <p className="mt-1 text-sm leading-relaxed text-tinta-3">
              De {data(a.de)} a {data(a.presenca_ate)}, a Câmara fez {contagem(a.sessoes_da_casa, "sessão", "sessões")} e registrou presença no
              sistema em {a.sessoes_com_presenca_registrada === a.sessoes_da_casa ? "todas" : `${inteiro(a.sessoes_com_presenca_registrada)} delas`}.
              Quem tomou posse ou saiu no meio do período tem menos.
            </p>
          </>
        )}
      </Bloco>
      <Bloco titulo="Ausências justificadas" total={a.ausencias_lidas ? ausencias : null}>
        {a.ausencias_lidas ? (
          <ListaRotulos
            itens={a.ausencias}
            vazio="Nenhuma justificativa de ausência registrada."
            p={(r) => proc(contagem(r.n, "justificativa de ausência", "justificativas de ausência"), `motivo, como o SAPL escreve: "${r.rotulo}"`, a.ate)}
          />
        ) : (
          <NaoLido className="mt-0.5 block" />
        )}
      </Bloco>
      <Bloco titulo={a.votos_ate && a.situacao === "parcial" ? `Votos nominais, até ${data(a.votos_ate)}` : "Votos nominais"} total={a.votos_ate ? votos : null}>
        {a.votos_ate === null ? (
          <NaoLido className="mt-0.5 block" />
        ) : (
          <ListaRotulos
            itens={a.votos}
            vazio="Nenhum voto nominal registrado."
            p={(r) => proc(contagem(r.n, "voto nominal", "votos nominais"), `voto registrado como "${r.rotulo}"`, a.votos_ate)}
          />
        )}
      </Bloco>
      <p className="mt-3 text-sm">
        <a href={a.documento} className="text-carimbo-claro underline" rel="noreferrer">
          Ver no SAPL da Câmara
        </a>
      </p>
    </div>
  );
}

function FrequenciaDoParlamentar({ a }: { a: AtividadeFrequencia }) {
  const proc = (situacao: "soma" | "da_fonte", registros: string, nota: string, local?: string): Procedencia => ({
    fontes: [a.fonte],
    coleta: a.coleta,
    documento: a.documento,
    situacao,
    registros,
    nota,
    local: local ?? null,
  });
  const temAnual = a.por_ano.some((x) => x.anual);
  // o ano em que o nome não aparece entra na tabela, dito, em vez de sumir
  const linhas = [
    ...a.por_ano.map((x) => ({ ano: x.ano, x })),
    ...(a.anos_sem_o_nome ?? []).map((ano) => ({ ano, x: null })),
  ].sort((p, q) => q.ano - p.ano);
  return (
    <div className="mt-1">
      <p className="text-sm text-tinta-3">
        Os relatórios de frequência que a Câmara publica{temAnual ? " (anuais em 2019 e 2020, mensais depois)" : ", mês a mês"}, de{" "}
        {periodo(a.de)} a {periodo(a.ate)}. A Câmara põe presença e falta justificada na mesma coluna.
      </p>
      <table className="mt-3 w-full text-left text-[0.84rem]">
        <caption className="sr-only">Frequência nas sessões por ano, com as colunas dos relatórios da Câmara</caption>
        <thead className="text-[0.74rem] leading-tight text-tinta-3">
          <tr className="border-b border-aco-2">
            <th scope="col" className="py-1.5 pr-2 font-normal">
              Ano
            </th>
            {COLUNAS.map((c) => (
              <th key={c} scope="col" className="py-1.5 pl-2 text-right font-normal">
                {ROTULO_FREQ[c]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {linhas.map(({ ano, x }) => (
            <tr key={ano} className="border-b border-aco">
              <th scope="row" className="py-1.5 pr-2 text-left align-top font-normal text-tinta">
                <span className="num">{ano}</span>
                {x && (
                  <span className="block whitespace-nowrap text-[0.74rem] text-tinta-3">
                    {x.anual ? "relatório anual" : contagem(x.relatorios, "mês", "meses")}
                  </span>
                )}
              </th>
              {!x ? (
                <td colSpan={3} className="py-1.5 pl-2 text-right align-top text-[0.8rem] text-tinta-3">
                  o nome não aparece nos relatórios deste ano
                </td>
              ) : x.presidiu === x.relatorios ? (
                <td colSpan={3} className="py-1.5 pl-2 text-right align-top text-[0.8rem] text-tinta-3">
                  presidiu as sessões: a Câmara não conta frequência de quem preside
                </td>
              ) : (
                COLUNAS.map((c) => (
                  <td key={c} className="py-1.5 pl-2 text-right align-top">
                    <Contagem
                      n={x[c]}
                      p={proc(
                        x.anual ? "da_fonte" : "soma",
                        x.anual ? "1 relatório anual" : `soma de ${contagem(x.relatorios - x.presidiu, "relatório mensal", "relatórios mensais")}`,
                        `coluna "${ROTULO_FREQ[c]}" dos relatórios de frequência da Câmara, ${ano}` +
                          (x.presidiu ? `; em ${contagem(x.presidiu, "mês presidiu", "meses presidiu")} as sessões e a Câmara não contou` : ""),
                      )}
                    />
                    {c === "licenca" && x.presidiu > 0 && (
                      <span className="block whitespace-nowrap text-[0.74rem] text-tinta-3">{contagem(x.presidiu, "mês presidindo", "meses presidindo")}</span>
                    )}
                  </td>
                ))
              )}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-[0.8rem] leading-snug text-tinta-3">
        Falta descontada é a falta sem justificativa aceita: pela nota da própria Câmara, cada uma desconta um dia do subsídio. Quem tomou posse
        ou saiu no meio do mês tem menos sessões; a nota do mês diz.
      </p>
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-tinta-2 hover:text-tinta">Mês a mês, com as notas da Câmara</summary>
        <ul className="mt-2 space-y-2.5">
          {a.periodos.map((m) => (
            <li key={m.periodo} className="border-t border-aco pt-1.5">
              <p className="flex flex-wrap items-baseline justify-between gap-x-3">
                <span className="num font-medium text-tinta">{periodo(m.periodo)}</span>
                <span className="num text-[0.78rem] text-tinta-3">
                  {m.sessoes != null ? contagem(m.sessoes, "sessão no mês", "sessões no mês") : "o relatório não diz quantas sessões"}
                </span>
              </p>
              {m.presidiu ? (
                <p className="text-tinta-3">Presidiu as sessões: a Câmara não conta a frequência.</p>
              ) : (
                <dl className="mt-0.5 grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 text-tinta-2">
                  {COLUNAS.map((c) => (
                    <div key={c} className="contents">
                      <dt>{ROTULO_FREQ[c]}</dt>
                      <dd className="text-right">
                        <Contagem n={m[c] ?? 0} p={proc("da_fonte", "1 linha da tabela do relatório", `coluna "${ROTULO_FREQ[c]}", ${periodo(m.periodo)}`, m.loc)} />
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
              {m.nota && <p className="mt-1 text-[0.8rem] leading-snug text-tinta-3">Nota da Câmara: {m.nota}</p>}
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}

// ---------------------------------------------------------------- casa

function equacao(conf: CasaAtividade["conferencia"]): { origem: string; publicadas: string; revisao: string; fora: string | null } | null {
  const m = /coletado = (\d+); revisão = (\d+)(?:; fora da janela = (\d+))?/.exec(conf?.detalhe ?? "");
  if (!conf?.esperado || !m) return null;
  return { origem: conf.esperado, publicadas: m[1], revisao: m[2], fora: m[3] ?? null };
}

function FichaSistema({ a, unidade, children }: { a: CasaAtividade; unidade: string; children?: React.ReactNode }) {
  const eq = equacao(a.conferencia);
  const fecha = a.conferencia?.resultado === "confere";
  const parcial = a.situacao === "parcial";
  return (
    <div className="relative rounded-[3px] bg-manilha px-4 py-3.5 text-manilha-tinta">
      <div className="pr-32">
        <h3 className="font-titulo text-[1.02rem] font-semibold leading-tight">{a.sistema}</h3>
        <p className="mt-0.5 text-[0.8rem] text-manilha-tinta-2">
          {a.fornecedor} · {MODO[a.modo] ?? a.modo}
        </p>
      </div>
      {eq && (
        <p className="num mt-2 text-[0.86rem] leading-snug">
          <span className="font-titulo text-[1.35rem] font-semibold">{inteiro(eq.origem)}</span> {unidade} {parcial ? "lidos até agora" : "na origem"}
          <span className="text-manilha-tinta-2">
            {" "}
            = {inteiro(eq.publicadas)} publicados + {inteiro(eq.revisao)} em revisão
            {eq.fora ? ` + ${inteiro(eq.fora)} de sessões de fora do período` : ""}
          </span>
        </p>
      )}
      {children}
      <p className="mt-2 text-[0.8rem]">
        <a href={a.endereco} className="break-all text-carimbo-escuro underline underline-offset-[3px]" rel="noreferrer">
          {a.endereco.replace(/^https?:\/\//, "")}
        </a>
      </p>
      <span
        className={`pointer-events-none absolute right-3 top-3 rounded-[3px] border-2 px-1.5 py-0.5 font-titulo text-[0.66rem] font-semibold tracking-[0.08em] ${fecha && !parcial ? "border-carimbo-escuro text-carimbo-escuro" : "border-sepia text-sepia"}`}
        style={{ transform: "rotate(-6deg)" }}
      >
        {parcial ? "COLETA PARCIAL" : fecha ? "CONFERIDO" : "VER CONFERÊNCIA"}
      </span>
    </div>
  );
}

export function AtividadeDaCasa({ atividade }: { atividade: CasaAtividade[] }) {
  if (!atividade.length) return null;
  return (
    <section id="nas-sessoes" aria-labelledby="nas-sessoes-t" className="scroll-mt-6 border-t border-aco pt-10">
      <h2 id="nas-sessoes-t" className="font-titulo text-2xl font-medium">
        Nas sessões
      </h2>
      <p className="mt-1 max-w-[62ch] text-sm text-tinta-3">
        Outro tipo de dado, de outro sistema: o que a Câmara registra das sessões plenárias. Não entra em soma nenhuma em reais. Só contagem
        bruta, com a fonte de cada número, e os vereadores em ordem alfabética.
      </p>
      {atividade.map((a) => (ehSaplCasa(a) ? <SaplDaCasa key={a.fonte} a={a} /> : <FrequenciaDaCasa key={a.fonte} a={a} />))}
    </section>
  );
}

function EmRevisaoAtividade({ itens }: { itens: CasaAtividade["em_revisao"] }) {
  if (!itens.length) return null;
  return (
    <div className="mt-6">
      <h3 className="font-titulo text-lg font-medium">Em revisão, fora da publicação</h3>
      <p className="mt-1 max-w-[62ch] text-sm text-tinta-3">
        Nome que não fechou com nenhum vereador das fontes de despesa (ou fechou com mais de um), e linha que o robô não leu com certeza. Não
        aparece em página de vereador até alguém conferir.
      </p>
      <ul className="mt-2 space-y-1.5 text-sm">
        {itens.map((r) => (
          <li key={r.motivo} className="border-t border-aco pt-1.5 text-tinta-2">
            {r.motivo}{" "}
            <span className="num text-tinta-3">
              · {contagem(r.n, "caso", "casos")}, {contagem(r.registros, "registro", "registros")}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SaplDaCasa({ a }: { a: CasaAtividadeSapl }) {
  const proc = (registros: string, nota: string, ate: string | null): Procedencia => ({
    fontes: [a.fonte],
    coleta: a.coleta,
    documento: a.endereco,
    situacao: "contagem",
    registros,
    nota,
    local: `API do SAPL, sessões de ${data(a.de)} a ${data(ate ?? a.ate)}`,
  });
  const votos = a.votos.reduce((s, v) => s + v.n, 0);
  const ausencias = a.ausencias.reduce((s, x) => s + x.n, 0);
  const presencaLida = a.presenca_ate !== null;
  const votosLidos = a.votos_ate !== null;
  return (
    <div className="mt-5">
      <div className="grid gap-6 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <FichaSistema a={a} unidade="registros">
          <p className="mt-2 text-[0.8rem] leading-snug text-manilha-tinta-2">
            Sessões de {data(a.de)} a {data(a.ate)}. {inteiro(a.pedidos_feitos)} de {contagem(a.pedidos, "pedido", "pedidos")} à API, um por minuto: o
            robots.txt do SAPL pede {a.crawl_delay} segundos entre pedidos.
          </p>
        </FichaSistema>
        <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-2 self-start text-[0.92rem]">
          <dt className="text-tinta-2">Sessões no período</dt>
          <dd className="text-right">
            <Contagem n={a.sessoes} p={proc(contagem(a.sessoes, "sessão plenária", "sessões plenárias"), "a lista de sessões do SAPL", a.ate)} />
          </dd>
          {a.sessoes_por_tipo.map((t) => (
            <div key={t.rotulo} className="contents text-sm text-tinta-3">
              <dt className="pl-3">{t.rotulo}</dt>
              <dd className="num text-right">{inteiro(t.n)}</dd>
            </div>
          ))}
          <dt className="text-tinta-2">Sessões com presença registrada</dt>
          <dd className="text-right">
            {presencaLida ? (
              <Contagem
                n={a.sessoes_com_presenca_registrada}
                p={proc(
                  contagem(a.sessoes_com_presenca_registrada, "sessão", "sessões"),
                  "sessões em que o sistema da Câmara tem pelo menos um vereador presente",
                  a.presenca_ate,
                )}
              />
            ) : (
              <NaoLido />
            )}
          </dd>
          {presencaLida && a.sessoes_com_presenca_coletada < a.sessoes && (
            <dd className="col-span-2 -mt-1.5 text-[0.8rem] text-tinta-3">
              entre as {inteiro(a.sessoes_com_presenca_coletada)} sessões até {data(a.presenca_ate)}, as que o robô já leu
            </dd>
          )}
          <dt className="text-tinta-2">Registros de presença</dt>
          <dd className="text-right">
            {presencaLida ? (
              <Contagem n={a.presencas} p={proc(contagem(a.presencas, "registro de presença", "registros de presença"), "presenças dos vereadores identificados", a.presenca_ate)} />
            ) : (
              <NaoLido />
            )}
          </dd>
          <dt className="text-tinta-2">Ausências justificadas</dt>
          <dd className="text-right">
            {a.ausencias_lidas ? (
              <Contagem
                n={ausencias}
                p={proc("justificativas de ausência dos vereadores identificados", a.ausencias.map((x) => `${x.rotulo}: ${x.n}`).join("; ") || "nenhuma", a.ate)}
              />
            ) : (
              <NaoLido />
            )}
          </dd>
          <dt className="text-tinta-2">Votos nominais</dt>
          <dd className="text-right">
            {votosLidos ? (
              <Contagem n={votos} p={proc(contagem(votos, "voto nominal", "votos nominais"), a.votos.map((x) => `${x.rotulo}: ${x.n}`).join("; ") || "nenhum", a.votos_ate)} />
            ) : (
              <NaoLido />
            )}
          </dd>
          {votosLidos &&
            a.votos.map((t) => (
              <div key={t.rotulo} className="contents text-sm text-tinta-3">
                <dt className="pl-3">{t.rotulo}</dt>
                <dd className="num text-right">{inteiro(t.n)}</dd>
              </div>
            ))}
        </dl>
      </div>
      {a.situacao === "parcial" && <Parcial presenca={a.presenca_ate} votos={a.votos_ate} ausencias={a.ausencias_lidas} />}
      {a.vereadores.length > 0 && (
        <div className="mt-6">
          <h3 className="font-titulo text-lg font-medium">Vereadores</h3>
          <p className="mt-1 max-w-[62ch] text-sm text-tinta-3">
            Em ordem alfabética. Quem tomou posse ou saiu no meio do período tem menos sessões. A ficha de cada número, com o motivo de cada
            ausência e o tipo de cada voto, está na página do vereador.
          </p>
          <table className="mt-3 hidden w-full text-left text-[0.92rem] sm:table">
            <caption className="sr-only">Atividade de cada vereador no SAPL, em ordem alfabética</caption>
            <thead className="text-[0.78rem] text-tinta-3">
              <tr className="border-b border-aco-2">
                <th scope="col" className="py-2 pr-4 font-normal">
                  Vereador
                </th>
                <th scope="col" className="py-2 pl-4 text-right font-normal">
                  Presença registrada
                </th>
                <th scope="col" className="py-2 pl-4 text-right font-normal">
                  Ausências justificadas
                </th>
                <th scope="col" className="py-2 pl-4 text-right font-normal">
                  Votos nominais
                </th>
              </tr>
            </thead>
            <tbody>
              {a.vereadores.map((v) => (
                <tr key={v.id} className="border-b border-aco">
                  <th scope="row" className="py-1.5 pr-4 text-left font-normal">
                    <Link href={`/parlamentares/${v.id}/`} className="hover:text-carimbo-claro hover:underline">
                      {v.nome}
                    </Link>
                  </th>
                  <td className="num py-1.5 pl-4 text-right text-tinta-2">{presencaLida ? inteiro(v.presencas) : "—"}</td>
                  <td className="num py-1.5 pl-4 text-right text-tinta-2">{a.ausencias_lidas ? inteiro(v.ausencias) : "—"}</td>
                  <td className="num py-1.5 pl-4 text-right text-tinta-2">{votosLidos ? inteiro(v.votos) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {/* no celular, a mesma informação em lista: sem rolagem de lado */}
          <ul className="mt-3 text-[0.92rem] sm:hidden">
            {a.vereadores.map((v) => (
              <li key={v.id} className="border-t border-aco py-2">
                <Link href={`/parlamentares/${v.id}/`} className="hover:text-carimbo-claro hover:underline">
                  {v.nome}
                </Link>
                <span className="num block text-sm text-tinta-3">
                  presença: {presencaLida ? inteiro(v.presencas) : "ainda não lida"} · ausências justificadas:{" "}
                  {a.ausencias_lidas ? inteiro(v.ausencias) : "ainda não lidas"} · votos: {votosLidos ? inteiro(v.votos) : "ainda não lidos"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <EmRevisaoAtividade itens={a.em_revisao} />
    </div>
  );
}

function FrequenciaDaCasa({ a }: { a: CasaAtividadeFrequencia }) {
  return (
    <div className="mt-5">
      <div className="grid gap-6 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <FichaSistema a={a} unidade="linhas de vereador">
          <p className="mt-2 text-[0.8rem] leading-snug text-manilha-tinta-2">
            {contagem(a.relatorios, "relatório", "relatórios")}, de {periodo(a.de)} a {periodo(a.ate)}. O PDF só aparece depois de &ldquo;Ver
            arquivos&rdquo;, num link que vence em 24 horas: o robô abre a consulta, clica e baixa na hora.
            {a.consolidados_nao_somados > 0 &&
              ` ${a.consolidados_nao_somados === 1 ? "O consolidado anual repete" : `Os ${a.consolidados_nao_somados} consolidados anuais repetem`} os meses e ${a.consolidados_nao_somados === 1 ? "não entra" : "não entram"} na conta.`}
          </p>
        </FichaSistema>
        <table className="self-start text-left text-[0.92rem]">
          <caption className="sr-only">Relatórios de frequência por ano</caption>
          <thead className="text-[0.78rem] text-tinta-3">
            <tr className="border-b border-aco-2">
              <th scope="col" className="py-2 pr-4 font-normal">
                Ano
              </th>
              <th scope="col" className="py-2 pl-4 text-right font-normal">
                Relatórios
              </th>
              <th scope="col" className="py-2 pl-4 text-right font-normal">
                Sessões, segundo os relatórios
              </th>
            </tr>
          </thead>
          <tbody>
            {a.por_ano.map((x) => (
              <tr key={x.ano} className="border-b border-aco">
                <th scope="row" className="num py-1.5 pr-4 text-left font-normal">
                  {x.ano}
                </th>
                <td className="num py-1.5 pl-4 text-right text-tinta-2">{x.anual ? "anual" : inteiro(x.relatorios)}</td>
                <td className="num py-1.5 pl-4 text-right text-tinta-2">
                  {x.sessoes_sem_nota === x.relatorios ? (
                    <span className="text-sm text-tinta-3">o relatório não diz</span>
                  ) : (
                    <>
                      <Contagem
                        n={x.sessoes}
                        p={{
                          fontes: [a.fonte],
                          coleta: a.coleta,
                          documento: a.endereco,
                          situacao: "soma",
                          registros: `soma das notas "foram realizadas N sessões" de ${contagem(x.relatorios - x.sessoes_sem_nota, "relatório", "relatórios")}`,
                          nota: x.sessoes_sem_nota ? `${contagem(x.sessoes_sem_nota, "relatório não diz", "relatórios não dizem")} quantas sessões houve` : null,
                        }}
                      />
                      {x.sessoes_sem_nota > 0 && (
                        <span className="block whitespace-nowrap text-[0.74rem] text-tinta-3">
                          {contagem(x.sessoes_sem_nota, "mês sem o número", "meses sem o número")}
                        </span>
                      )}
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {a.vereadores.length > 0 && (
        <details className="mt-6">
          <summary className="cursor-pointer font-titulo text-lg font-medium hover:text-carimbo-claro">
            Vereadores nos relatórios <span className="num text-sm font-normal text-tinta-3">· {inteiro(a.vereadores.length)}</span>
          </summary>
          <p className="mt-1 text-sm text-tinta-3">Em ordem alfabética. A frequência de cada um, ano a ano e mês a mês, está na página dele.</p>
          <ul className="mt-3 columns-1 gap-8 text-[0.92rem] sm:columns-2 lg:columns-3">
            {a.vereadores.map((v) => (
              <li key={v.id} className="flex break-inside-avoid items-baseline justify-between gap-3 border-t border-aco py-1.5">
                <Link href={`/parlamentares/${v.id}/`} className="min-w-0 hover:text-carimbo-claro hover:underline">
                  {v.nome}
                </Link>
                <span className="num shrink-0 text-sm text-tinta-3">{contagem(v.relatorios, "relatório", "relatórios")}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      <EmRevisaoAtividade itens={a.em_revisao} />
    </div>
  );
}
