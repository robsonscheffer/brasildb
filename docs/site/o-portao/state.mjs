// Pure, tab-local state. No opinion scoring, persistence, network or DOM.
export const PHASES = [
  { time: 'Fim da tarde', label: 'Você já votou. Sua carona ainda não chegou.' },
  { time: '17h03', label: 'Marco nacional: divulgação da prorrogação. Cena reconstituída.' },
  { time: '17h06', label: 'Marco nacional: interrupção da apuração, segundo a Exame.' },
  { time: 'Mais tarde', label: 'Passagem de tempo ficcional. Sem horário atribuído à chegada da orientação.' },
];

export function createState() {
  return { phase: 0, known: new Set(), notes: [], reply: '', conclusion: '', revised: '', ended: false };
}

export function remember(state, key, text, kind = 'Ouvido', source = 'Conversa ficcional') {
  if (state.known.has(key)) return false;
  state.known.add(key);
  state.notes.push({ key, text, kind, source });
  return true;
}

export function advance(state) {
  if (state.phase >= PHASES.length - 1 || state.ended) return false;
  state.phase++;
  if (state.phase === 1) remember(state, 'news', 'Chegou uma notícia de prorrogação. Ela não informa o estado de cada sala.', 'Ouvido', 'Alerta dramatizado; marco atribuído à Exame');
  if (state.phase === 2) remember(state, 'pause', 'A atualização dramatizada informa interrupção da apuração. Não mostra alteração de votos.', 'Ouvido', 'Atualização dramatizada; marco atribuído à Exame');
  return true;
}

export function replyChoices(state) {
  const choices = ['Ainda não conferi.'];
  if (state.known.has('news')) choices.push('Ouvi que prorrogaram. Não sei como ficou aqui.');
  if (state.known.has('corridor')) choices.push('Vi movimento, mas não sei o que era.');
  if (state.known.has('celia-local')) choices.push('Na minha seção, disseram que estavam encerrando.');
  if (state.known.has('clarification')) choices.push('A orientação que explicaram distingue continuar de reabrir.');
  choices.push('Prefiro te explicar quando você chegar.');
  return choices;
}

export function canAskClarification(state) { return state.phase >= 3; }
export function canLeave() { return true; }

export function collides(x, z, obstacles, radius = .30) {
  return obstacles.some(box => x + radius > box.minX && x - radius < box.maxX && z + radius > box.minZ && z - radius < box.maxZ);
}

export function move(position, direction, seconds, obstacles, speed = 2.9) {
  const length = Math.hypot(direction.x, direction.z);
  if (!length) return { x: position.x, z: position.z, distance: 0 };
  const dt = Math.min(Math.max(seconds, 0), .05);
  const dx = direction.x / Math.max(1, length) * speed * dt;
  const dz = direction.z / Math.max(1, length) * speed * dt;
  let { x, z } = position;
  if (!collides(x + dx, z, obstacles)) x += dx;
  if (!collides(x, z + dz, obstacles)) z += dz;
  return { x, z, distance: Math.hypot(x - position.x, z - position.z) };
}
