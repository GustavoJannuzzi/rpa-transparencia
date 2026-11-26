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
  /** O que ficou fora dos totais desta pessoa, por categoria e motivo. */
  em_revisao: GrupoRevisao[];
  /** Só vereador: anos de mandato que as fontes cobrem. */
  anos_mandato?: number[];
  /** Só vereador: anos inteiros de uma fonte em revisão, dentro do mandato. */
  periodos_em_revisao?: { fonte: string; anos: number[]; motivo: string }[];
};

export type GrupoRevisao = { fonte: string; motivo: string; categoria: string; anos: number[]; linhas: number };

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
  cobertura_curitiba: { de: number; ate: number; fonte: string | null; rotulo: string; detalhe?: string; detalhe_tecnico?: string }[];
  /** vereadores e servidores vêm nulos no ano que está inteiro em revisão */
  diarias_camara_curitiba: { ano: number; vereadores: string | null; servidores: string | null; linhas: number; em_revisao: number }[];
};

export type GrupoFila = {
  fonte: string;
  tipo: string;
  motivo: string;
  /** itens na fila (uma linha, ou um recorte inteiro como uma categoria num ano) */
  n: number;
  /** linhas de despesa que este motivo tira dos totais; cada linha conta num motivo só */
  linhas: number;
  exemplos: { chave: string; detalhe: Record<string, unknown> }[];
};

export type Revisao = {
  grupos: GrupoFila[];
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
