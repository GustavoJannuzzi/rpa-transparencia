import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Ficha não encontrada", robots: { index: false } };

export default function NaoAchado() {
  return (
    <div className="mx-auto max-w-[760px] px-4 py-16 sm:px-8">
      <h1 className="font-titulo text-[2.2rem] font-medium">Esta ficha não está na gaveta</h1>
      <p className="mt-3 text-tinta-2">
        O endereço não existe. Todo parlamentar do índice tem página, mesmo quem não tem despesa conferida.
      </p>
      <p className="mt-6 flex flex-wrap gap-x-6 gap-y-2">
        <Link href="/" className="text-carimbo-claro underline">
          Voltar ao grafo
        </Link>
        <Link href="/parlamentares/" className="text-carimbo-claro underline">
          Ver a lista de parlamentares
        </Link>
      </p>
    </div>
  );
}
