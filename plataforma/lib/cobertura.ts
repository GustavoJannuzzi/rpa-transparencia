/** Situação de cada casa na página Cobertura: o que a coleta mediu e, para as que
 * ficaram de fora, o motivo em português de leigo. As chaves vêm do `publicar`. */

export type Classe = "coletada" | "em_revisao" | "barrada" | "sem_adaptador" | "nao_identificado" | "outra";

/** Por que a casa ficou de fora, como o levantamento (ou a coleta) achou. */
export const MOTIVO_FORA: Record<string, string> = {
  robots: "O robots.txt do portal proíbe a consulta.",
  robots_cloudflare: "O robots.txt do portal proíbe a consulta, e ela ainda passa por um desafio da Cloudflare.",
  cloudflare: "A consulta passa por um desafio da Cloudflare.",
  anti_robo: "O portal tem proteção contra robô.",
  captcha: "A consulta pede captcha, e o robots.txt proíbe a API. Captcha nunca é contornado.",
  sistema_interno: "O sistema achado é interno (pede CPF), não um portal de consulta.",
  na_fila: "O fornecedor do portal já tem adaptador, e a câmara ainda não está na lista de coleta.",
  sem_consulta_diarias: "O portal da câmara não tem a consulta de diárias com o cargo de quem recebeu.",
  sem_adaptador: "O fornecedor do portal ainda não tem adaptador.",
  em_coleta: "O robô desta casa está pronto e a coleta está em andamento. Os dados entram no site quando ela terminar e for conferida.",
  reserva: "Fonte aberta, na reserva: ainda sem adaptador.",
  sem_fornecedor: "A fonte só publica totais e não diz quem recebeu.",
  nao_publica: "A despesa por deputado não é publicada.",
  nao_existe: "A casa não tem verba indenizatória.",
  fora_do_ar: "O portal estava fora do ar no dia do levantamento.",
  nao_verificado: "Não verificado: a consulta voltou vazia nos meses testados.",
  nao_identificado: "O levantamento não identificou o fornecedor do portal.",
  depois: "Vem depois, no mesmo modelo: a cota dos senadores.",
  outro: "Fora por outro motivo, descrito no levantamento.",
};

const BARRADA = new Set(["robots", "robots_cloudflare", "cloudflare", "anti_robo", "captcha"]);
const SEM_ADAPTADOR = new Set(["na_fila", "em_coleta", "sem_adaptador", "reserva", "depois"]);

export function classe(situacao: string, motivo: string | null | undefined): Classe {
  if (situacao === "coletada") return "coletada";
  if (situacao === "em_revisao") return "em_revisao";
  if (motivo && BARRADA.has(motivo)) return "barrada";
  if (motivo && SEM_ADAPTADOR.has(motivo)) return "sem_adaptador";
  if (motivo === "nao_identificado") return "nao_identificado";
  return "outra";
}

export const ROTULO_CLASSE: Record<Classe, string> = {
  coletada: "Coletada",
  em_revisao: "Em revisão",
  barrada: "Fora: o portal barra o robô",
  sem_adaptador: "Fora: em coleta, na fila ou sem adaptador",
  nao_identificado: "Fora: fornecedor não identificado",
  outra: "Fora: outro motivo",
};

/** Preenchimento de cada classe no mapa e na amostra da legenda (padrões definidos no SVG do mapa). */
export const PREENCHIMENTO: Record<Classe, string> = {
  coletada: "var(--color-manilha)",
  em_revisao: "url(#hachura-revisao)",
  barrada: "url(#hachura-barrada)",
  sem_adaptador: "var(--color-aco-2)",
  nao_identificado: "var(--color-gaveta-2)",
  outra: "var(--color-gaveta-3)",
};

export const ORDEM_CLASSE: Classe[] = ["coletada", "em_revisao", "sem_adaptador", "barrada", "outra", "nao_identificado"];

/** Uma linha da tabela de todas as casas (federal, assembleias e câmaras do PR, no mesmo formato). */
export type LinhaCobertura = {
  grupo: "federal" | "assembleia" | "camara";
  id: string;
  nome: string;
  onde: string;
  fornecedor: string | null;
  classe: Classe;
  situacao: string;
  motivo: string | null;
  detalhe: string | null;
  href: string | null;
  parlamentares?: number;
  linhas?: number;
};
