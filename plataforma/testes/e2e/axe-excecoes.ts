// Violações do axe já conhecidas e com conserto a caminho. Cada exceção vale só
// para a regra, o trecho de HTML e as telas listadas; qualquer outra violação
// reprova o teste.
//
// Quando o conserto entrar, apague a exceção: o teste também reprova se uma
// exceção não achar mais a violação que ela cobre, para nenhuma ficar esquecida.
//
// As duas primeiras vêm da auditoria de 26/11/2026 (itens A1 e A2) e saem com o
// conserto de acessibilidade da plataforma (contraste do carimbo sépia e a busca
// como combobox com aria-activedescendant). A terceira apareceu no primeiro
// teste no tamanho de celular e entra no mesmo conserto da busca.

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

export const EXCECOES: Excecao[] = [
  {
    regra: "color-contrast",
    html: /\bsepia\b/,
    telas: ["inicio", "inicio-em-lista", "inicio-busca-aberta"],
    motivo: "carimbo sépia (#7a6635) a 3,33:1 sobre a manilha; o conserto leva a cor para perto de #5f4f27 (4,5:1)",
  },
  {
    regra: "nested-interactive",
    html: /role="option"/,
    telas: ["inicio-busca-aberta"],
    motivo: "a busca põe um <button> dentro de role=option; o conserto troca por aria-activedescendant no campo",
  },
  {
    regra: "target-size",
    html: /role="tab"|Ver em lista/,
    telas: ["inicio-busca-aberta"],
    projetos: ["acessibilidade-celular"],
    motivo: "no celular, a lista da busca aberta cobre as abas Brasil/Paraná e o botão \"Ver em lista\" (20 px de altura), que ficam com menos de 24 px livres",
  },
];
