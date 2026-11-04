/* Aplica el tema guardado antes de pintar (evita el destello claro→oscuro). Script clásico. */
(function () {
  try {
    var tema = JSON.parse(localStorage.getItem("factu.tema"));
    if (tema === "light" || tema === "dark") document.documentElement.dataset.theme = tema;
  } catch (e) {
    /* sin almacenamiento: se usa la preferencia del sistema */
  }
})();
