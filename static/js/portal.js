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
    if (!th || e.target.closest(".col-hide")) return;
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

  // Tabbladen: openen via #hash in de URL (bijv. na uploaden terug naar #tab-docs) en de hash bijwerken bij wisselen.
  if (window.bootstrap && location.hash) {
    const tab = $(`[data-bs-toggle="tab"][data-bs-target="${CSS.escape(location.hash)}"]`);
    if (tab) bootstrap.Tab.getOrCreateInstance(tab).show();
  }
  document.addEventListener("shown.bs.tab", e => {
    const target = e.target.dataset.bsTarget;
    if (target && target.startsWith("#tab-")) history.replaceState(null, "", target);
  });
  document.addEventListener("click", e => {
    const link = e.target.closest("a[data-open-tab]");
    const tab = link && $(`[data-bs-toggle="tab"][data-bs-target="${link.dataset.openTab}"]`);
    if (!tab || !window.bootstrap) return;
    e.preventDefault();
    bootstrap.Tab.getOrCreateInstance(tab).show();
    tab.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  // Uploadvak: bestanden slepen of kiezen; direct versturen.
  $$("[data-dropzone]").forEach(zone => {
    const form = zone.closest("form"), input = $("input[type=file]", zone);
    if (!form || !input) return;
    const send = () => { if (input.files.length) { zone.classList.add("is-busy"); form.submit(); } };
    input.addEventListener("change", send);
    ["dragenter", "dragover"].forEach(t => zone.addEventListener(t, e => { e.preventDefault(); zone.classList.add("is-over"); }));
    ["dragleave", "drop"].forEach(t => zone.addEventListener(t, () => zone.classList.remove("is-over")));
    zone.addEventListener("drop", e => {
      e.preventDefault();
      if (!e.dataTransfer.files.length) return;
      input.files = e.dataTransfer.files;
      send();
    });
  });

  // Havenveld: volledige naam tonen bij de code ("BRPNG" -> "Paranaguá, Brazilië").
  const plain = v => (v || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toUpperCase().trim();
  $$("input[data-port-input]").forEach(input => {
    const list = input.list, label = input.parentElement.querySelector("[data-port-name]");
    if (!list || !label) return;
    const update = () => {
      const value = plain(input.value);
      if (!value) { label.textContent = ""; return; }
      const options = Array.from(list.options);
      const hit = options.find(o => o.value === value.replace(/\s/g, ""))
        || options.find(o => plain(o.textContent.split(",")[0]) === value.split(/[,(]/)[0].trim());
      label.textContent = hit ? `${hit.textContent} (${hit.value})` : "Onbekende haven: wordt opgeslagen zoals ingevuld (toe te voegen onder Stamgegevens > Havens).";
      label.classList.toggle("text-warning-emphasis", !hit);
    };
    input.addEventListener("input", update);
    update();
  });

  // Adres uit het adresboek kiezen: adresveld en chauffeursinstructies invullen.
  $$("select[data-fill-place]").forEach(select => {
    select.addEventListener("change", () => {
      const option = select.selectedOptions[0];
      if (!option || !option.value) return;
      const place = document.getElementById(select.dataset.fillPlace);
      if (place && option.dataset.place) place.value = option.dataset.place;
      const notes = select.dataset.fillInstructions && document.getElementById(select.dataset.fillInstructions);
      if (notes && option.dataset.instructions && (!notes.value.trim() || notes.dataset.autoFilled === notes.value)) {
        notes.value = option.dataset.instructions;
        notes.dataset.autoFilled = notes.value;
      }
    });
  });

  // Kolom direct verbergen vanuit de kolomkop (via het kolommenmenu, zodat het bewaard wordt).
  document.addEventListener("click", e => {
    const btn = e.target.closest("[data-hide-col]");
    if (!btn) return;
    const box = document.getElementById(`col-${btn.dataset.hideCol}`);
    if (!box) return;
    box.checked = false;
    box.closest("form").submit();
  });

  // Kolommenmenu: volgorde slepen of met pijltjes, kant-en-klare indelingen.
  $$("[data-column-list]").forEach(list => {
    const items = () => $$("li[data-key]", list);
    const lockedCount = () => items().filter(li => li.getAttribute("draggable") === "false").length;
    let dragged = null;
    list.addEventListener("dragstart", e => {
      dragged = e.target.closest("li[draggable=true]");
      if (!dragged) return;
      dragged.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
    });
    list.addEventListener("dragend", () => { if (dragged) dragged.classList.remove("dragging"); dragged = null; });
    list.addEventListener("dragover", e => {
      if (!dragged) return;
      e.preventDefault();
      // Tijdens slepen meescrollen als je bij de boven- of onderrand van de lijst komt.
      const box = list.closest(".modal-body");
      if (box) {
        const rect = box.getBoundingClientRect(), edge = 60;
        if (e.clientY < rect.top + edge) box.scrollTop -= 12;
        else if (e.clientY > rect.bottom - edge) box.scrollTop += 12;
      }
      const after = items().filter(li => li !== dragged && li.getAttribute("draggable") === "true")
        .find(li => e.clientY < li.getBoundingClientRect().top + li.offsetHeight / 2);
      if (after) list.insertBefore(dragged, after); else list.appendChild(dragged);
    });
    list.addEventListener("click", e => {
      const btn = e.target.closest("[data-move]");
      if (!btn) return;
      const li = btn.closest("li"), all = items(), i = all.indexOf(li), j = i + Number(btn.dataset.move);
      if (j < lockedCount() || j >= all.length) return;
      if (Number(btn.dataset.move) < 0) list.insertBefore(li, all[j]); else list.insertBefore(all[j], li);
      btn.focus();
    });
    const form = list.closest("form");
    const presets = JSON.parse(($("#column-presets") || {}).textContent || "{}");
    form.addEventListener("click", e => {
      const btn = e.target.closest("[data-preset], [data-preset-none]");
      if (!btn) return;
      const keys = btn.dataset.preset ? presets[btn.dataset.preset].columns : [];
      items().forEach(li => { const box = $("input[type=checkbox]", li); if (!box.disabled) box.checked = keys.includes(li.dataset.key); });
      // Gekozen kolommen in de volgorde van de indeling bovenaan, de rest eronder.
      keys.slice().reverse().forEach(key => {
        const li = items().find(x => x.dataset.key === key);
        if (li && li.getAttribute("draggable") === "true") list.insertBefore(li, items()[lockedCount()]);
      });
    });
  });

  // Formulier: waarschuwen bij weggaan met niet-opgeslagen wijzigingen.
  $$("form[data-dirty-warning]").forEach(form => {
    let dirty = false;
    form.addEventListener("input", () => { dirty = true; });
    form.addEventListener("change", () => { dirty = true; });
    form.addEventListener("submit", () => { dirty = false; });
    window.addEventListener("beforeunload", e => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });
  });
})();
