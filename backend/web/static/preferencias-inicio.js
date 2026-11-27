/*
 * Pone la apariencia y el tamaño del texto que esta persona eligió en «Preferencias», antes de que el
 * navegador dibuje la página (por eso se carga en <head>, sin «defer»): así no se ve un parpadeo del
 * diseño por defecto. Se guardan solo en este navegador. Sin almacenamiento o sin elección, la página
 * queda en «Oscuro» (como la app y la página de presentación) y con el texto normal. Las páginas marcadas
 * con «data-tema-fijo» (la presentación de DOMUX) se ven siempre oscuras.
 */
(function () {
  "use strict";
  try {
    var root = document.documentElement;
    var theme = window.localStorage.getItem("domux.apariencia");
    if (!root.hasAttribute("data-tema-fijo") && (theme === "mixto" || theme === "auto")) {
      root.setAttribute("data-tema", theme);
    }
    var size = window.localStorage.getItem("domux.tamanoTexto");
    if (size === "grande" || size === "muy-grande") {
      root.setAttribute("data-texto", size);
    }
  } catch (error) {
    // Navegador sin almacenamiento (modo privado estricto): se queda la apariencia por defecto.
  }
})();
