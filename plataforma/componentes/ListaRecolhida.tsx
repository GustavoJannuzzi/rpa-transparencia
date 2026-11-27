import type { ReactNode } from "react";

type Props = {
  /** o texto do botão que abre a lista, com a contagem ("Mostrar os 648 deputados federais") */
  rotulo: string;
  /** false: a lista sai aberta, sem o botão (lista curta) */
  recolhida?: boolean;
  className?: string;
  children: ReactNode;
};

/**
 * Lista longa que começa recolhida, num `<details>` nativo: sem JavaScript, o
 * navegador não desenha o que está fechado, e a busca da página (Ctrl+F) abre a
 * lista sozinha nos navegadores Chromium. Medido em /parlamentares/ (1.725 nomes,
 * Pixel 7 emulado, CPU 4x, 27/11/2026, só o HTML): aberta, 70 mil px de altura e
 * 3,2 s de bloqueio da linha principal; recolhida, 5,3 mil px e 1,1 s.
 */
export default function ListaRecolhida({ rotulo, recolhida = true, className = "", children }: Props) {
  const lista = <ul className={className}>{children}</ul>;
  if (!recolhida) return lista;
  return (
    <details className="lista-recolhida mt-3">
      <summary className="cursor-pointer text-sm text-tinta-2 underline decoration-tinta-3/50 underline-offset-2 hover:text-tinta">{rotulo}</summary>
      {lista}
    </details>
  );
}

/**
 * Abre a lista da casa que o endereço aponta (`/parlamentares/#casa-cm-maringa`),
 * na carga e quando o endereço muda. Vai no HTML como script em linha, depois das
 * listas, para não pôr um componente de cliente na página só por isso.
 */
export const ABRIR_LISTA_DO_ENDERECO = `(()=>{const abrir=()=>{const id=decodeURIComponent(location.hash.slice(1));const alvo=id&&document.getElementById(id);const lista=alvo&&alvo.querySelector("details.lista-recolhida");if(lista)lista.open=true};abrir();addEventListener("hashchange",abrir)})()`;
