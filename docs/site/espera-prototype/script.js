// Progressive enhancement only: text, images, charts and links work without JS.
const chapters = [...document.querySelectorAll("main > section")];
const links = [...document.querySelectorAll(".chapter-nav a")];
let scheduled = false;
function markChapter() {
  const line = window.innerHeight * 0.4;
  let current = chapters[0];
  for (const chapter of chapters) {
    if (chapter.getBoundingClientRect().top <= line) current = chapter;
  }
  for (const link of links) {
    if (link.hash === "#" + current.id) link.setAttribute("aria-current", "location");
    else link.removeAttribute("aria-current");
  }
  scheduled = false;
}
window.addEventListener("scroll", () => {
  if (!scheduled) { scheduled = true; requestAnimationFrame(markChapter); }
}, { passive: true });
window.addEventListener("resize", markChapter);
markChapter();
