/** Nomes das fontes como o visitante lê, e como cada uma é coletada. */
export const FONTES: Record<string, { nome: string; curto: string; como: string }> = {
  camara_deputados: { nome: "Câmara dos Deputados — API e arquivo anual da cota", curto: "Câmara dos Deputados", como: "API + arquivo anual" },
  cmc_legado: { nome: "Câmara de Curitiba — portal legado (PDF)", curto: "Legado de Curitiba", como: "robô + PDF" },
  cmc_elotech: { nome: "Câmara de Curitiba — Elotech", curto: "Elotech", como: "API" },
  cmc_prefeitura: { nome: "Câmara de Curitiba — portal da Prefeitura", curto: "Portal da Prefeitura", como: "robô de navegador" },
  cmc_betha: { nome: "Câmara de Curitiba — Betha", curto: "Betha", como: "robô de navegador" },
  tse: { nome: "TSE — dados abertos de candidaturas", curto: "TSE", como: "arquivo" },
  // câmaras e assembleias de coleta/entidades.toml (um adaptador por fornecedor, configurado por entidade)
  elotech_maringa: { nome: "Câmara de Maringá — Elotech", curto: "Elotech (Maringá)", como: "API" },
  elotech_ponta_grossa: { nome: "Câmara de Ponta Grossa — Elotech", curto: "Elotech (Ponta Grossa)", como: "API" },
  elotech_foz_do_iguacu: { nome: "Câmara de Foz do Iguaçu — Elotech", curto: "Elotech (Foz do Iguaçu)", como: "API" },
  elotech_sarandi: { nome: "Câmara de Sarandi — Elotech", curto: "Elotech (Sarandi)", como: "API" },
  elotech_umuarama: { nome: "Câmara de Umuarama — Elotech", curto: "Elotech (Umuarama)", como: "API" },
  elotech_cianorte: { nome: "Câmara de Cianorte — Elotech", curto: "Elotech (Cianorte)", como: "API" },
  elotech_irati: { nome: "Câmara de Irati — Elotech", curto: "Elotech (Irati)", como: "API" },
  elotech_campina_grande_do_sul: { nome: "Câmara de Campina Grande do Sul — Elotech", curto: "Elotech (Campina Grande do Sul)", como: "API" },
  elotech_pitanga: { nome: "Câmara de Pitanga — Elotech", curto: "Elotech (Pitanga)", como: "API" },
  elotech_ubirata: { nome: "Câmara de Ubiratã — Elotech", curto: "Elotech (Ubiratã)", como: "API" },
  elotech_cambara: { nome: "Câmara de Cambará — Elotech", curto: "Elotech (Cambará)", como: "API" },
  elotech_renascenca: { nome: "Câmara de Renascença — Elotech", curto: "Elotech (Renascença)", como: "API" },
  cldf: { nome: "Câmara Legislativa do DF — dados abertos (CSV e planilha)", curto: "CLDF", como: "arquivo" },
  almg: { nome: "Assembleia de Minas Gerais — API de dados abertos", curto: "ALMG", como: "API" },
  alesp: { nome: "Assembleia de São Paulo — dados abertos (arquivo JSON)", curto: "ALESP", como: "arquivo" },
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
