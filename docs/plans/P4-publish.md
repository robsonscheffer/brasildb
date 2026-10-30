# P4 publish checklist (W8)

The site is live at `/` since P4 W9. This list holds what the public page still needs. Robson
checks each line; a line is closed when its evidence is written next to it.

## Mobile navigation (new in W8)

- [x] N1 A bottom bar on phones: back, the fold's name and number (3 de 9), next. Tap targets
      at least 44px. It replaces the floating "próximo" button, which covers note text.
- [x] N2 Tapping the name opens the list of the 9 folds; a tap jumps to one.
- [x] N3 A first-screen hint ("role ou toque em próximo") that goes away after the first scroll.
- [x] N4 The current note stays above the bar (it sits at the top of the sheet); the bar
      covers only the dim notes still to come. The card fold and the footer get room for it.
- [x] N5 The close chart's caption ("escala comprimida...") fits at 390px; today it is cut.
      Evidence for N1 to N5: taps on next, back and the list at 390x844, 0 console errors (2026-10-30).

## Copy

- [x] C1 Every line of the walk through the copywriting skill, then copy-editing.
      Evidence: each changed line is listed old to new in the W8 copy PR; site_v2_check clean.
- [x] C2 Every sentence names a place, a minute or a number.
      Exempt: the hook's two lines under the 128.236.074 headline, note headlines whose time line
      carries the minute, buttons, prompts and the map legend, and the STF "decisão" line (F3).
- [x] C3 No "seguro", no "fraude", no side, no candidate; no em-dashes; pt-BR.
      Evidence: grep finds none of these in index.html or curiosidades.json (2026-10-30).
- [x] C4 Each term links to `como.html#<term>`.
      Evidence: urna, log, zona, secao, zeresima, hora, metade, solimoes, bateria, contingencia,
      encerramento, boletim, totalizacao and chegada link where the walk first uses them.
      Biometria, agregada and diferencas never appear in the walk, so they have no link.
- [x] C5 The night copy says "entrou na soma", not "transmite": `ha` is the count time.
      Evidence: the night fold counts "seções somadas"; its label is "apuração"; the urna trip's
      last step says "entra na soma do TSE". 0 console errors at 390x844 and 1440x900.

## Facts

- [ ] F1 Every row of P4's W1 table read against its SQL by a second session.
- [ ] F2 The "pico" fact (421.314) includes abroad; the Brazil curve peaks at 420.848. Say
      which one the page shows.
- [ ] F3 The STF minute: a source for the decision's time, or the page stops naming 17h15.
- [ ] F4 The time-zone country list (`PAIS`) checked against a source.
- [x] F5 The MG towns file is 37 KB gzip, over the 33 KB budget. Towns are now one array each, times in minutes, no aptos or secoes: MG 37.2 -> 27.6 KB gzip, SP 29.6 -> 22.1, largest 27.6.

## Public

- [ ] P1 A new OG image (one static image), replacing v1's `og.jpg`.
- [ ] P2 Share text and card checked on WhatsApp and Instagram, on a phone.
- [ ] P3 Meta description, page title and `robots`.
- [x] P4 A line naming the source (TSE open data) and the repo on the card or the footer.
      Evidence: footer of the walk and `/explorar/`, plus the note at the top of `como.html` (2026-10-30).
- [ ] P5 Old share links: `?t=` to `/explorar/`, `/v2/` to `/`, town links keep working.

## Access

- [ ] A1 Reduced motion: the calm page has every number.
- [ ] A2 Screen-reader tables behind each chart.
- [ ] A3 A keyboard walk from the first fold to the card.
- [ ] A4 390x844, 1440x900 and 1366x650 (short laptop): no clipped text, 0 console errors.

Done when no line is open and Robson says publish.
