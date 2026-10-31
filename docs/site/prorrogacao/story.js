const $ = id => document.getElementById(id);
const fmt = n => new Intl.NumberFormat('pt-BR').format(n);
const hm = minute => `${String(Math.floor(minute / 60)).padStart(2, '0')}:${String(minute % 60).padStart(2, '0')}`;
const hms = second => `${hm(Math.floor(second / 60))}:${String(second % 60).padStart(2, '0')}`;
async function get(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Não foi possível carregar ${path} (${response.status}).`);
  return response.json();
}
let chapter = 0, revealed = false, minute = 1023, data, facts, map = null;
const chapters = [
  {name: 'A NOTÍCIA', time: 1023, title: 'A votação foi prorrogada.<br><em>O que ainda acontecia?</em>', description: 'Uma notícia não conta o que cada urna estava fazendo. Os registros ajudam a reconstruir esse momento.', stat: '79,1%', label: 'JÁ TINHAM ENCERRADO', text: 'das seções já tinham encerrado quando saiu a primeira notícia da prorrogação. O país não estava inteiro votando.', caption: 'Primeira notícia. Não é a hora confirmada da assinatura.'},
  {name: 'A COMUNICAÇÃO', time: 1069, title: 'A ordem chega.<br><em>Quase tudo já encerrou.</em>', description: 'Às 17h49, o TSE comunicou a ordem aos tribunais regionais. Avance e volte no relógio para acompanhar os encerramentos.', stat: '98,5%', label: 'JÁ TINHAM ENCERRADO', text: 'das seções já estavam encerradas nesse momento, segundo a análise nacional dos logs.', caption: 'O TSE comunica a ordem aos tribunais regionais.'},
  {name: 'O QUE RESTAVA', time: 1146, title: 'O mapa apaga.<br><em>Um voto ainda entra.</em>', description: 'O último voto registrado no Brasil foi em São Paulo. Mas o último voto e o encerramento da seção não são a mesma coisa.', stat: '19h06', label: 'ÚLTIMO VOTO REGISTRADO NO BRASIL', text: 'em São Paulo. O horário, sozinho, não informa se a pessoa já estava na fila ou se votou por causa da prorrogação.', caption: 'Último voto registrado no Brasil. Há seções ainda encerrando.'},
  {name: 'CONFIRA O REGISTRO', time: 1150, title: 'Não é só uma luz.<br><em>É um registro que você abre.</em>', description: 'Siga a seção do último voto: encerramento, boletim, arquivos e entrada na totalização. A evidência fica disponível para conferência.', stat: 'Nunca em quem.', label: 'O QUE O LOG PERMITE VER', text: 'O registro conta quando a urna operou. Não identifica a escolha do eleitor. Veja a sequência abaixo e abra o arquivo publicado.', caption: 'Minuto do encerramento da seção do último voto.'}
];

function selectCity(id) {
  $('city').value = id || '';
  $('reset-view').hidden = !id;
  renderTime();
}
function renderTime() {
  $('clock').textContent = hm(minute);
  $('time').value = minute;
  $('time-output').value = hm(minute);
  $('clock-caption').textContent = minute === chapters[chapter].time ? chapters[chapter].caption : 'Relógio livre · a narrativa mantém seu marco de referência.';
  if (!data) return;
  let remaining = 0;
  for (const city of data.cities) remaining += city.total - city.closures.reduce((n, [m, count]) => n + (m < minute ? count : 0), 0);
  $('map-status').textContent = `${fmt(remaining)} de ${fmt(data.total)} seções do mapa sem encerramento antes de ${hm(minute)}.`;
  const city = data.cities.find(c => c.id === $('city').value);
  if (city) {
    const closed = city.closures.reduce((n, [m, count]) => n + (m < minute ? count : 0), 0);
    $('city-result').textContent = `${city.nome}, ${city.uf} · ${fmt(city.total - closed)} de ${fmt(city.total)} seções publicadas ainda sem encerramento antes de ${hm(minute)}. Não é uma contagem de pessoas votando.`;
  } else {
    $('city-result').textContent = 'Clique num ponto do mapa ou escolha pela lista. Não é necessário usar o mapa 3D.';
  }
  map?.update(minute, city?.id ?? null);
}
function renderChapter(moveFocus = false) {
  const current = chapters[chapter];
  minute = current.time;
  $('chapter-number').textContent = `${String(chapter + 1).padStart(2, '0')} / 04`;
  $('chapter-name').textContent = current.name;
  $('headline').innerHTML = current.title;
  $('description').textContent = current.description;
  $('stat').textContent = current.stat;
  $('stat').style.fontSize = chapter === 3 ? 'clamp(30px, 3.4vw, 48px)' : '';
  $('finding-label').textContent = current.label;
  $('finding-text').textContent = current.text;
  $('question').hidden = revealed;
  $('finding').hidden = !revealed;
  $('back').disabled = chapter === 0;
  $('next').hidden = !revealed;
  $('next').textContent = chapter === 3 ? 'Ver a sequência documental ↓' : 'Seguir os registros →';
  $('evidence').hidden = chapter !== 3;
  $('feedback').hidden = chapter !== 0;
  if (chapter >= 2) selectCity(facts.ultimo_voto.lugar.id_municipio_tse);
  renderTime();
  if (moveFocus) {
    $('headline').tabIndex = -1; $('headline').focus({preventScroll: true});
    if (matchMedia('(max-width: 760px)').matches) $('investigacao').scrollIntoView();
  }
}
function reveal(answer) {
  revealed = true;
  $('loading').textContent = 'Mova o relógio, escolha uma cidade ou siga a investigação.';
  $('feedback').textContent = answer === 'nao' ? 'Sua hipótese coincide com os registros. Agora acompanhe o que restava.' : 'Os registros mostram o contrário: a maioria já tinha encerrado. Agora acompanhe o que restava.';
  $('time').disabled = false;
  document.querySelectorAll('[data-minute]').forEach(button => button.disabled = false);
  renderChapter(true);
}

async function loadEvidence() {
  const place = facts.ultimo_voto.lugar;
  const path = `../data/secoes/${place.uf}/${place.id_municipio_tse}-${place.zona}.json`;
  const file = await get(path);
  const row = file.secoes[place.secao];
  if (!Array.isArray(row)) throw new Error('Registro da seção indisponível.');
  const record = Object.fromEntries(file.campos.map((key, index) => [key, row[index]]));
  $('section-place').textContent = `${place.municipio}, ${place.uf} · Zona ${place.zona} · Seção ${place.secao}`;
  $('section-source').href = path;
  $('section-source').textContent = 'Abrir os dados desta seção ↗';
  const items = [[facts.ultimo_voto.hora, 'Último voto registrado nesta seção e no Brasil.']];
  const names = ['Operador selecionou: Encerrar votação', 'Procedimento de encerramento confirmado', 'Gerando relatório [BU] [INÍCIO]', 'Imprimindo relatório [BU] via nº [1]', 'Fim de impressão', 'Gerando arquivo de resultado [bu.dat] + [Início]', 'Gerando arquivo de resultado [log.jez] + [Início]'];
  let seconds = 0;
  (record.fim_log || []).forEach((delta, index) => { seconds += delta; items.push([hms(seconds), names[index]]); });
  if (record.chegada) items.push([record.chegada, 'Primeira totalização desta seção no TSE. Não é o horário de transmissão.']);
  for (const [time, text] of items) {
    const li = document.createElement('li'), clock = document.createElement('time'), label = document.createElement('span');
    clock.textContent = time; label.textContent = text; li.append(clock, label); $('records').append(li);
  }
}

$('next').addEventListener('click', () => {
  if (chapter === 3) { $('evidence').scrollIntoView(); $('evidence-title').tabIndex = -1; $('evidence-title').focus({preventScroll: true}); return; }
  chapter++; renderChapter(true);
});
$('back').addEventListener('click', () => { chapter = Math.max(0, chapter - 1); renderChapter(true); });
$('time').addEventListener('input', event => { minute = Number(event.target.value); renderTime(); });
document.querySelectorAll('[data-minute]').forEach(button => button.addEventListener('click', () => { minute = Number(button.dataset.minute); renderTime(); }));
$('city').addEventListener('change', event => selectCity(event.target.value));
$('reset-view').addEventListener('click', () => selectCity(''));
document.querySelectorAll('[data-answer]').forEach(button => button.disabled = true);

(async () => {
  try {
    const [closures, rawFacts] = await Promise.all([get('closures.json'), get('../data/curiosidades.json')]);
    data = closures; facts = Object.fromEntries(rawFacts.itens.map(fact => [fact.id, fact]));
    // Fail closed if the reviewed national checkpoints change upstream.
    if (!facts.stf?.certo || !facts.stf.texto.includes('79,1%') || !facts.stf.texto.includes('98,5%') || facts.ultimo_voto?.hora !== '19:06:21') throw new Error('Os fatos de referência mudaram. Consulte as fontes enquanto revisamos a narrativa.');
    const ordered = [...data.cities].sort((a, b) => `${a.nome} ${a.uf}`.localeCompare(`${b.nome} ${b.uf}`, 'pt-BR'));
    for (const city of ordered) {
      const option = document.createElement('option'); option.value = city.id; option.textContent = `${city.nome}, ${city.uf}`; $('city').append(option);
    }
    $('coverage').textContent = `O mapa reúne ${fmt(data.total)} seções principais com encerramento e totalização publicados. A análise nacional das porcentagens também inclui seções sem horário de encerramento. Não usamos a cobertura do mapa como denominador dessas porcentagens.`;
    document.querySelectorAll('[data-answer]').forEach(button => { button.disabled = false; button.addEventListener('click', () => reveal(button.dataset.answer)); });
    $('city').disabled = false;
    $('loading').textContent = 'Registros carregados. Comece pela sua hipótese.';
    renderTime();
    // The textual investigation never depends on WebGL or the map module.
    try {
      const [module, borders] = await Promise.all([import('./map.js'), get('../data/borders.json')]);
      map = module.createMap($('map'), data.cities, borders, id => selectCity(id));
      renderTime();
    } catch (error) { $('map-fallback').hidden = false; }
    try { await loadEvidence(); }
    catch (error) {
      const li = document.createElement('li'); li.textContent = 'Não foi possível carregar a sequência. Abra o arquivo da seção para conferir.'; $('records').append(li);
      $('section-source').href = `../data/secoes/SP/71072-0001.json`;
    }
  } catch (error) {
    $('loading').textContent = `${error.message} Recarregue a página para tentar novamente. As fontes continuam disponíveis abaixo.`;
    $('loading').setAttribute('role', 'alert');
  }
})();
