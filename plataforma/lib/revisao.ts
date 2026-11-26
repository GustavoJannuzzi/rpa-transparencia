import type { GrupoFila } from "./tipos";

/** Por que um recorte de despesas ficou fora da soma, primeiro em português de leigo.
 * As chaves vêm do `publicar` (campo `motivo` de `em_revisao`). */
export const MOTIVO_LEIGO: Record<string, string> = {
  api_x_arquivo:
    "A Câmara publica essa categoria de um jeito na API e de outro no arquivo do ano. Até a diferença ser explicada, a categoria inteira daquele ano fica fora da soma.",
  consulta_prefeitura:
    "O portal da Prefeitura devolve listas diferentes para o mesmo ano, conforme a consulta, e não publica um total para desempatar.",
  sinal_negativo:
    "Valor negativo que a Câmara não explica: o documento vale mais que zero, mas o valor descontado vem com sinal de menos.",
  identidade: "A despesa não tem parlamentar identificado com certeza.",
  cancelada: "Diária cancelada ou devolvida, e o relatório do ano não tem total para confirmar se ela entra na soma.",
  conta_da_linha: "A conta da própria linha não fecha com os valores que ela traz.",
  outro: "O robô não leu a linha com certeza.",
};

/** A frase de leigo para um motivo da fila de revisão. O texto do robô fica no detalhe técnico. */
export function motivoDaFila(g: Pick<GrupoFila, "tipo" | "motivo">): string {
  const m = g.motivo;
  if (g.tipo === "api_x_arquivo") {
    const ano = /em (\d{4})/.exec(m)?.[1];
    const cat = /^'([^']+)'/.exec(m)?.[1];
    return cat ? `${categoriaLegivel(cat)}${ano ? ` em ${ano}` : ""}: ${minuscula(MOTIVO_LEIGO.api_x_arquivo)}` : MOTIVO_LEIGO.api_x_arquivo;
  }
  if (g.tipo === "consulta") {
    const ano = /^(\d{4})/.exec(m)?.[1];
    return ano ? `Diárias de ${ano}: ${minuscula(MOTIVO_LEIGO.consulta_prefeitura)}` : MOTIVO_LEIGO.consulta_prefeitura;
  }
  if (g.tipo === "identidade") {
    if (m.includes("fora da lista")) return "Deputado que aparece nas despesas, mas não na lista oficial da legislatura.";
    if (m.includes("matrículas")) return "Nomes diferentes ligados à mesma pessoa pelas matrículas da Câmara.";
    if (m.includes("sem nome")) return "Parlamentar sem nome em nenhuma das fontes.";
    if (m.includes("gabinete sem")) return "Gabinete sem vereador identificado.";
  }
  if (g.tipo === "partido") {
    if (m.includes("não encontrado")) return "O nome do vereador não aparece entre os candidatos daquela eleição no TSE; o partido fica em revisão.";
    if (m.includes("partidos diferentes")) return "O nome casa com candidatos de partidos diferentes na mesma eleição.";
    if (m.includes("indefinido")) return "Partido atual indefinido: o deputado não tem despesa e aparece com mais de um partido.";
  }
  if (g.tipo === "gabinete") {
    if (m.includes("só um")) return "O gabinete aparece em só um dos dois sistemas de pessoal da Câmara.";
    return `Os dois sistemas de pessoal da Câmara contam um número diferente de pessoas no gabinete (${m}).`;
  }
  if (g.tipo === "fronteira") {
    if (m.includes("sem par")) return "Diária de 2026 que aparece no portal da Prefeitura e não no Betha.";
    return "Diária de 2026 com valor diferente no Betha e no portal da Prefeitura.";
  }
  if (g.tipo === "total") return "O total do mês no relatório em PDF não fecha com a soma das linhas daquele mês.";
  if (g.tipo === "leitura") return "Linha da origem que o robô não conseguiu ler com certeza.";
  if (m.includes("guarda de privacidade"))
    return "O cargo veio escrito de um jeito que o robô não reconhece como vereador; por segurança, o nome foi descartado e a linha ficou de fora.";
  if (m.includes("sem identidade")) return "Despesa sem deputado identificado: ele não está na lista oficial da legislatura.";
  if (m.includes("valor líquido negativo")) return MOTIVO_LEIGO.sinal_negativo;
  if (m.includes("cancelada ou devolvida")) return MOTIVO_LEIGO.cancelada;
  if (m.includes("quantidade × unitário ≠ total")) return "A conta da linha não fecha (quantidade vezes valor unitário dá outro total), embora o total do mês confira.";
  if (m.includes("não verificável")) return "Não dá para conferir a conta da linha, e o relatório do ano não tem total.";
  if (m.includes("empenhado")) return "A conta da linha não fecha: o valor reservado menos o cancelado não dá o valor da diária.";
  if (m.includes("cancelada na fonte")) return "Cancelada na fonte, mas o valor cancelado não é igual ao reservado.";
  if (m.includes("outro ano")) return "Linha de outro ano dentro do arquivo anual.";
  if (m.includes("de-para")) return "Categoria ou cargo novo, que ainda não tem tradução para as categorias da plataforma.";
  return sentenca(m);
}

function minuscula(s: string): string {
  return s.charAt(0).toLowerCase() + s.slice(1);
}

/** "PASSAGEM AÉREA - SIGEPA" → "Passagem aérea (SIGEPA)": a sigla da origem fica como veio. */
function categoriaLegivel(original: string): string {
  const [base, sufixo] = original.replace(/\.$/, "").split(" - ");
  const b = sentenca(base);
  if (!sufixo) return b;
  return `${b} (${sufixo.length <= 6 && !sufixo.includes(" ") ? sufixo : sufixo.charAt(0) + sufixo.slice(1).toLowerCase()})`;
}

function sentenca(s: string): string {
  const limpo = s.trim().replace(/\.$/, "");
  return limpo === limpo.toUpperCase() ? limpo[0] + limpo.slice(1).toLowerCase() : limpo[0].toUpperCase() + limpo.slice(1);
}
