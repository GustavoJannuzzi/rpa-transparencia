// Testes de navegador contra o site exportado (out/), servido como na Vercel por
// testes/servidor.mjs. Rode `npm run build` antes.
// - acessibilidade: axe-core em cada tipo de página, no desktop e no celular;
// - visual: toHaveScreenshot. As imagens de referência são do runner Linux do
//   GitHub Actions; fora do Linux esses testes são pulados (ver docs/ci.md).
import { defineConfig, devices } from "@playwright/test";

const PORTA = 3107;
const CI = !!process.env.CI;

export default defineConfig({
  testDir: "testes/e2e",
  outputDir: "testes/resultados",
  snapshotPathTemplate: "{testDir}/prints/{arg}-{projectName}-{platform}{ext}",
  fullyParallel: true,
  forbidOnly: CI,
  retries: CI ? 1 : 0,
  // no CI, print sem referência reprova (nunca grava sozinho); quem grava é o
  // workflow de prints, com --update-snapshots=changed
  updateSnapshots: CI ? "none" : "missing",
  workers: CI ? 2 : undefined,
  reporter: CI ? [["list"], ["html", { open: "never", outputFolder: "testes/relatorio-playwright" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORTA}`,
    locale: "pt-BR",
    timezoneId: "America/Sao_Paulo",
    trace: "retain-on-failure",
  },
  expect: {
    toHaveScreenshot: { animations: "disabled", caret: "hide", scale: "css", maxDiffPixelRatio: 0.002 },
  },
  webServer: {
    command: "node testes/servidor.mjs",
    url: `http://127.0.0.1:${PORTA}/`,
    env: { PORTA: String(PORTA) },
    reuseExistingServer: !CI,
  },
  projects: [
    { name: "acessibilidade-desktop", testMatch: /acessibilidade\.spec\.ts/, use: { ...devices["Desktop Chrome"], viewport: { width: 1366, height: 900 } } },
    { name: "acessibilidade-celular", testMatch: /acessibilidade\.spec\.ts/, use: { ...devices["Pixel 7"] } },
    { name: "visual-desktop", testMatch: /visual\.spec\.ts/, use: { ...devices["Desktop Chrome"], viewport: { width: 1366, height: 900 } } },
    { name: "visual-celular", testMatch: /visual\.spec\.ts/, use: { ...devices["Pixel 7"] } },
  ],
});
