import type { Metadata, Viewport } from "next";
import { Archivo, Libre_Franklin } from "next/font/google";
import Link from "next/link";
import Busca from "@/componentes/Busca";
import Navegacao from "@/componentes/Navegacao";
import { dataDaColeta } from "@/lib/dados";
import { data } from "@/lib/formato";
import { IMAGEM_OG, NOME, SITE } from "@/lib/site";
import "./globals.css";

const archivo = Archivo({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--fonte-archivo", display: "swap" });
const franklin = Libre_Franklin({ subsets: ["latin"], weight: ["400", "500"], variable: "--fonte-franklin", display: "swap" });

const DESCRICAO =
  "Plataforma independente que junta despesas de deputados federais, deputados estaduais e vereadores vindas de muitos sistemas diferentes, com a procedência de cada número.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: { default: "rpa-transparencia — despesas de parlamentares com procedência", template: "%s — rpa-transparencia" },
  description: DESCRICAO,
  alternates: { canonical: "/" },
  openGraph: {
    title: "Quem gastou com quem, e de onde vem cada número",
    description: DESCRICAO,
    url: "/",
    siteName: NOME,
    locale: "pt_BR",
    type: "website",
    images: [IMAGEM_OG],
  },
  twitter: { card: "summary_large_image", title: "Quem gastou com quem, e de onde vem cada número", description: DESCRICAO, images: [IMAGEM_OG.url] },
};

export const viewport: Viewport = { themeColor: "#1b2220", colorScheme: "dark" };

export default function Layout({ children }: { children: React.ReactNode }) {
  const coleta = dataDaColeta();
  return (
    <html lang="pt-BR" className={`${archivo.variable} ${franklin.variable}`}>
      <body className="flex min-h-dvh flex-col">
        <a href="#conteudo" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:bg-manilha focus:px-3 focus:py-2 focus:text-manilha-tinta">
          Pular para o conteúdo
        </a>
        <header className="border-b border-aco">
          <div className="mx-auto flex max-w-[1600px] flex-col gap-3 px-4 py-3 sm:px-8 lg:h-16 lg:flex-row lg:items-center lg:gap-10 lg:py-0">
            <Link href="/" className="font-titulo text-[1.3rem] font-semibold tracking-[-0.01em] text-tinta">
              rpa-transparencia
            </Link>
            <Navegacao />
            <div className="lg:ml-auto">
              <Busca />
            </div>
          </div>
        </header>
        <main id="conteudo" className="flex-1">
          {children}
        </main>
        {/* descrição única dos valores clicáveis (aria-describedby), em vez de repetir o texto em cada número */}
        <span id="dica-ficha" hidden>
          Abre a ficha de procedência: fonte, data da coleta e documento oficial.
        </span>
        <footer className="border-t border-aco">
          <div className="mx-auto flex max-w-[1600px] flex-col gap-2 px-4 py-6 text-sm text-tinta-3 sm:flex-row sm:justify-between sm:px-8">
            <p>
              Plataforma independente, sem vínculo com nenhuma das casas legislativas, prefeituras ou tribunais citados. Dados
              públicos coletados em <span className="num">{data(coleta)}</span>.
            </p>
            <p>
              <Link href="/sobre/" className="underline hover:text-tinta">
                Sobre e regras
              </Link>
              {" · "}
              <a href="/conferencia/" className="underline hover:text-tinta">
                Relatório de conferência
              </a>
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
