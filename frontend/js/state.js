/**
 * Estado simple con suscripción.
 * @template T
 * @param {T} inicial
 */
export function crearEstado(inicial) {
  let valor = inicial;
  const oyentes = new Set();
  return {
    /** @returns {T} */
    get: () => valor,
    /** @param {Partial<T> | ((v: T) => T)} cambio */
    set(cambio) {
      valor = typeof cambio === "function" ? cambio(valor) : { ...valor, ...cambio };
      oyentes.forEach((fn) => fn(valor));
    },
    /** @param {(v: T) => void} fn @returns {() => void} desuscribir */
    subscribe(fn) {
      oyentes.add(fn);
      return () => oyentes.delete(fn);
    },
  };
}

/** Estado global de la aplicación. */
export const app = crearEstado({
  usuario: /** @type {null | {idtrabajador:number, nombre:string, email:string, rol:string}} */ (null),
  tema: "auto",
});
