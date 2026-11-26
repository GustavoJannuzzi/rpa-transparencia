// Violações do axe já conhecidas e com conserto a caminho. Cada exceção vale só
// para a regra, o trecho de HTML e as telas listadas; qualquer outra violação
// reprova o teste.
//
// Quando o conserto entrar, apague a exceção: o teste também reprova se uma
// exceção não achar mais a violação que ela cobre, para nenhuma ficar esquecida.
//
// Hoje a lista está vazia. As três primeiras (contraste do carimbo sépia, botão
// dentro de role=option na busca e, no celular, a busca aberta cobrindo as abas)
// saíram com o conserto de acessibilidade da plataforma (PR #2).
//
// Exemplo de entrada:
//   {
//     regra: "color-contrast",
//     html: /\bsepia\b/,
//     telas: ["inicio"],
//     projetos: ["acessibilidade-celular"], // opcional
//     motivo: "o que falha e qual conserto vai tirar a exceção",
//   },

export type Excecao = {
  regra: string;
  /** casa com o HTML do nó que o axe acusou */
  html: RegExp;
  /** nome das telas (testes/e2e/estados.ts) em que a violação aparece hoje */
  telas: string[];
  /** só nestes projetos do playwright.config.ts (sem o campo: em todos) */
  projetos?: string[];
  motivo: string;
};

export const EXCECOES: Excecao[] = [];
