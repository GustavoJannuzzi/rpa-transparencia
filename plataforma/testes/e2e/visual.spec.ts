// Regressão visual: cada tela de estados.ts comparada com a imagem de referência,
// no desktop (1366 px) e no celular (Pixel 7). O desenho do grafo (canvas) fica
// mascarado; a casca em volta dele é comparada.
//
// As referências são geradas no runner Linux do GitHub Actions, pelo workflow
// "Atualizar prints de referência". Gerar no Windows ou no macOS não serve: a
// renderização de fonte muda e todo print reprovaria. Ver docs/ci.md.
import { existsSync, readdirSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { ESTADOS, abrir } from "./estados";

const PRINTS = path.join(__dirname, "prints");

test.skip(process.platform !== "linux", "as referências são do runner Linux do CI");

test.beforeEach(({}, info) => {
  // Antes da primeira rodada do workflow de prints não há referência nenhuma para
  // este projeto: o teste é pulado com o aviso, em vez de reprovar tudo. Faltando
  // só algumas, ele reprova normalmente.
  const referencias = existsSync(PRINTS) ? readdirSync(PRINTS).filter((f) => f.endsWith(`-${info.project.name}-linux.png`)) : [];
  test.skip(
    referencias.length === 0 && info.config.updateSnapshots === "none",
    "ainda sem prints de referência: rode o workflow \"Atualizar prints de referência\"",
  );
});

for (const estado of ESTADOS.filter((e) => !e.soAxe)) {
  test(`print: ${estado.nome}`, async ({ page }) => {
    await abrir(page, estado);
    await page.mouse.move(0, 0);
    await expect(page).toHaveScreenshot(`${estado.nome}.png`, {
      mask: estado.temGrafo ? [page.locator("canvas")] : [],
      timeout: 15_000,
    });
  });
}
