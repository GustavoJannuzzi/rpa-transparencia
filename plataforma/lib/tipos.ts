export type Filiacao = { partido: string; desde: string | null; ate: string | null; base: string; fonte: string };

export type Gabinete = {
  fonte: string;
  rotulo: string;
  competencia: string;
  data_referencia: string;
  pessoas: number;
  custo: string;
  k: string;
  src: string;
  lotacao: string;
};

export type Parlamentar = {
  id: string;
  nome: string;
  nome_civil: string | null;
  casa: "camara-deputados" | "cmc";
  uf: string | null;
  municipio: string | null;
  partido: string | null;
  filiacoes: Filiacao[];
  anos: number[];
  fontes: string[];
  total: string;
  linhas: number;
  por_categoria: Record<string, string>;
  por_ano: Record<string, string>;
  procedencia_ano: Record<string, { fontes: string[]; linhas: number }>;
  procedencia_categoria: Record<string, { fontes: string[]; linhas: number }>;
  gabinete: Gabinete[];
  mandatos: number[];
  id_camara: string | null;
  top_fornecedores: { doc: string; nome: string | null; linhas: number }[];
  p: { coleta: Record<string, string> };
};

export type ItemIndice = {
  id: string;
  nome: string;
  casa: "camara-deputados" | "cmc";
  uf: string | null;
  partido: string | null;
  total: string;
  linhas: number;
  gabinete: boolean;
};

export type Partido = {
  sigla: string;
  membros: { id: string; nome: string; casa: string; uf: string | null; total: string }[];
  por_categoria: Record<string, string>;
  por_mes: Record<string, string>;
  total: string;
  fontes: string[];
  coleta: Record<string, string>;
  procedencia_mes: Record<string, { fontes: string[]; linhas: number }>;
  procedencia_categoria: Record<string, { fontes: string[]; linhas: number }>;
  regra: string;
};

export type ItemPartido = { sigla: string; slug: string; federal: number; municipal: number; total: string };

export type Conferencia = {
  verificacao: string;
  escopo: string;
  esperado: string | null;
  obtido: string | null;
  resultado: string;
  detalhe: string | null;
};

export type TotalOficial = {
  escopo: string;
  metrica: string;
  valor: string;
  texto_original: string | null;
  url: string | null;
  coletado_em: string | null;
};

export type Fonte = {
  id: string;
  sistema: string;
  fornecedor: string;
  modo: "api" | "arquivo" | "robo" | "robo_pdf";
  casa: string;
  cobre_de: number;
  cobre_ate: number;
  endereco: string;
  o_que_tem: string;
  ultima_coleta: { inicio: string; fim: string; situacao: string; totais: string } | null;
  inventario: Record<string, number>;
  situacoes: Record<string, number>;
  pendencias_de_leitura: number;
  totais_oficiais: TotalOficial[];
  conferencias: Conferencia[];
};

export type Fontes = {
  gerado_em: string;
  versao_robo: string;
  fontes: Fonte[];
  cobertura_curitiba: { de: number; ate: number; fonte: string | null; rotulo: string; detalhe?: string }[];
  diarias_camara_curitiba: { ano: number; vereadores: string; servidores: string; linhas: number }[];
};

export type Revisao = {
  grupos: { fonte: string; tipo: string; motivo: string; n: number; exemplos: { chave: string; detalhe: Record<string, unknown> }[] }[];
  linhas_em_revisao_por_fonte: Record<string, number>;
  gerado_em: string;
};

export type ArquivoAno = {
  colunas: string[];
  prefixos_documento: string[];
  categorias: (string | null)[];
  fornecedores: [string | null, string][];
  coletas: { fonte: string; coletado_em: string }[];
  linhas: [string, number, number, string, string | null, number, InfoLinha | null][];
};

export type InfoLinha = {
  s?: string;
  o?: string;
  f?: string;
  loc?: string;
  src?: string;
  k?: string;
  x?: string;
  hosp?: string;
  tran?: string;
  devo?: string;
};

/** Procedência de um número na tela. Sem isto, o número não aparece. */
export type Procedencia = {
  fontes: string[];
  coleta: string;
  documento?: string | null;
  local?: string | null;
  situacao?: "conferido" | "fora_da_soma" | "soma";
  nota?: string | null;
  linhas?: number;
};
