/* The reader's place, shared by every page (P5): one picker, one top bar with the place chip,
   one URL contract. A place is {cidade, zona, secao}: cidade is the TSE town id (abroad, the
   city id of exterior.json), zona and secao are 4 digits; zona and secao may be empty.
   The lists come from data/lugares/<UF>.json, so only sections we have can be picked. */
(() => {
  const D = "data/";
  const cache = {};
  const get = p => cache[p] || (cache[p] = fetch(D + p).then(r => { if (!r.ok) throw new Error(p); return r.json(); }));
  const norm = s => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"})[c]);
  const p4 = n => String(n).padStart(4, "0");

  // Every town: Brazil's (towns.json), then the cities abroad (exterior.json, uf ZZ).
  const cidades = (() => {
    let p = null;
    return () => p || (p = Promise.all([get("towns.json"), get("exterior.json")]).then(([t, e]) => {
      const out = t.id.map((id, i) => ({id: String(id), uf: t.uf[i], nome: t.nome[i]}))
        .concat(e.cidades.map(c => ({id: String(c.id), uf: "ZZ", nome: c.nome, pais: c.pais})));
      for (const c of out) c.busca = norm(`${c.nome} ${c.pais || ""}`);
      out.porId = new Map(out.map(c => [c.id, c]));
      return out;
    }));
  })();
  const rotulo = c => `${c.nome}, ${c.uf === "ZZ" ? c.pais : c.uf}`;
  async function cidade(id) { return id ? (await cidades()).porId.get(String(id)) || null : null; }
  async function buscar(q, max = 8) {
    q = norm(q.trim());
    if (q.length < 2) return [];
    const todas = await cidades(), a = [], b = [];
    for (const c of todas) {
      if (c.busca.startsWith(q)) { if (a.length < max) a.push(c); }
      else if (b.length < max && c.busca.includes(q)) b.push(c);
      if (a.length >= max) break;
    }
    return a.concat(b).slice(0, max);
  }

  // A city's zonas and sections: {zona: ["0001", ...]}, and agregadas {"zona-secao": principal}.
  async function secoes(c) {
    const uf = (await get(`lugares/${c.uf}.json`))[c.id] || {};
    const zonas = {};
    for (const [z, faixas] of Object.entries(uf)) {
      if (z === "agregadas") continue;
      zonas[z] = faixas.flatMap(f => Array.isArray(f) ? Array.from({length: f[1] - f[0] + 1}, (_, k) => p4(f[0] + k)) : [p4(f)]);
    }
    return {zonas, agregadas: uf.agregadas || {}};
  }

  // ---- URL: cidade, zona, secao on every page; other keys belong to the page.
  function ler(search = location.search) {
    const q = new URLSearchParams(search), d = v => (v || "").replace(/\D/g, "");
    const lugar = {cidade: d(q.get("cidade")), zona: d(q.get("zona")), secao: d(q.get("secao"))};
    if (lugar.zona) lugar.zona = p4(lugar.zona); else lugar.secao = "";
    if (lugar.secao) lugar.secao = p4(lugar.secao);
    if (!lugar.cidade) lugar.zona = lugar.secao = "";
    return lugar;
  }
  function query(lugar, extra = {}) {
    const q = new URLSearchParams();
    if (lugar?.cidade) {
      q.set("cidade", lugar.cidade);
      if (lugar.zona) q.set("zona", lugar.zona);
      if (lugar.zona && lugar.secao) q.set("secao", lugar.secao);
    }
    for (const [k, v] of Object.entries(extra)) if (v != null && v !== "") q.set(k, v);
    return q.toString();
  }
  const href = (pagina, lugar, extra) => { const q = query(lugar, extra); return q ? `${pagina}?${q}` : pagina; };
  function escrever(lugar, extra) { const q = query(lugar, extra); history.replaceState(null, "", q ? `?${q}` : location.pathname); }

  // ---- the picker: city search, then zona and seção as lists. Seção is optional.
  // opts: {lugar, onEscolher(lugar, cidade), botao}: without `botao`, each change is reported at once.
  let nPicker = 0;
  function seletor(el, opts = {}) {
    const n = ++nPicker;
    el.classList.add("lg-sel");
    el.innerHTML = `
      <label class="lg-campo lg-cid">Cidade
        <input type="text" inputmode="search" autocomplete="off" spellcheck="false" placeholder="Digite a sua cidade"
          role="combobox" aria-expanded="false" aria-autocomplete="list" aria-controls="lg-hits-${n}">
        <ul class="lg-hits" id="lg-hits-${n}" role="listbox" hidden></ul>
      </label>
      <div class="lg-par">
        <label class="lg-campo">Zona <select disabled><option value="">—</option></select></label>
        <label class="lg-campo">Seção <select disabled><option value="">—</option></select></label>
      </div>
      <small class="lg-nota">Cidade, zona e seção estão no título de eleitor e no app e-Título. A seção é opcional.</small>
      ${opts.botao ? `<div class="lg-acoes"><button type="button" class="lg-usar" disabled>${esc(opts.botao)}</button>${opts.onLimpar ? '<button type="button" class="lg-limpar">Limpar</button>' : ""}</div>` : ""}`;
    const input = el.querySelector("input"), ul = el.querySelector(".lg-hits");
    const [zSel, sSel] = el.querySelectorAll("select"), usar = el.querySelector(".lg-usar");
    let c = null, lista = null, hits = [], ativo = -1;
    const lugar = () => ({cidade: c?.id || "", zona: zSel.value, secao: zSel.value ? sSel.value : ""});
    const mudou = () => { if (usar) usar.disabled = !c; else if (c) opts.onEscolher?.(lugar(), c); };
    const opcoes = (sel, vs, v) => {
      sel.innerHTML = `<option value="">${sel === zSel ? "Toda a cidade" : "Toda a zona"}</option>` +
        vs.map(x => `<option${x === v ? " selected" : ""}>${x}</option>`).join("");
    };
    function preencherSecoes(v) {
      const ss = lista?.zonas[zSel.value] || [];
      opcoes(sSel, ss, v); sSel.disabled = !zSel.value;
    }
    async function porCidade(nova, z = "", s = "") {
      c = nova; lista = null;
      input.value = c ? rotulo(c) : "";
      zSel.disabled = sSel.disabled = true;
      opcoes(zSel, []); opcoes(sSel, []);
      if (!c) return;
      lista = await secoes(c);
      if (c !== nova) return;
      const zs = Object.keys(lista.zonas).sort();
      opcoes(zSel, zs, zs.includes(z) ? z : ""); zSel.disabled = !zs.length;
      preencherSecoes(s);
    }
    function fechar() { ul.hidden = true; input.setAttribute("aria-expanded", "false"); }
    function escolher(k) {
      const nova = hits[k]; if (!nova) return;
      fechar(); porCidade(nova).then(mudou).then(() => zSel.focus());
    }
    input.addEventListener("input", async () => {
      const q = input.value;
      if (c) { c = null; lista = null; zSel.disabled = sSel.disabled = true; opcoes(zSel, []); opcoes(sSel, []); if (usar) usar.disabled = true; }
      const r = await buscar(q);
      if (input.value !== q) return;
      hits = r; ativo = r.length ? 0 : -1;
      ul.innerHTML = r.map((h, k) => `<li role="option" data-k="${k}" aria-selected="${k === ativo}">${esc(h.nome)}<span>${esc(h.uf === "ZZ" ? h.pais : h.uf)}</span></li>`).join("");
      ul.hidden = !r.length; input.setAttribute("aria-expanded", String(!ul.hidden));
    });
    input.addEventListener("keydown", e => {
      if (ul.hidden) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault(); ativo = (ativo + (e.key === "ArrowDown" ? 1 : -1) + hits.length) % hits.length;
        [...ul.children].forEach((li, k) => li.setAttribute("aria-selected", String(k === ativo)));
      } else if (e.key === "Enter") { e.preventDefault(); escolher(Math.max(0, ativo)); }
      else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); fechar(); }
    });
    ul.addEventListener("mousedown", e => { const li = e.target.closest("li"); if (li) { e.preventDefault(); escolher(+li.dataset.k); } });
    input.addEventListener("blur", () => setTimeout(fechar, 120));
    zSel.addEventListener("change", () => { preencherSecoes(""); mudou(); });
    sSel.addEventListener("change", mudou);
    usar?.addEventListener("click", () => { if (c) opts.onEscolher?.(lugar(), c); });
    el.querySelector(".lg-limpar")?.addEventListener("click", () => opts.onLimpar());
    const pronto = (async () => {
      const l = opts.lugar;
      if (l?.cidade) await porCidade(await cidade(l.cidade), l.zona, l.secao);
    })();
    return {
      pronto,
      focar: () => (c ? zSel : input).focus({preventScroll: true}),
      definir: async l => porCidade(await cidade(l?.cidade), l?.zona, l?.secao),
    };
  }

  // ---- the sheet: the picker in a dialog. Resolves with {lugar, cidade}, or null when closed.
  // "Limpar" (only with a place set) resolves with an empty place and cidade null.
  function folha(lugarAtual, foco) {
    return new Promise(resolve => {
      const dlg = document.createElement("dialog");
      dlg.className = "lg-folha";
      dlg.setAttribute("aria-labelledby", "lg-folha-t");
      dlg.innerHTML = `<div class="lg-folha-topo"><h2 id="lg-folha-t">O seu lugar</h2>
        <button type="button" class="lg-x" aria-label="Fechar">×</button></div><div class="lg-corpo"></div>`;
      document.body.appendChild(dlg);
      let fim = null;
      const s = seletor(dlg.querySelector(".lg-corpo"), {lugar: lugarAtual, botao: "Usar este lugar",
        onEscolher: (lugar, c) => { fim = {lugar, cidade: c}; dlg.close(); },
        onLimpar: lugarAtual?.cidade ? () => { fim = {lugar: {cidade: "", zona: "", secao: ""}, cidade: null}; dlg.close(); } : null});
      dlg.querySelector(".lg-x").addEventListener("click", () => dlg.close());
      dlg.addEventListener("click", e => { if (e.target === dlg) dlg.close(); });
      dlg.addEventListener("keydown", e => e.stopPropagation()); // the home's stepper keys stay out
      dlg.addEventListener("close", () => { dlg.remove(); resolve(fim); });
      dlg.showModal();
      s.pronto.then(() => {
        if (foco === "secao") dlg.querySelectorAll("select")[lugarAtual?.zona ? 1 : 0].focus();
        else s.focar();
      });
    });
  }

  // ---- the top bar: site name, pages, and the place chip. opts: {pagina, onTrocar}.
  const PAGINAS = [["index.html", "Início"], ["apuracao.html", "A apuração"], ["como.html", "Como contamos"]];
  function barra(el, opts) {
    el.classList.add("lg-barra");
    el.innerHTML = `<button type="button" class="lg-menu" aria-expanded="false" aria-controls="lg-nav">Menu</button>
      <a class="lg-nome" href="index.html">O Brasil votando</a>
      <nav class="lg-nav" id="lg-nav" aria-label="Páginas">${PAGINAS.map(([p, t]) =>
        `<a href="${p}" data-p="${p}"${p === opts.pagina ? ' aria-current="page"' : ""}>${t}</a>`).join("")}</nav>
      <button type="button" class="lg-chip" aria-haspopup="dialog"></button>`;
    const chip = el.querySelector(".lg-chip");
    chip.addEventListener("click", () => opts.onTrocar?.());
    // Phones: the pages fold into a menu under the bar.
    const menu = el.querySelector(".lg-menu");
    const abrir = on => { el.classList.toggle("aberta", on); menu.setAttribute("aria-expanded", String(on)); };
    menu.addEventListener("click", e => { e.stopPropagation(); abrir(!el.classList.contains("aberta")); });
    document.addEventListener("click", e => { if (!el.contains(e.target)) abrir(false); });
    el.addEventListener("keydown", e => { if (e.key === "Escape" && el.classList.contains("aberta")) { e.stopPropagation(); abrir(false); menu.focus(); } });
    const api = {
      async mostrar(lugar) {
        const c = await cidade(lugar?.cidade);
        if (!c) { chip.innerHTML = `<span class="lg-vazio">Escolha o seu lugar</span>`; chip.setAttribute("aria-label", "Escolher o seu lugar"); }
        else {
          const z = lugar.zona ? `<span class="lg-z">\u00a0· zona ${lugar.zona}</span>` : "";
          const s = lugar.zona && lugar.secao ? `<span class="lg-s">\u00a0· seção ${lugar.secao}</span>` : "";
          chip.innerHTML = `<span class="lg-c">${esc(rotulo(c))}</span>${z}${s}<span class="lg-t">\u00a0· trocar</span>`;
          chip.setAttribute("aria-label", `Seu lugar: ${rotulo(c)}${lugar.zona ? `, zona ${lugar.zona}` : ""}${lugar.secao ? `, seção ${lugar.secao}` : ""}. Trocar`);
        }
        for (const a of el.querySelectorAll(".lg-nav a")) a.href = href(a.dataset.p, lugar);
        el.querySelector(".lg-nome").href = href("index.html", lugar);
      },
    };
    return api;
  }

  window.Lugar = {cidades, cidade, buscar, secoes, rotulo, ler, query, href, escrever, seletor, folha, barra};
})();
