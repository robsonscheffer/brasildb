import test from 'node:test';
import assert from 'node:assert/strict';
import { createState, advance, remember, replyChoices, canLeave, canAskClarification, move } from '../docs/site/o-portao/state.mjs';
import { conversation, DOCUMENTS } from '../docs/site/o-portao/content.mjs';

test('everyone can leave before seeking any evidence', () => {
  const state = createState();
  assert.equal(canLeave(state), true);
  assert.equal(state.known.size, 0);
  assert.deepEqual(replyChoices(state), ['Ainda não conferi.', 'Prefiro te explicar quando você chegar.']);
  assert.equal('score' in state, false);
});

test('news, suspension and later clarification are ordered and bounded', () => {
  const state = createState();
  assert.equal(canAskClarification(state), false);
  advance(state); assert.equal(state.phase, 1); assert(state.known.has('news'));
  assert.equal(canAskClarification(state), false);
  advance(state); assert.equal(state.phase, 2); assert(state.known.has('pause'));
  assert.equal(canAskClarification(state), false);
  advance(state); assert.equal(state.phase, 3); assert.equal(canAskClarification(state), true);
  assert.equal(advance(state), false);
  assert.equal(state.phase, 3);
});

test('later dialogue and previous sources remain distinguishable', () => {
  const state = createState();
  remember(state, 'celia-local', 'Minha equipe está encerrando.', 'Explicado por alguém', 'Célia · fala ficcional');
  assert(!replyChoices(state).some(choice => choice.includes('distingue')));
  advance(state); advance(state); advance(state);
  assert(!replyChoices(state).some(choice => choice.includes('distingue')));
  remember(state, 'clarification', 'A orientação distingue continuar de reabrir.', 'Explicado por alguém', 'Célia · fala ficcional posterior');
  assert(replyChoices(state).some(choice => choice.includes('distingue')));
  assert.equal(state.notes[0].source, 'Célia · fala ficcional');
});

test('notes are deduplicated and never promoted to historical documents', () => {
  const state = createState();
  assert.equal(remember(state, 'corridor', 'Movimento no corredor.', 'Observado', 'Cena ficcional'), true);
  assert.equal(remember(state, 'corridor', 'Prova de fraude.', 'Documento', 'Autoridade'), false);
  assert.equal(state.notes.length, 1);
  assert.equal(state.notes[0].kind, 'Observado');
  assert.equal(state.notes[0].source, 'Cena ficcional');
});

test('ending stops live chronology, not access to the documentary', () => {
  const state = createState(); state.ended = true;
  assert.equal(advance(state), false);
  assert.equal(canLeave(state), true);
});

test('Célia cannot offer the later clarification before the explicit time cut', () => {
  const state = createState();
  for (let phase = 0; phase < 3; phase++) {
    assert(!conversation('celia', state).choices.some(choice => choice.id === 'clarification'));
    assert(!conversation('celia', state).greeting.some(line => line.text.includes('orientação agora está mais clara')));
    advance(state);
  }
  assert(conversation('celia', state).choices.some(choice => choice.id === 'clarification'));
});

test('all routes have the same unfiltered documentary and all NPC notes remain fiction', () => {
  assert.equal(DOCUMENTS.length, 5);
  assert(DOCUMENTS.some(doc => doc.records));
  const state = createState(); advance(state); advance(state); advance(state);
  for (const id of ['lia', 'davi', 'celia']) for (const choice of conversation(id, state).choices) {
    if (choice.note) assert.match(choice.note.source, /ficcional/);
  }
});

test('collision blocks classrooms but allows the real gate opening', () => {
  const walls = [
    { minX: -13, maxX: 13, minZ: -14, maxZ: -7 },
    { minX: -13, maxX: -2, minZ: 12, maxZ: 12.4 },
    { minX: 2, maxX: 13, minZ: 12, maxZ: 12.4 },
  ];
  const intoClass = move({x: 0, z: -6.7}, {x: 0, z: -1}, .05, walls);
  assert.equal(intoClass.z, -6.7);
  const throughGate = move({x: 0, z: 12}, {x: 0, z: 1}, .05, walls);
  assert(throughGate.z > 12);
  const intoWall = move({x: 4, z: 11.6}, {x: 0, z: 1}, .05, walls);
  assert.equal(intoWall.z, 11.6);
});

test('diagonal movement is normalized and long frames cannot tunnel through walls', () => {
  const straight = move({x: 0, z: 0}, {x: 1, z: 0}, .05, []);
  const diagonal = move({x: 0, z: 0}, {x: 1, z: 1}, .05, []);
  assert(Math.abs(straight.distance - diagonal.distance) < 1e-10);
  const long = move({x: 0, z: 0}, {x: 1, z: 0}, 100, []);
  assert(long.distance <= .146);
});
