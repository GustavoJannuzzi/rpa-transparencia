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
      // a inicial tem duas buscas (a do topo e a de dentro do grafo): esta é a do topo
      await page.getByRole("combobox", { name: "Buscar deputado ou vereador" }).fill("car");
      await expect(page.getByRole("option").first()).toBeVisible();
    },
  },
  {
    // o estado vem da URL: vista, ponto escolhido e a ficha dele aberta
    nome: "inicio-ponto-no-grafo",
    rota: "/?vista=brasil&no=dep-220704",
    soAxe: true,
    preparar: async (page) => {
      await grafoPronto(page);
      await expect(page.getByRole("heading", { name: "Carol Dartora" })).toBeVisible();
    },
  },
  {
    nome: "inicio-busca-do-grafo",
    rota: "/",
    soAxe: true,
    preparar: async (page) => {
      await grafoPronto(page);
      await page.getByRole("combobox", { name: "Achar alguém no grafo" }).fill("dartora");
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
  // atividade nas sessões: o SAPL (Sarandi) e o relatório de frequência de Curitiba, com a ficha de uma contagem aberta
  { nome: "vereador-nas-sessoes", rota: "/parlamentares/ver-sarandi-aparecido-biancho/" },
  {
    nome: "vereador-frequencia-ficha-aberta",
    rota: "/parlamentares/ver-cwb-alexandre-leprevost/",
    soAxe: true,
    preparar: async (page) => {
      await page.locator("#nas-sessoes ~ div button.valor").first().click();
      await expect(page.getByRole("dialog", { name: "Ficha de procedência" }).first()).toBeVisible();
    },
  },
  { nome: "casa-camara-curitiba", rota: "/casas/cmc/", soAxe: true },
  { nome: "como-os-dados-chegam-aqui", rota: "/como-os-dados-chegam-aqui/" },
  // as casas novas: a vitrine dos vários sistemas, uma câmara do Elotech e uma assembleia de arquivo agregado
  { nome: "cobertura", rota: "/cobertura/" },
  { nome: "casa-camara", rota: "/casas/cm-maringa/" },
  { nome: "casa-assembleia", rota: "/casas/al-sp/", soAxe: true },
  { nome: "deputado-estadual", rota: "/parlamentares/est-mg-12193/", soAxe: true },
  { nome: "sobre", rota: "/sobre/" },
  { nome: "pagina-nao-encontrada", rota: "/nao-existe/" },
];

export async function abrir(page: Page, estado: Estado) {
  const resposta = await page.goto(estado.rota, { waitUntil: "load" });
  expect(resposta?.status(), `status de ${estado.rota}`).toBe(estado.nome === "pagina-nao-encontrada" ? 404 : 200);
  await page.evaluate(() => document.fonts.ready);
  if (estado.preparar) await estado.preparar(page);
  // o axe e o print medem a tela parada: espera as animações de entrada (a ficha que
  // sobe, o carimbo que bate), senão o axe pega a cor no meio do fade e acusa contraste
  await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== "running"), null, { timeout: 5_000 });
}
