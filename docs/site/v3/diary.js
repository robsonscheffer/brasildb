/* V3 prototype. Scroll is input; no autoplay, scroll hijacking or synthetic vote times. */
"use strict";

const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
const $ = (id) => document.getElementById(id);
const pad = (n) => String(n).padStart(3, "0");
const node = (tag, className, text) => {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
};

async function init() {
  $("loading").hidden = false;
  const response = await fetch("./data/secao.json");
  if (!response.ok) throw new Error("Não foi possível carregar os registros.");
  const data = await response.json();
  if (data.schema !== 1 || !data.events?.length) throw new Error("Formato de dados inesperado.");
  const { events, summary, section } = data;
  const first = (type) => events.find((e) => e.type === type);
  const firstBattery = summary.battery_episodes[0].start;
  const afterBattery = events.find((e) => e.type === "vote" && e.time > firstBattery);
  const half = events.find((e) => e.key === "half");
  const chapters = [
    {
      id: "preparo", time: events[0].time, label: "O preparo", kicker: "ANTES DOS VOTOS",
      title: "O dia começa no zero.",
      copy: "Antes de receber o primeiro voto, eu imprimi a zerésima. Um registro de como a votação começava.",
    },
    {
      id: "abertura", time: first("open").time, label: "A abertura", kicker: "AS PORTAS ABREM",
      title: "Pode vir o primeiro.",
      copy: "Às 08:00:01, eu estava pronta. O primeiro voto foi computado às " + summary.first_vote + ". Depois dele, vieram os outros.",
    },
    {
      id: "bateria", time: firstBattery, label: "A bateria", kicker: "MUDA A ENERGIA",
      title: "Entrei na bateria. Continuei.",
      copy: "Às " + firstBattery + ", passei para a bateria. Às " + afterBattery.time + ", registrei mais um voto. O dia seguiu.",
    },
    {
      id: "ritmo", time: half.time, label: "O ritmo", kicker: "ENQUANTO ISSO, NO PAÍS",
      title: "Aqui, um de cada vez.",
      copy: "No minuto das " + half.time.slice(0, 5).replace(":", "h") + ", o país passou da metade dos votos registrados no dia. Nesta seção, cada linha continuava sendo um voto.",
    },
    {
      id: "encerramento", time: summary.last_vote, label: "O último voto", kicker: "A SEÇÃO ENCERRA",
      title: "O último foi o " + summary.votes + ".",
      copy: "Às " + summary.last_vote + ", registrei meu último voto. Às " + first("close").time + ", a votação foi encerrada. Depois, imprimi o boletim.",
    },
    {
      id: "apuracao", time: summary.arrival, label: "O resultado", kicker: "DEPOIS DA URNA",
      title: "Minha parte chegou ao registro.",
      copy: "O arquivo do TSE marca " + summary.arrival + " para esta seção. Mais tarde, o arquivo nacional já mostrava todas as seções totalizadas.",
    },
  ];

  document.querySelectorAll("[data-total]").forEach((e) => { e.textContent = summary.votes; });
  $("preview-vote").textContent = pad(afterBattery.votes);
  const nav = $("chapter-nav");
  const chapterSelect = $("mobile-chapters");
  const currentOption = node("option", "", "Capítulos");
  currentOption.value = "";
  currentOption.disabled = true;
  chapterSelect.replaceChildren(currentOption);
  chapterSelect.disabled = false;
  chapterSelect.addEventListener("change", () => {
    const target = document.getElementById(chapterSelect.value);
    if (location.hash !== "#" + target.id) history.pushState(null, "", "#" + target.id);
    target.scrollIntoView({ behavior: reducedMotion.matches ? "instant" : "smooth", block: "start" });
    target.focus({ preventScroll: true });
    chapterSelect.value = "";
  });
  const tape = $("tape");
  const fragment = document.createDocumentFragment();
  const sections = chapters.map((chapter, i) => {
    const link = node("a", "", chapter.label);
    link.href = "#" + chapter.id;
    const time = node("time", "", chapter.time.slice(0, 5));
    time.dateTime = section.date + "T" + chapter.time + "-03:00";
    link.append(time);
    nav.append(link);
    const option = node("option", "", String(i + 1).padStart(2, "0") + " " + chapter.label);
    option.value = chapter.id;
    chapterSelect.append(option);

    const block = node("section", "chapter");
    block.setAttribute("aria-labelledby", chapter.id + "-title");
    const heading = node("header", "chapter-heading");
    heading.id = chapter.id;
    heading.tabIndex = -1;
    heading.append(node("span", "chapter-kicker", String(i + 1).padStart(2, "0") + " / " + chapter.kicker));
    const title = node("h2", "", chapter.title);
    title.id = chapter.id + "-title";
    heading.append(title, node("p", "", chapter.copy));
    const list = node("ol", "records");
    list.setAttribute("aria-label", "Registros: " + chapter.label);
    block.append(heading, list);
    fragment.append(block);
    return list;
  });

  let chapterIndex = 0;
  const rows = events.map((event, index) => {
    while (chapterIndex < chapters.length - 1 && event.time >= chapters[chapterIndex + 1].time) chapterIndex++;
    event.chapter = chapterIndex;
    const row = node("li", "log-record");
    row.dataset.event = index;
    row.dataset.time = event.time;
    row.dataset.type = event.type;
    const time = node("time", "", event.precision === "minute" ? event.time.slice(0, 5) : event.time);
    time.dateTime = section.date + "T" + (event.precision === "minute" ? event.time.slice(0, 5) : event.time) + "-03:00";
    if (event.type === "national") {
      row.classList.add("national");
      const head = node("span", "national-heading", "ENQUANTO ISSO, NO BRASIL");
      head.append(time);
      row.append(head, node("strong", "national-label", event.label),
        node("span", "national-detail", event.detail),
        node("span", "national-source", "LOGS COLETADOS · PRECISÃO DE UM MINUTO"));
    } else if (event.type === "final") {
      row.classList.add("final-record");
      row.append(time, node("strong", "final-number", "100%"),
        node("span", "final-label", "DAS SEÇÕES TOTALIZADAS"),
        node("span", "final-detail", "O arquivo nacional gerado neste horário já mostra o total. O país terminou de contar."));
    } else {
      const isFirstVote = event.type === "vote" && event.votes === 1;
      const isLastVote = event.type === "vote" && event.votes === summary.votes;
      const isVotingBattery = event.type === "battery" && event.time >= summary.first_vote && event.time <= summary.last_vote;
      if (["zero", "open", "close", "bulletin", "arrival"].includes(event.type) || isFirstVote || isLastVote || isVotingBattery) {
        row.classList.add("special");
      }
      const label = isFirstVote ? "PRIMEIRO VOTO COMPUTADO" : isLastVote ? "ÚLTIMO VOTO COMPUTADO" : event.label;
      row.append(time, node("span", "log-label", label));
      if (event.type === "vote") {
        const count = node("span", "vote-number", pad(event.votes));
        count.append(node("small", "", "/" + summary.votes));
        row.append(count);
      }
    }
    sections[chapterIndex].append(row);
    return row;
  });
  tape.replaceChildren(fragment);
  $("tape-end").hidden = false;
  const marks = Array.from({ length: summary.votes }, () => node("i"));
  $("vote-marks").append(...marks);

  const links = [...nav.children];
  const hero = $("inicio");
  const preview = $("preview-paper");
  const progress = $("page-progress");
  const context = $("chapter-context");
  let positions = [];
  let active = -1;
  let activeChapter = -1;
  let previousVotes = 0;
  let scheduled = false;
  let chapterAnimation;
  let heroHeight = hero.offsetHeight;
  let maxScroll = document.documentElement.scrollHeight - innerHeight;

  function measure() {
    positions = rows.map((row) => row.getBoundingClientRect().top + scrollY + row.offsetHeight / 2);
    heroHeight = hero.offsetHeight;
    maxScroll = document.documentElement.scrollHeight - innerHeight;
    schedule();
  }

  function render() {
    scheduled = false;
    const y = scrollY;
    progress.style.transform = "scaleX(" + Math.min(1, y / Math.max(1, maxScroll)) + ")";
    if (!reducedMotion.matches && innerWidth > 900 && y <= heroHeight) {
      preview.style.setProperty("--paper-y", Math.min(24, y * .055) + "px");
    } else {
      preview.style.removeProperty("--paper-y");
    }
    // The active record is the last midpoint above the reading position.
    const readingPosition = y + Math.max(innerWidth <= 900 ? 85 : 150, innerHeight * .52);
    let lo = 0, hi = positions.length;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (positions[mid] <= readingPosition) lo = mid + 1;
      else hi = mid;
    }
    const next = lo - 1;
    if (next === active) return;
    if (active >= 0) rows[active].classList.remove("is-current");
    active = next;
    if (active >= 0) rows[active].classList.add("is-current");
    const current = events[Math.max(0, active)];
    const votes = active < 0 ? 0 : current.votes;
    $("clock-main").textContent = current.time.slice(0, 5);
    $("clock-seconds").textContent = current.precision === "minute" ? "min" : current.time.slice(6);
    $("mobile-clock").textContent = current.precision === "minute" ? current.time.slice(0, 5) : current.time;
    $("bar-count").textContent = pad(votes);
    $("index-count").textContent = pad(votes);
    if (previousVotes > 0) marks[previousVotes - 1].classList.remove("current");
    for (let i = Math.min(previousVotes, votes); i < Math.max(previousVotes, votes); i++) {
      marks[i].classList.toggle("read", i < votes);
    }
    if (votes > 0) marks[votes - 1].classList.add("current");
    previousVotes = votes;
    const phase = active < 0 ? 0 : current.chapter;
    document.body.dataset.activeChapter = chapters[phase].id;
    document.body.dataset.activeEvent = active;
    document.body.dataset.votes = votes;
    if (phase !== activeChapter) {
      const chapter = chapters[phase];
      currentOption.textContent = String(phase + 1).padStart(2, "0") + " " + chapter.label;
      chapterSelect.value = "";
      $("chapter-kicker").textContent = String(phase + 1).padStart(2, "0") + " / " + chapter.kicker;
      $("context-title").textContent = chapter.title;
      $("context-copy").textContent = chapter.copy;
      links.forEach((link, i) => {
        if (i === phase) link.setAttribute("aria-current", "step");
        else link.removeAttribute("aria-current");
      });
      chapterAnimation?.cancel();
      if (activeChapter >= 0 && !reducedMotion.matches) {
        chapterAnimation = context.animate([
          { opacity: .3, transform: "translateY(6px)" },
          { opacity: 1, transform: "translateY(0)" },
        ], { duration: 280, easing: "cubic-bezier(.2,.7,.2,1)" });
      }
      activeChapter = phase;
    }
  }

  function schedule() {
    if (!scheduled) { scheduled = true; requestAnimationFrame(render); }
  }

  addEventListener("scroll", schedule, { passive: true });
  addEventListener("resize", measure, { passive: true });
  reducedMotion.addEventListener("change", () => {
    chapterAnimation?.cancel();
    schedule();
  });
  const resize = new ResizeObserver(measure);
  resize.observe(document.querySelector("main"));
  document.fonts.ready.then(measure);
  measure();
  document.body.dataset.ready = "true";

  // Chapters are created after fetch. Restore a direct link without an animated fly-through.
  let hash;
  try { hash = decodeURIComponent(location.hash.slice(1)); } catch { hash = ""; }
  if (hash) {
    const target = document.getElementById(hash);
    if (target) {
      await document.fonts.ready;
      target.scrollIntoView({ behavior: "instant", block: "start" });
      measure();
    }
  }
}

init().catch((error) => {
  console.error("Diário:", error);
  const message = node("div", "load-error");
  message.setAttribute("role", "alert");
  message.append(node("p", "", "O diário não carregou. Recarregue a página ou abra o arquivo de dados."));
  const link = node("a", "", "Abrir os registros da seção");
  link.href = "./data/secao.json";
  message.append(link);
  $("tape").replaceChildren(message);
  document.body.dataset.ready = "error";
});
