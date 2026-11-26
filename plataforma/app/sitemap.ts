import type { MetadataRoute } from "next";
import { casas, dataDaColeta, indice, partidos } from "@/lib/dados";
import { SITE } from "@/lib/site";

export const dynamic = "force-static";

/** Todas as páginas do site, com a data da coleta mais recente como última mudança. */
export default function sitemap(): MetadataRoute.Sitemap {
  const quando = dataDaColeta();
  const fixas = ["/", "/partidos/", "/parlamentares/", "/cobertura/", "/como-os-dados-chegam-aqui/", "/sobre/"];
  return [
    ...fixas.map((c) => ({ url: `${SITE}${c}`, lastModified: quando })),
    ...partidos().map((p) => ({ url: `${SITE}/partidos/${p.slug}/`, lastModified: quando })),
    ...casas()
      .filter((c) => c.id !== "camara-deputados")
      .map((c) => ({ url: `${SITE}/casas/${c.id}/`, lastModified: quando })),
    ...indice().map((i) => ({ url: `${SITE}/parlamentares/${i.id}/`, lastModified: quando })),
  ];
}
