// As telas que os testes de navegador visitam: uma de cada tipo de página do
// export, mais os estados que só existem depois de um clique (a lista do grafo,
// a busca aberta, a ficha de procedência). O axe e os prints usam a mesma lista.
import { expect, type Page } from "@playwright/test";

export type Estado = {
  nome: string;
  rota: string;
  /** deixa a tela no estado que se quer medir (depois do carregamento) */
  preparar?: (page: Page) => Promise<void>;
  /** o grafo é <canvas>: o print esconde o desenho e compara só a casca */
  temGrafo?: boolean;
  /** só o axe (o print desta tela não diz nada a mais que outro) */
  soAxe?: boolean;
};

async function grafoPronto(page: Page) {
  await expect(page.getByText("Abrindo o grafo…")).toHaveCount(0, { timeout: 30_000 });
}

export const ESTADOS: Estado[] = [
  { nome: "inicio", rota: "/", temGrafo: true, preparar: grafoPronto },
  {
    nome: "inicio-em-lista",
    rota: "/",
    preparar: async (page) => {
      await grafoPronto(page);
      await page.getByRole("button", { name: "Ver em lista" }).click();
      await expect(page.getByRole("button", { name: "Voltar ao grafo" })).toBeVisible();
    },
  },
  {
    nome: "inicio-busca-aberta",
    rota: "/",
    soAxe: true,
    preparar: async (page) => {
      await grafoPronto(page);
      await page.getByRole("combobox").fill("car");
      await expect(page.getByRole("option").first()).toBeVisible();
    },
  },
  { nome: "partidos", rota: "/partidos/" },
  { nome: "partido-pt", rota: "/partidos/pt/" },
  { nome: "parlamentares", rota: "/parlamentares/" },
  { nome: "deputada", rota: "/parlamentares/dep-220704/" },
  {
    nome: "deputada-ficha-aberta",
    rota: "/parlamentares/dep-220704/",
    preparar: async (page) => {
      const valor = page.locator("button.valor").first();
      await valor.click();
      await expect(page.getByRole("dialog", { name: "Ficha de procedência" }).first()).toBeVisible();
    },
  },
  { nome: "vereador", rota: "/parlamentares/ver-cwb-pedro-paulo-costa/" },
  { nome: "vereador-com-gabinete", rota: "/parlamentares/ver-cwb-alexandre-leprevost/", soAxe: true },
  { nome: "como-os-dados-chegam-aqui", rota: "/como-os-dados-chegam-aqui/" },
  { nome: "sobre", rota: "/sobre/" },
  { nome: "pagina-nao-encontrada", rota: "/nao-existe/" },
];

export async function abrir(page: Page, estado: Estado) {
  const resposta = await page.goto(estado.rota, { waitUntil: "load" });
  expect(resposta?.status(), `status de ${estado.rota}`).toBe(estado.nome === "pagina-nao-encontrada" ? 404 : 200);
  await page.evaluate(() => document.fonts.ready);
  if (estado.preparar) await estado.preparar(page);
}
