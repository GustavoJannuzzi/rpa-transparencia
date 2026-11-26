import type { Metadata } from "next";

/** Endereço público do site. Na Vercel, o domínio de produção estável (nunca o
 * domínio efêmero de cada deploy, que pode pedir login e quebrar o cartão do link
 * compartilhado). Variável vazia conta como ausente. */
export const SITE = process.env.VERCEL_PROJECT_PRODUCTION_URL
  ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`
  : "https://rpa-transparencia.vercel.app";

export const NOME = "rpa-transparencia";

/** Uma imagem só para o link compartilhado, no visual da gaveta. */
export const IMAGEM_OG = { url: "/og.png", width: 1200, height: 630, alt: "Uma ficha manilha com o carimbo CONFERIDO sobre a gaveta grafite" };

/** Título, descrição, endereço canônico e cartão de link compartilhado de uma página. */
export function metadadosDaPagina({ title, description, caminho }: { title: string; description: string; caminho: string }): Metadata {
  return {
    title,
    description,
    alternates: { canonical: caminho },
    openGraph: { title, description, url: caminho, siteName: NOME, locale: "pt_BR", type: "website", images: [IMAGEM_OG] },
    twitter: { card: "summary_large_image", title, description, images: [IMAGEM_OG.url] },
  };
}
