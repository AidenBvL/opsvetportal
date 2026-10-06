/* OPS/VET Portaal: kleine hulpmiddelen voor de hele site. Geen framework nodig. */
(function () {
  "use strict";
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* geen opslag beschikbaar */ } },
  };

  // Thema wisselen (licht/donker), onthouden per browser.
  function applyThemeIcon() {
    const dark = document.documentElement.getAttribute("data-bs-theme") === "dark";
    $$("[data-theme-toggle] i").forEach(i => { i.className = dark ? "bi bi-sun" : "bi bi-moon-stars"; });
  }
  document.addEventListener("click", e => {
    const t = e.target.closest("[data-theme-toggle]");
    if (!t) return;
    const next = document.documentElement.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-bs-theme", next);
    store.set("opsvet-theme", next);
    applyThemeIcon();
  });
  applyThemeIcon();

  // Zijmenu: inklappen op desktop, uitschuiven op mobiel.
  document.addEventListener("click", e => {
    if (e.target.closest("[data-sidebar-compact]")) {
      const on = document.documentElement.classList.toggle("sidebar-compact");
      store.set("opsvet-sidebar", on ? "compact" : "full");
    }
    if (e.target.closest("[data-sidebar-open]")) document.body.classList.add("sidebar-open");
    if (e.target.closest("[data-sidebar-close]")) document.body.classList.remove("sidebar-open");
  });

  // Sneltoetsen: "/" of Ctrl+K = zoeken, "n" = nieuw-menu.
  document.addEventListener("keydown", e => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) || document.activeElement.isContentEditable;
    const search = $("#global-search");
    if (search && ((e.key === "/" && !typing) || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k"))) {
      e.preventDefault(); search.focus(); search.select();
    }
    if (e.key === "Escape" && document.activeElement === search) search.blur();
  });

  // Meldingen als toasts.
  $$(".toast").forEach(el => window.bootstrap && new bootstrap.Toast(el).show());

  // Klikbare tabelrijen (behalve als je op een link/knop/formulier klikt).
  document.addEventListener("click", e => {
    const row = e.target.closest("tr[data-href]");
    if (!row || e.target.closest("a, button, input, select, textarea, label, form")) return;
    if (e.ctrlKey || e.metaKey) window.open(row.dataset.href, "_blank");
    else window.location.href = row.dataset.href;
  });

  // Sorteerbare kolommen: <th data-sort> (optioneel data-sort="num" of "date"), waarde uit data-value of tekst.
  document.addEventListener("click", e => {
    const th = e.target.closest("th[data-sort]");
    if (!th) return;
    const table = th.closest("table"), tbody = table.tBodies[0];
    const idx = Array.from(th.parentNode.children).indexOf(th);
    const asc = !th.classList.contains("asc");
    $$("th[data-sort]", table).forEach(h => h.classList.remove("asc", "desc"));
    th.classList.add(asc ? "asc" : "desc");
    const kind = th.dataset.sort;
    const val = tr => {
      const cell = tr.children[idx];
      if (!cell) return "";
      const raw = cell.dataset.value ?? cell.textContent.trim();
      if (kind === "num" || kind === "date") { const n = parseFloat(raw); return isNaN(n) ? (asc ? Infinity : -Infinity) : n; }
      return raw.toLowerCase();
    };
    const rows = $$("tr", tbody).filter(tr => tr.children.length > 1);
    rows.sort((a, b) => { const x = val(a), y = val(b); return (x > y ? 1 : x < y ? -1 : 0) * (asc ? 1 : -1); });
    rows.forEach(r => tbody.appendChild(r));
  });

  // Zoekbare keuzelijsten (Tom Select) voor lange lijsten en meervoudige keuzes.
  function enhanceSelects(root = document) {
    if (!window.TomSelect) return;
    $$("select", root).forEach(sel => {
      if (sel.tomselect || sel.dataset.plain !== undefined || sel.closest(".toolbar, .no-ts")) return;
      if (!sel.multiple && sel.options.length < 8) return;
      new TomSelect(sel, {
        plugins: sel.multiple ? ["remove_button"] : [],
        maxOptions: 500,
        allowEmptyOption: true,
        create: false,
        render: { no_results: () => '<div class="no-results p-2 text-body-secondary">Niets gevonden</div>' },
      });
    });
  }
  enhanceSelects();

  // Bevestiging vóór een actie: <form data-confirm="Weet je het zeker?">.
  document.addEventListener("submit", e => {
    const msg = e.target.dataset && e.target.dataset.confirm;
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // Kopieerknoppen: <button data-copy="tekst">.
  document.addEventListener("click", async e => {
    const btn = e.target.closest("[data-copy]");
    if (!btn) return;
    try { await navigator.clipboard.writeText(btn.dataset.copy); btn.classList.add("text-success"); setTimeout(() => btn.classList.remove("text-success"), 1200); }
    catch (err) { window.prompt("Kopieer:", btn.dataset.copy); }
  });

  // Relatieve tijd: <span data-relative="2026-11-03T08:00:00+01:00">.
  const rtf = window.Intl && Intl.RelativeTimeFormat ? new Intl.RelativeTimeFormat("nl", { numeric: "auto" }) : null;
  function relative() {
    if (!rtf) return;
    const now = Date.now();
    $$("[data-relative]").forEach(el => {
      const t = Date.parse(el.dataset.relative);
      if (isNaN(t)) return;
      const diff = (t - now) / 1000, abs = Math.abs(diff);
      const [v, u] = abs < 3600 ? [diff / 60, "minute"] : abs < 86400 ? [diff / 3600, "hour"] : [diff / 86400, "day"];
      el.textContent = rtf.format(Math.round(v), u);
    });
  }
  relative();
  setInterval(relative, 60000);

  // Formulier: waarschuwen bij weggaan met niet-opgeslagen wijzigingen.
  $$("form[data-dirty-warning]").forEach(form => {
    let dirty = false;
    form.addEventListener("input", () => { dirty = true; });
    form.addEventListener("change", () => { dirty = true; });
    form.addEventListener("submit", () => { dirty = false; });
    window.addEventListener("beforeunload", e => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });
  });
})();
