"use client";

import { useSyncExternalStore } from "react";

/** Liga um componente a uma media query. No servidor (e no primeiro render da
 * hidratação) vale `noServidor`, para o HTML estático ser sempre o mesmo. */
export function useMidia(consulta: string, noServidor = false): boolean {
  return useSyncExternalStore(
    (avisar) => {
      const m = window.matchMedia(consulta);
      m.addEventListener("change", avisar);
      return () => m.removeEventListener("change", avisar);
    },
    () => window.matchMedia(consulta).matches,
    () => noServidor,
  );
}

export { TELA_ESTREITA } from "./telas";
