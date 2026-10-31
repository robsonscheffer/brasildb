# A separate playable account of the voting extension

Goal: add `/prorrogacao/` to Votando without changing the existing home or map.

Architecture: static HTML, CSS and JavaScript, with a locally vendored Three.js orthographic map. Reuse the published facts and section records; generate a compact closure-by-city index from those records. No external runtime services.

## Constraints

- Portuguese copy. All clocks are Brasília time, second round of 25 October 2026.
- Distinguish the first news at 17:03 from the signing time, and the TSE communication at 17:49.
- Do not infer voter identity, candidate, queue length, extension-caused votes or electoral impact.
- The map contains 497,894 published principal section records with closure and totalization. The national query also includes sections without a closure timestamp. Display coverage and do not silently equate the datasets.
- Closure times are minute-resolution, compared strictly before the displayed minute. No interpolated evidence.
- Preserve document access without JavaScript or WebGL; respect reduced motion and keyboard input.

## Build and verify

1. Add a deterministic standard-library generator at `scripts/extension_data.py` and tests at `tests/test_extension_data.py`. Skip aggregated aliases and foreign sections, group closures by city and minute, retain provenance and coverage. Verify generated output matches all committed source records and reported checkpoints.
2. Create `docs/site/prorrogacao/index.html`, `style.css`, `story.js`, `map.js`, generated `closures.json`, and a pinned local Three.js module and license. Implement a reveal question, chapter controls, minute scrubber, city inspection and the final section's actual closing sequence. Facts are fetched from `../data/curiosidades.json`, not duplicated numeric constants.
3. Run Python tests and existing site checks. Run browser checks at desktop and phone sizes, including timeline endpoints, checkpoint transitions, city inspection, evidence, no-WebGL fallback, reduced motion and console/network errors. Open the local page for review.
4. Commit the isolated change, push its feature branch and open a PR. Do not merge or publish without confirmation.
