import Link from "next/link";

export default function NaoAchado() {
  return (
    <div className="mx-auto max-w-[760px] px-4 py-16 sm:px-8">
      <h1 className="font-titulo text-[2.2rem] font-medium">Esta ficha não está na gaveta</h1>
      <p className="mt-3 text-tinta-2">O endereço não existe, ou o parlamentar não tem despesas publicadas.</p>
      <p className="mt-6">
        <Link href="/" className="text-carimbo-claro underline">
          Voltar ao grafo
        </Link>
      </p>
    </div>
  );
}
