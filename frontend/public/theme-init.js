/* Sets data-theme before first paint (external file: the CSP forbids inline scripts).
   Mirrors src/lib/theme.ts — keep the storage key and default in sync. */
(function () {
  var theme = "light";
  try {
    var pref = localStorage.getItem("algoprofitx-theme");
    if (pref === "light" || pref === "dark") theme = pref;
    else if (pref === "system") theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch (e) { /* storage blocked: default light */ }
  var root = document.documentElement;
  root.setAttribute("data-theme", theme);
  root.style.colorScheme = theme;
})();
