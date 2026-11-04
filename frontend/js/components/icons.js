/**
 * Iconos SVG propios (trazo 1.75, viewBox 24). Cada icono es una lista de trazos:
 * string = atributo d de un <path>; [cx, cy, r] = <circle>.
 */
const NS = "http://www.w3.org/2000/svg";

const ICONOS = {
  logo: ["M6 4h9l3 3v13H6z", "M9 10h6M9 14h6M9 18h3", "M15 4v3h3"],
  dashboard: ["M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z"],
  pos: ["M3 4h2l2.2 10.2a1.5 1.5 0 0 0 1.5 1.2h8.6a1.5 1.5 0 0 0 1.5-1.1L21 8H6.2", [9.5, 20, 1.3], [17, 20, 1.3]],
  users: ["M16 20v-1.5a3.5 3.5 0 0 0-3.5-3.5h-5A3.5 3.5 0 0 0 4 18.5V20", [10, 8, 3.5], "M20 20v-1.2a3 3 0 0 0-2.2-2.9M15.5 4.8a3.5 3.5 0 0 1 0 6.4"],
  box: ["M12 3l8 4.5v9L12 21l-8-4.5v-9z", "M4 7.5l8 4.5 8-4.5M12 12v9"],
  badge: ["M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z", [12, 10, 2.5], "M8.5 17c.6-2 2-3 3.5-3s2.9 1 3.5 3"],
  receipt: ["M6 3h12v18l-3-2-3 2-3-2-3 2z", "M9 8h6M9 12h6M9 16h3"],
  invoice: ["M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7z", "M14 3v4h4M9 13h6M9 17h6M9 9h2"],
  wallet: ["M4 7a2 2 0 0 1 2-2h11v4", "M4 7v10a2 2 0 0 0 2 2h14V9H6a2 2 0 0 1-2-2z", [16.5, 14, 1]],
  chart: ["M4 20V4M4 20h16M8 16v-4M12 16V8M16 16v-6"],
  search: [[11, 11, 7], "M20 20l-4-4"],
  plus: ["M12 5v14M5 12h14"],
  minus: ["M5 12h14"],
  x: ["M6 6l12 12M18 6L6 18"],
  check: ["M5 12.5l4.5 4.5L19 7"],
  menu: ["M4 6h16M4 12h16M4 18h16"],
  sidebar: ["M4 5h16v14H4zM9 5v14"],
  chevronLeft: ["M15 6l-6 6 6 6"],
  chevronRight: ["M9 6l6 6-6 6"],
  chevronDown: ["M6 9l6 6 6-6"],
  arrowLeft: ["M19 12H5M11 6l-6 6 6 6"],
  edit: ["M4 20h4L19 9l-4-4L4 16z", "M13.5 6.5l4 4"],
  trash: ["M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6"],
  eye: ["M2.5 12S6 5 12 5s9.5 7 9.5 7-3.5 7-9.5 7S2.5 12 2.5 12z", [12, 12, 3]],
  eyeOff: ["M3 3l18 18M10.6 5.1A10 10 0 0 1 12 5c6 0 9.5 7 9.5 7a17 17 0 0 1-2.6 3.6M6.6 6.6C3.9 8.4 2.5 12 2.5 12S6 19 12 19a9.6 9.6 0 0 0 5.4-1.6M9.9 9.9a3 3 0 0 0 4.2 4.2"],
  logout: ["M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 16l-4-4 4-4M6 12h10"],
  sun: [[12, 12, 4], "M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"],
  moon: ["M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"],
  copy: ["M9 9h10v11H9z", "M5 15V4h10"],
  download: ["M12 4v11M7 10l5 5 5-5M5 20h14"],
  upload: ["M12 16V5M7 10l5-5 5 5M5 20h14"],
  mail: ["M4 6h16v12H4z", "M4 7l8 6 8-6"],
  refresh: ["M20 11a8 8 0 0 0-14.7-4.3L4 8M4 4v4h4", "M4 13a8 8 0 0 0 14.7 4.3L20 16M20 20v-4h-4"],
  alert: ["M12 3l9.5 17h-19z", "M12 10v4M12 17h.01"],
  info: [[12, 12, 9], "M12 11v5M12 8h.01"],
  checkCircle: [[12, 12, 9], "M8 12.5l2.7 2.7L16 10"],
  xCircle: [[12, 12, 9], "M9 9l6 6M15 9l-6 6"],
  printer: ["M7 9V3h10v6", "M7 17H4v-7h16v7h-3", "M7 14h10v7H7z"],
  qr: ["M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4z", "M14 14h2v2h-2zM18 18h2v2h-2zM14 18h2M18 14h2"],
  card: ["M3 6h18v12H3z", "M3 10h18M7 15h3"],
  cash: ["M3 7h18v10H3z", "M6 10v4M18 10v4", [12, 12, 2.2]],
  bank: ["M3 10l9-6 9 6", "M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 20h18"],
  clock: [[12, 12, 9], "M12 7v5l3 2"],
  external: ["M14 4h6v6M20 4l-9 9", "M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"],
  key: [[8, 15, 4], "M11 12l9-9M17 6l2 2M15 8l2 2"],
  user: [[12, 8, 4], "M5 20c1-3.5 3.8-5 7-5s6 1.5 7 5"],
  sort: ["M8 4v16M4 8l4-4 4 4", "M16 20V4M12 16l4 4 4-4"],
  sortUp: ["M12 19V5M6 11l6-6 6 6"],
  sortDown: ["M12 5v14M6 13l6 6 6-6"],
  filter: ["M4 5h16l-6 7.5V19l-4 1v-7.5z"],
  ban: [[12, 12, 9], "M5.6 5.6l12.8 12.8"],
  send: ["M21 3L10 14", "M21 3l-7 18-4-7-7-4z"],
  stack: ["M12 3l9 5-9 5-9-5z", "M3 13l9 5 9-5"],
  undo: ["M9 14L4 9l5-5", "M4 9h11a5 5 0 0 1 0 10h-3"],
  trend: ["M3 17l6-6 4 4 8-8", "M15 7h6v6"],
};

/**
 * Crea un icono SVG decorativo (aria-hidden).
 * @param {keyof typeof ICONOS} nombre
 * @param {{size?: number, class?: string}} [opciones]
 * @returns {SVGSVGElement}
 */
export function icon(nombre, { size = 18, class: clase } = {}) {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", String(size));
  svg.setAttribute("height", String(size));
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.75");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  if (clase) svg.setAttribute("class", clase);
  for (const trazo of ICONOS[nombre] ?? ICONOS.info) {
    if (Array.isArray(trazo)) {
      const c = document.createElementNS(NS, "circle");
      c.setAttribute("cx", String(trazo[0]));
      c.setAttribute("cy", String(trazo[1]));
      c.setAttribute("r", String(trazo[2]));
      svg.append(c);
    } else {
      const p = document.createElementNS(NS, "path");
      p.setAttribute("d", trazo);
      svg.append(p);
    }
  }
  return svg;
}
