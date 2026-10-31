# Build a playable courtyard, not another data explorer

Goal: add `/o-portao/`, a third-person browser game about the voting extension. Leave the existing home, explorer and the separate extension-map branch unchanged.

## Scope and boundaries

- One fictional school courtyard, one player who has already voted at their assigned section, three approachable NPCs, an open exit and an optional later documentary epilogue.
- Walk, look around, approach, question, observe, reply to a personal message and choose whether to wait or leave. No combat, candidate selection, belief score, opinion telemetry or procedural voting simulation.
- Conversations and local events are explicitly fictional. National landmarks are attributed to sources. No fictional witness authenticates a historical claim.
- The news, interruption of counting, later clarification and letter are distinct. The letter's reported signature time is not its receipt time at a school. Do not assign a precise time to the later clarification.
- The original first decision's signing time and the original TSE letter remain unconfirmed here. Do not animate a closing procedure or fabricate an official document while electoral review is outstanding.
- The documentary uses declared public explanations, not invented private motives. Closure percentages do not establish extension-caused votes or prove the absence of every irregularity.

## Files and responsibilities

- `docs/site/o-portao/index.html`, `style.css`: full-screen scene, accessible dialogs, mobile movement controls, sources and no-JavaScript explanation.
- `state.mjs`: pure progression, knowledge provenance, conditional reply choices and collision movement.
- `content.mjs`: Portuguese NPC conversations and separately attributed documentary content.
- `world.mjs`: locally bundled Three.js, original procedural school, articulated characters, third-person camera, picking/proximity, collision shapes and lighting. No external model or texture dependencies.
- `audio.mjs`: optional synthesized ambience and footsteps; starts only after a user action, suspends on pause/background.
- `game.mjs`: keyboard/touch input, scene progression, dialogue, notebook, phone, ending and evidence integration. Opinion text stays in memory in the tab.
- `tests/test_portao_state.mjs`: deterministic progression, collision and attribution tests with Node's built-in runner.
- `scripts/portao_browser_check.cjs`: real keyboard/touch browser checks, early exit and documentary access, fallback, responsive layout and console/network failures.

## Build order and verification

1. Write pure state and tests before connecting the scene. Verify ordered progression, future information restrictions, no scoring and an always-available exit.
2. Build the original low-poly school and third-person controller. Test actual movement and proximity, not a list of teleport buttons as the primary game.
3. Connect fiction, explicit time cuts, local observation, optional notebook and message choices. Keep source documents outside the fictional world.
4. Add the documentary with public source links and optional actual final-section records. If shared facts or section files fail to load, show the limitation instead of replacing evidence with invented data.
5. Run Python regression tests, Node tests, existing site source checks and desktop/mobile Playwright checks. Inspect screenshots. Review state transitions independently before pushing.
6. Open a local preview, commit the isolated change and open a PR. Do not merge or deploy without approval.
