"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITENS = [
  { href: "/", rotulo: "Grafo" },
  { href: "/partidos/", rotulo: "Partidos" },
  { href: "/parlamentares/", rotulo: "Parlamentares" },
  { href: "/cobertura/", rotulo: "Cobertura" },
  { href: "/como-os-dados-chegam-aqui/", rotulo: "Como os dados chegam aqui" },
  { href: "/sobre/", rotulo: "Sobre" },
];

export default function Navegacao() {
  const atual = usePathname() || "/";
  return (
    <nav aria-label="Principal" className="-mx-1 flex flex-wrap gap-x-3 gap-y-1 text-[0.95rem] sm:gap-5">
      {ITENS.map((i) => {
        const ativo = i.href === "/" ? atual === "/" : atual.startsWith(i.href);
        return (
          <Link
            key={i.href}
            href={i.href}
            aria-current={ativo ? "page" : undefined}
            className={`shrink-0 whitespace-nowrap px-1 py-1 ${ativo ? "text-tinta shadow-[inset_0_-2px_0_var(--color-carimbo)]" : "text-tinta-2 hover:text-tinta"}`}
          >
            {i.rotulo}
          </Link>
        );
      })}
    </nav>
  );
}
