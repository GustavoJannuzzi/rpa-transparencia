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
  /** ex.: "uma fonte só" (a Câmara não tem um segundo sistema de pessoal para conferir) */
  nota?: string;
};

/** Subsídio: o que o cadastro de pessoal da casa diz que o parlamentar recebe, numa data. */
export type Subsidio = {
  fonte: string;
  rotulo: string;
  valor: string;
  competencia: string;
  data_referencia: string;
  k: string;
  src: string;
  loc: string | null;
  cargo: string | null;
};

export type Parlamentar = {
  id: string;
  nome: string;
  nome_civil: string | null;
  /** id da casa: "camara-deputados", "cmc" (Curitiba), "cm-<município>", "al-<uf>" */
  casa: string;
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
  /** Só vereador: anos do mandato em que a fonte diz não ter diária nenhuma (não é zero: é não publicar). */
  anos_sem_publicacao?: number[];
  /** "agregado": a fonte publica a despesa já somada (por fornecedor, tipo e mês), não nota a nota. */
  granularidade?: "nota" | "agregado" | "misto";
  subsidio?: Subsidio[];
};

export type GrupoRevisao = { fonte: string; motivo: string; categoria: string; anos: number[]; linhas: number };

export type ItemIndice = {
  id: string;
  nome: string;
  casa: string;
  uf: string | null;
  municipio?: string;
  partido: string | null;
  total: string;
  linhas: number;
  gabinete: boolean;
};

export type Partido = {
  sigla: string;
  membros: { id: string; nome: string; casa: string; uf: string | null; municipio?: string; total: string }[];
  por_categoria: Record<string, string>;
  por_mes: Record<string, string>;
  total: string;
  fontes: string[];
  coleta: Record<string, string>;
  procedencia_mes: Record<string, { fontes: string[]; linhas: number }>;
  procedencia_categoria: Record<string, { fontes: string[]; linhas: number }>;
  regra: string;
};

export type ItemPartido = { sigla: string; slug: string; federal: number; estadual?: number; municipal: number; total: string };

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
  /** `src`: a página ou o arquivo de onde as linhas desta coleta saíram */
  coletas: { fonte: string; coletado_em: string; src?: string }[];
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
  /** "agregado": a linha é uma soma feita pela fonte, não uma nota */
  g?: string;
};

export type SistemaDaCasa = { fonte: string; sistema: string; fornecedor: string; modo: string; de: number; ate: number; endereco: string };

export type TipoCasa = "camara_federal" | "senado" | "assembleia" | "camara_municipal";

export type ResumoCasa = {
  id: string;
  nome: string;
  tipo: TipoCasa;
  esfera: "federal" | "estadual" | "municipal";
  uf: string;
  municipio: string | null;
  ibge: number | null;
  cargo: string;
  de: number;
  ate: number;
  sistemas: SistemaDaCasa[];
  parlamentares: number;
  com_despesa: number;
  linhas: number;
  total: string;
  em_revisao: number;
  situacao: "coletada" | "em_revisao";
  p: { fontes: string[]; coleta: string };
};

export type Casa = ResumoCasa & {
  por_ano: {
    ano: number;
    total: string | null;
    vereadores?: string | null;
    servidores?: string | null;
    linhas?: number;
    linhas_vereadores?: number;
    fonte_nao_publica?: boolean;
  }[];
  por_categoria: Record<string, string>;
  membros: { id: string; nome: string; partido: string | null; total: string; linhas: number }[];
  fornecedores_comuns: { doc: string; nome: string | null; parlamentares: number }[];
  subsidio: { min: string; max: string; pessoas: number; datas: string[]; fontes: string[] } | null;
  conferencia: { fonte: string; esperado?: string; obtido?: string; resultado?: string; detalhe?: string; erros?: string | null }[];
  outras_conferencias: (Conferencia & { fonte: string })[];
  em_revisao_por_motivo: { fonte: string; motivo: string; linhas: number }[];
};

export type SituacaoCobertura = "coletada" | "em_revisao" | "fora";

export type CamaraCobertura = {
  ibge: number;
  municipio: string;
  fornecedor: string | null;
  portal: string | null;
  situacao: SituacaoCobertura;
  motivo: string | null;
  base: string | null;
  /** Câmara configurada que ficou de fora: o que a coleta achou no portal dela. */
  detalhe?: string;
  casa?: string;
  parlamentares?: number;
  linhas?: number;
};

export type AssembleiaCobertura = {
  uf: string;
  sigla: string;
  nome: string;
  cadeiras: number;
  sistema: string;
  situacao: SituacaoCobertura;
  motivo: string | null;
  detalhe: string | null;
  casa?: string;
  parlamentares?: number;
  linhas?: number;
};

export type Cobertura = {
  levantamento: {
    data: string;
    camaras_pr: {
      total: number;
      com_fornecedor_dos_quatro_adaptadores: number;
      por_fornecedor: Record<string, number>;
      sem_fornecedor_identificado: number;
      robots_proibe_tudo: number;
    };
    camaras_com_fornecedor_nomeado: number;
  };
  medidas: { camaras_coletadas: number; assembleias_coletadas: number; parlamentares: number; linhas: number; sistemas: string[] };
  camaras_pr: CamaraCobertura[];
  assembleias: AssembleiaCobertura[];
  federal: { id: string; nome: string; situacao: SituacaoCobertura; motivo?: string; parlamentares?: number; linhas?: number }[];
};

export type Mapa = { viewBox: string; areas: { id: number | string; d: string }[]; fonte: string; baixado_em: string };

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
