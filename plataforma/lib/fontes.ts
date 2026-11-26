/** Nomes das fontes como o visitante lê, e como cada uma é coletada. */
export const FONTES: Record<string, { nome: string; curto: string; como: string }> = {
  camara_deputados: { nome: "Câmara dos Deputados — API e arquivo anual da cota", curto: "Câmara dos Deputados", como: "API + arquivo anual" },
  cmc_legado: { nome: "Câmara de Curitiba — portal legado (PDF)", curto: "Legado de Curitiba", como: "robô + PDF" },
  cmc_elotech: { nome: "Câmara de Curitiba — Elotech", curto: "Elotech", como: "API" },
  cmc_prefeitura: { nome: "Câmara de Curitiba — portal da Prefeitura", curto: "Portal da Prefeitura", como: "robô de navegador" },
  cmc_betha: { nome: "Câmara de Curitiba — Betha", curto: "Betha", como: "robô de navegador" },
  tse: { nome: "TSE — dados abertos de candidaturas", curto: "TSE", como: "arquivo" },
};

export function nomeFonte(id: string): string {
  return FONTES[id]?.nome ?? id;
}

export function comoFonte(id: string): string {
  return FONTES[id]?.como ?? "";
}

export const MODO: Record<string, string> = {
  api: "API",
  arquivo: "arquivo",
  robo: "robô de navegador",
  robo_pdf: "robô + PDF",
};
