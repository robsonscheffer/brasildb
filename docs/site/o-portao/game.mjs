import { createState, advance, remember, replyChoices, PHASES } from './state.mjs';
import { PEOPLE, conversation, PHASE_LINES, DOCUMENTS, SOURCES } from './content.mjs';
import { createAudio } from './audio.mjs';

const $ = id => document.getElementById(id);
const state = createState();
const audio = createAudio();
const panel = $('panel');
const keys = new Set();
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
let world = null, started = false, reading = false, paused = false, audioEnabled = false;
let near = null, phaseAge = 0, elapsed = 0, last = 0, raf = null, stepAt = 0;
let announcementUntil = 0, panelKind = '', dialogPerson = null, touchedConversation = false;
let touch = {x: 0, z: 0}, joyPointer = null, lookPointer = null, lookX = 0, lookY = 0;
let documentToken = 0, documentaryData = null;
let returnFocus = null, crossedGate = false;

function el(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function action(text, callback, {primary = false, id} = {}) {
  const button = el('button', text, `action${primary ? ' primary' : ''}`);
  if (id) button.id = id;
  button.addEventListener('click', callback); return button;
}
function stopInput() {
  keys.clear(); touch = {x: 0, z: 0}; joyPointer = null; lookPointer = null;
  $('joystick-knob').style.transform = '';
}
function openPanel(kicker, title, {wide = false, kind = 'general'} = {}) {
  stopInput(); panelKind = kind; documentToken++;
  $('panel-kicker').textContent = kicker; $('panel-title').textContent = title;
  $('panel-body').replaceChildren(); panel.classList.toggle('wide', wide);
  if (!panel.open) { returnFocus = document.activeElement; panel.showModal(); }
  $('interaction').hidden = true;
  return $('panel-body');
}
function closePanel() { panel.close(); }
function sourceLinks(parent, ids) {
  const links = el('div', undefined, 'source-links');
  ids.forEach(id => { const source = SOURCES[id], link = el('a', `${source.label} ↗`); link.href = source.url; link.target = '_blank'; link.rel = 'noopener noreferrer'; links.append(link); });
  parent.append(links);
}
function line(parent, speaker, text) {
  const wrapper = el('div', undefined, 'dialogue-line'); wrapper.append(el('span', speaker, 'speaker'), el('p', text)); parent.append(wrapper);
}
function focusChoices() { panel.querySelector('.choices button, .action-row button, textarea, #close-panel')?.focus({preventScroll: true}); }

function refreshHUD() {
  $('clock').textContent = PHASES[state.phase].time;
  $('phase-label').textContent = PHASES[state.phase].label;
}
function advanceScene() {
  if (!advance(state)) return;
  phaseAge = 0; refreshHUD(); audio.notify(); $('phone-dot').hidden = false;
  const labels = {1:'ALERTA DRAMATIZADO · NOTÍCIA ÀS 17H03',2:'ATUALIZAÇÃO DRAMATIZADA · MARCO ÀS 17H06',3:'CORTE DE TEMPO FICCIONAL · MAIS TARDE'};
  const messages = {1:'A votação foi prorrogada até as sete. A notícia não diz o estado de cada seção.',2:'Segundo a cronologia da Exame, o TSE interrompeu a contagem e a divulgação.',3:'Você continuou esperando. A orientação agora distingue continuar de reabrir.'};
  $('announcement-source').textContent = labels[state.phase];
  $('announcement-text').textContent = messages[state.phase];
  $('announcement').hidden = false;
  $('subtitle').replaceChildren();
  PHASE_LINES[state.phase].forEach(({speaker,text}) => {const p=el('div');p.append(el('strong',`${speaker}: `),document.createTextNode(text));$('subtitle').append(p);});
  $('subtitle').hidden = false; announcementUntil = elapsed + 13;
  if (state.phase === 3) world?.setLater?.();
}

function talk(id) {
  if(!panel.open||panelKind!=='conversation'||dialogPerson!==id)touchedConversation=false;
  dialogPerson = id;
  const data = conversation(id, state);
  const body = openPanel(`${data.role} · conversa ficcional`, data.name, {kind:'conversation'});
  body.append(el('p', 'Conversa ficcional. Não é depoimento de uma pessoa real.', 'small'));
  data.greeting.forEach(({speaker,text}) => line(body,speaker,text));
  const choices = el('div', undefined, 'choices');
  data.choices.forEach(option => choices.append(action(option.label, () => answer(id, option))));
  choices.append(action('Voltar para o pátio', closePanel)); body.append(choices); focusChoices();
}
function answer(id, option) {
  const body = openPanel(`${PEOPLE[id].name} · conversa ficcional`, option.label, {kind:'conversation'});
  touchedConversation = true;
  if(option.note) { const n=option.note; remember(state,n.key,n.text,n.kind,n.source); }
  option.lines.forEach(({speaker,text}) => line(body,speaker,text));
  const row = el('div', undefined, 'action-row');
  row.append(action('Perguntar outra coisa', () => talk(id)), action('Voltar para o pátio', closePanel, {primary:true}));
  body.append(row); focusChoices();
}

function observe(id) {
  const isCorridor = id === 'corridor';
  const body = openPanel('OBSERVAÇÃO · CENA FICCIONAL', isCorridor ? 'O mesmo corredor. Trabalhos diferentes.' : 'O mural público.', {kind:'observation'});
  if(isCorridor) {
    remember(state,'corridor','Há movimento na outra sala e impressão perto da sua seção. Só observar o corredor não identifica a finalidade de cada atividade.','Observado','Encenação ficcional');
    body.append(el('p','Há pessoas terminando tarefas no corredor. Você ouve uma impressão perto da sala A. Na outra sala, há atividade, mas daqui não dá para identificar cada evento.'));
    body.append(el('p','Luz acesa e gente circulando, sozinhas, não demonstram que uma seção foi reaberta. Também não explicam tudo o que acontece no prédio.'));
  } else {
    remember(state,'notice','O mural da encenação sinaliza o acesso às salas. Não contém um boletim real nem demonstra o funcionamento de uma urna.','Observado','Mural ilustrativo da cena');
    body.append(el('p','Avisos sobre o acesso às salas e o espaço público. Não há aqui uma reprodução de boletim de urna, assinatura ou resultado de uma seção real.'));
    body.append(el('p','O som de uma impressora não permite concluir sozinho qual documento está sendo produzido. Você pode perguntar a Célia o que a equipe dela está fazendo.'));
  }
  body.append(action('Continuar observando o pátio',closePanel,{primary:true})); focusChoices();
}
function waitAtBench() {
  const body=openPanel('PASSAGEM DE TEMPO · ESCOLHA FICCIONAL','Sua carona ainda não chegou.',{kind:'wait'});
  body.append(el('p',state.phase<3?'Você pode continuar esperando ou voltar a caminhar. Não precisa recolher todas as conversas para avançar.':'Já se passou algum tempo. Você pode retomar uma conversa ou ir embora.'));
  if(state.phase<3)body.append(action(state.phase===2?'Continuar esperando a carona':'Esperar um pouco',()=>{advanceScene();closePanel();},{primary:true,id:'wait-forward'}));
  body.append(action('Voltar para o pátio',closePanel)); focusChoices();
}
function showNotebook() {
  const body=openPanel('CADERNO OPCIONAL · NÃO É UM PLACAR','O que você encontrou.',{kind:'notebook'});
  body.append(el('p','Origem e alcance importam. Nenhuma fala da escola vira prova histórica.', 'small'));
  if(!state.notes.length) body.append(el('p','Você ainda não registrou uma conversa ou observação. Pode explorar sem usar o caderno.'));
  state.notes.forEach(note=>{
    const entry=el('div',undefined,'entry');entry.append(el('p',note.kind,'eyebrow'),el('p',note.text),el('small',note.source));body.append(entry);
  });
  body.append(action('Fechar o caderno',closePanel)); focusChoices();
}
function showPhone() {
  $('phone-dot').hidden=true;
  const body=openPanel('TELEFONE FICCIONAL · CONVERSA PESSOAL','Sua carona.',{kind:'phone'});
  const message=el('div',undefined,'message');message.append(el('span','Mensagem pessoal · ficção'),el('p',state.phase===0?'Tô chegando. Me espera perto do portão.':'Aí voltaram a votar?'));body.append(message);
  if(state.phase>0){
    body.append(el('p','Você pode dizer o que encontrou, repetir o que ouviu ou dizer que ainda não sabe. Não há resposta pontuada.','small'));
    const choices=el('div',undefined,'choices');replyChoices(state).forEach(text=>choices.append(action(text,()=>{
      state.reply=text;
      const sent=openPanel('MENSAGEM PESSOAL · FICÇÃO','Sua resposta ficou nesta aba.',{kind:'phone'});
      const quote=el('div',undefined,'message');quote.append(el('span','Você'),el('p',text));sent.append(quote,el('p','Não foi enviada a ninguém nem salva no servidor.','small'),action('Voltar para o pátio',closePanel,{primary:true}));focusChoices();
    })));body.append(choices);
  }
  if(state.reply)body.append(el('p',`Sua resposta anterior: “${state.reply}”`,'small'));
  body.append(action('Guardar o telefone',closePanel)); focusChoices();
}

function leave() {
  const body=openPanel('A CARONA CHEGOU · FIM DA CENA FICCIONAL','E aí, o que você acha que aconteceu?',{wide:true,kind:'ending'});
  body.append(el('p','Você pode sair sem responder, registrar sua interpretação ou dizer que ainda não sabe. O jogo não avalia sua opinião.'));
  const label=el('label','Sua interpretação (opcional)','field');label.htmlFor='conclusion';
  const input=el('textarea');input.id='conclusion';input.spellcheck=false;input.autocomplete='off';input.setAttribute('autocorrect','off');input.maxLength=1200;input.value=state.conclusion;input.placeholder='O que você viu? O que ouviu? O que continua sem saber?';
  const row=el('div',undefined,'action-row');
  row.append(action('Sair e conferir os documentos',()=>{state.conclusion=input.value;state.ended=true;showSeparation();},{primary:true,id:'end-scene'}),action('Ainda não sei',()=>{state.conclusion='Ainda não sei.';state.ended=true;showSeparation();}));
  body.append(label,input,el('p','Sua resposta fica apenas na memória desta aba. Não usamos armazenamento persistente nem enviamos esse texto.','small'),row,action('Voltar para o pátio',closePanel));
  input.focus({preventScroll:true});
}
function showSeparation() {
  const body=openPanel('FIM DA CENA FICCIONAL','Agora, fora daquela escola.',{wide:true,kind:'ending'});
  body.append(el('p','A escola e as pessoas que você encontrou foram inventadas. Elas não são testemunhas reais da eleição.'));
  body.append(el('p','Os documentos e registros a seguir foram consultados depois dos acontecimentos. Não estavam todos disponíveis naquele pátio, em tempo real.'));
  if(state.conclusion) { const quote=el('div',undefined,'message');quote.append(el('span','Sua interpretação, sem avaliação'),el('p',state.conclusion));body.append(quote); }
  const row=el('div',undefined,'action-row');row.append(action('Abrir documentos e registros',()=>showDocument(0),{primary:true,id:'open-documents'}),action('Encerrar por aqui',showFinished));body.append(row);focusChoices();
}
function showFinished() {
  const body=openPanel('SEM PLACAR · SEM VEREDITO DO JOGO','O que você conclui fica com você.',{wide:true,kind:'ending'});
  if(state.conclusion)body.append(el('p',state.conclusion));
  body.append(el('p','Você pode voltar ao pátio ou consultar as fontes quando quiser. Nenhum texto seu foi enviado.'));
  const row=el('div',undefined,'action-row');row.append(action('Consultar os documentos',()=>showDocument(0),{primary:true}),action('Voltar para o pátio',closePanel));body.append(row);focusChoices();
}
async function json(path){const r=await fetch(path);if(!r.ok)throw new Error(`${path}: ${r.status}`);return r.json();}
async function loadDocumentary() {
  if(documentaryData)return documentaryData;
  const results=await Promise.allSettled([json('../data/curiosidades.json'),json('../data/secoes/SP/71072-0001.json')]);
  let facts=null,section=null;
  try {
    if(results[0].status==='fulfilled'&&Array.isArray(results[0].value?.itens)){
      const values=Object.fromEntries(results[0].value.itens.filter(item=>item&&typeof item.id==='string').map(item=>[item.id,item]));
      const place=values.ultimo_voto?.lugar;
      if(values.stf?.certo&&typeof values.stf.texto==='string'&&values.stf.texto.includes('79,1%')&&values.stf.texto.includes('98,5%')&&values.ultimo_voto?.hora==='19:06:21'&&place?.id_municipio_tse==='71072'&&place?.zona==='0001'&&place?.secao==='0405')facts=values;
    }
    if(facts&&results[1].status==='fulfilled'){
      const raw=results[1].value,row=raw?.secoes?.['0405'];
      if(Array.isArray(row)&&Array.isArray(raw.campos)&&raw.campos.every(name=>typeof name==='string')){
        const candidate=Object.fromEntries(raw.campos.map((name,i)=>[name,row[i]]));
        if(Array.isArray(candidate.fim_log)&&candidate.fim_log.length>0&&candidate.fim_log.length<=7&&candidate.fim_log.every(n=>Number.isInteger(n)&&n>=0)&&typeof candidate.chegada==='string'&&/^\d{2}:\d{2}$/.test(candidate.chegada))section=candidate;
      }
    }
  } catch { facts=null;section=null; }
  const result={facts,section};
  if(facts&&section)documentaryData=result;
  return result;
}
function addRecords(parent,data){
  if(!data.section){parent.append(el('p','A sequência desta seção não pôde ser carregada. Abra o arquivo publicado para conferir; não substituímos dados ausentes por uma simulação.','small'));return;}
  const details=el('details');const summary=el('summary','Inspecionar uma seção real: São Paulo · zona 0001 · seção 0405','records-toggle');details.append(summary);
  details.append(el('p','Esta seção real não é a escola da ficção. Os horários abaixo são de Brasília. A primeira totalização não é o horário de transmissão.','small'));
  const list=el('ol',undefined,'record-list');
  function item(time,text){const li=el('li');li.append(el('time',time),el('span',text));list.append(li);}
  item(data.facts.ultimo_voto.hora,'Último voto registrado no Brasil, segundo a análise publicada.');
  const names=['Operador selecionou: Encerrar votação','Procedimento de encerramento confirmado','Gerando relatório [BU] [INÍCIO]','Imprimindo relatório [BU] via nº [1]','Fim de impressão','Gerando arquivo de resultado [bu.dat] + [Início]','Gerando arquivo de resultado [log.jez] + [Início]'];
  let seconds=0;
  if(Array.isArray(data.section.fim_log))data.section.fim_log.slice(0,names.length).forEach((delta,i)=>{seconds+=delta;const t=[Math.floor(seconds/3600),Math.floor(seconds%3600/60),seconds%60].map(n=>String(n).padStart(2,'0')).join(':');item(t,names[i]);});
  if(data.section.chegada)item(data.section.chegada,'Primeira totalização desta seção no TSE.');
  details.append(list);const link=el('a','Abrir o arquivo desta seção ↗');link.href='../data/secoes/SP/71072-0001.json';link.target='_blank';link.rel='noopener';details.append(link);parent.append(details);
}
async function showDocument(index){
  const doc=DOCUMENTS[index];
  const body=openPanel(`DEPOIS DA ELEIÇÃO · DOCUMENTOS REAIS · ${index+1} / ${DOCUMENTS.length}`,doc.title,{wide:true,kind:'documentary'});
  const token=documentToken;
  body.append(el('p',doc.tag,'document-count'));
  const copy=el('article',undefined,'document-copy');body.append(copy);
  if(doc.records){
    copy.append(el('p','Carregando os arquivos publicados…','small'));
    const data=await loadDocumentary().catch(()=>({facts:null,section:null}));if(token!==documentToken||!panel.open)return;
    copy.replaceChildren();
    if(data.facts)copy.append(el('p',doc.paragraphs[0]));
    else copy.append(el('p','Os fatos compartilhados não puderam ser carregados ou mudaram desde a revisão desta cena. Os percentuais não serão exibidos como evidência nesta versão. Consulte os arquivos e o método.'));
    doc.paragraphs.slice(1).forEach(text=>copy.append(el('p',text)));addRecords(copy,data);
  }else doc.paragraphs.forEach(text=>copy.append(el('p',text)));
  sourceLinks(body,doc.sources);
  if(doc.reflection){
    if(state.conclusion){const before=el('div',undefined,'message');before.append(el('span','O que você escreveu antes dos documentos'),el('p',state.conclusion));body.append(before);}
    const label=el('label','Quer manter ou rever sua interpretação? (opcional)','field');label.htmlFor='revised';const input=el('textarea');input.id='revised';input.spellcheck=false;input.autocomplete='off';input.setAttribute('autocorrect','off');input.maxLength=1200;input.value=state.revised||state.conclusion;body.append(label,input,el('p','Sem avaliação automática. Texto apenas nesta aba.','small'));
    const row=el('div',undefined,'action-row');row.append(action('Manter minha interpretação',showFinished),action('Guardar esta revisão na aba',()=>{state.revised=input.value;showRevision();},{primary:true,id:'save-revision'}));body.append(row);
  }
  const nav=el('div',undefined,'action-row');if(index>0)nav.append(action('← Documento anterior',()=>showDocument(index-1)));
  if(index<DOCUMENTS.length-1)nav.append(action('Próximo documento →',()=>showDocument(index+1),{primary:true,id:'next-document'}));
  else nav.append(action('Voltar para o pátio',closePanel));body.append(nav);panel.scrollTop=0;focusChoices();
}
function showRevision(){
  const body=openPanel('SUA INTERPRETAÇÃO · SEM AVALIAÇÃO','Você pode mudar de ideia. Ou não.',{wide:true,kind:'ending'});
  body.append(el('p',state.revised||'Você não escreveu uma nova interpretação.'),el('p','A evidência não muda conforme sua resposta. Não há pontuação ou envio de texto.','small'));
  const row=el('div',undefined,'action-row');row.append(action('Voltar aos documentos',()=>showDocument(0)),action('Voltar para o pátio',closePanel,{primary:true}));body.append(row);focusChoices();
}

function showSources(){
  const body=openPanel('FONTES E LIMITES','A escola é ficção. As fontes não.',{wide:true,kind:'sources'});
  body.append(el('p','Escola, personagens, conversas, mensagens pessoais e horários locais de chegada são inventados. Não encenamos o funcionamento técnico de uma urna nem reproduzimos um documento oficial fictício como autêntico.'));
  body.append(el('p','A cronologia nacional é atribuída à Exame; o esclarecimento pode ser lido no STF; o ofício é descrito pelo Times Brasil; os registros e o método são do BrasilDB. Justificativas públicas não demonstram intenções ocultas.'));
  body.append(el('p','O horário exato de assinatura da primeira decisão e o original integral do ofício do TSE não foram confirmados para esta experiência. Não confundimos assinatura, publicação e chegada a uma escola.'));
  body.append(el('p','Esta experiência é independente. Não identifica escolhas de eleitores, não calcula efeito causal da prorrogação e não conclui ausência de toda irregularidade. As afirmações documentais foram revistas editorialmente; a cena continua uma ficção.'));
  sourceLinks(body,Object.keys(SOURCES));
  body.append(action('Abrir o epílogo documental',()=>showDocument(0),{primary:true}),action('Voltar',closePanel));focusChoices();
}
function showPause(){
  paused=true;audio.suspend();if(raf!==null)cancelAnimationFrame(raf);raf=null;
  const body=openPanel('PAUSA','O pátio pode esperar.',{kind:'pause'});
  const choices=el('div',undefined,'choices');
  choices.append(action('Continuar',closePanel,{primary:true}));
  const sound=action(`Som ambiente: ${audioEnabled?'ligado':'desligado'}`,async()=>{audioEnabled=await audio.setEnabled(!audioEnabled);audio.suspend();sound.textContent=`Som ambiente: ${audioEnabled?'ligado':'desligado'}`;});choices.append(sound);
  choices.append(action('Fontes e limites',showSources),action('Modo sem movimento',()=>{reading=true;showReadingMenu();}),action('Sair pelo portão',leave));body.append(choices);focusChoices();
}
function showReadingMenu(){
  paused=false;
  const body=openPanel('ALTERNATIVA ACESSÍVEL · SEM MOVIMENTO 3D','O mesmo pátio, em leitura.',{wide:true,kind:'reading'});
  body.append(el('p',PHASES[state.phase].time,'reading-label'));
  body.append(el('p','Esta é uma alternativa ao controle do personagem, não a experiência de caminhada. As conversas, a ordem das informações e o acesso aos documentos são os mesmos.','small'));
  const choices=el('div',undefined,'reading-list');
  for(const id of Object.keys(PEOPLE))choices.append(action(`Conversar com ${PEOPLE[id].name}`,()=>talk(id)));
  choices.append(action('Observar o corredor',()=>observe('corridor')),action('Examinar o mural',()=>observe('notice')),action('Esperar a carona',waitAtBench),action('Telefone',showPhone),action('Caderno',showNotebook),action('Sair pelo portão',leave));body.append(choices);
  const row=el('div',undefined,'action-row');
  if(world)row.append(action('Voltar ao personagem 3D',()=>{reading=false;closePanel();},{primary:true}));
  row.append(action('Fontes e limites',showSources),action('Voltar à tela inicial',()=>{reading=false;started=false;closePanel();$('start-screen').hidden=false;$('hud').hidden=true;}));body.append(row);focusChoices();
}
function interact(){
  if(!near||panel.open||!started)return;
  if(PEOPLE[near.id])talk(near.id);
  else if(near.id==='bench')waitAtBench();
  else if(near.id==='gate')leave();
  else observe(near.id);
}

function tick(now){
  raf=null;
  const dt=Math.min((now-last)/1000||.016,.15);last=now;
  if(!document.hidden&&world){
    const active=started&&!panel.open&&!paused&&!state.ended&&!reading;
    if(active){elapsed+=dt;phaseAge+=dt;if((state.phase===0&&phaseAge>18)||(state.phase===1&&phaseAge>24))advanceScene();}
    const x=active?(Number(keys.has('d')||keys.has('arrowright'))-Number(keys.has('a')||keys.has('arrowleft'))+touch.x):0;
    const z=active?(Number(keys.has('w')||keys.has('arrowup'))-Number(keys.has('s')||keys.has('arrowdown'))+touch.z):0;
    const result=world.update(dt,{x,z},elapsed);near=result.near;
    if(active&&result.walkDistance-stepAt>.72){audio.step();stepAt=result.walkDistance;}
    $('interaction').hidden=!active||!near;
    if(near)$('interact').textContent=near.label;
    for(const id of Object.keys(PEOPLE)){
      const p=world.projectNPC(id),label=$(`label-${id}`);label.hidden=!started||!p?.visible;
      if(p){label.style.left=`${p.x}px`;label.style.top=`${p.y}px`;}
    }
    if(active&&result.exiting){crossedGate=true;leave();}
    if(elapsed>announcementUntil){$('announcement').hidden=true;$('subtitle').hidden=true;}
    world.render();
  }
  if(!document.hidden&&!paused&&!reading&&world&&started)raf=requestAnimationFrame(tick);
}
function ensureLoop(){if(raf===null&&!document.hidden&&world&&started&&!paused&&!reading){last=performance.now();raf=requestAnimationFrame(tick);}}
function contextLost(){
  stopInput();if(raf!==null)cancelAnimationFrame(raf);raf=null;audio.suspend();world=null;near=null;started=false;reading=false;paused=false;
  if(panel.open)panel.close();
  $('hud').hidden=true;$('fallback').hidden=false;$('loading').hidden=true;$('start-screen').hidden=true;
}
async function startGame(asReading=false){
  started=true;reading=asReading;paused=false;state.ended=false;
  $('start-screen').hidden=true;$('fallback').hidden=true;$('hud').hidden=false;
  if(!asReading){ensureLoop();audioEnabled=await audio.setEnabled(true);}
  else showReadingMenu();
  refreshHUD();
}

$('start').addEventListener('click',()=>startGame());
$('start-reading').addEventListener('click',()=>startGame(true));
$('fallback-reading').addEventListener('click',()=>startGame(true));
$('fallback-retry').addEventListener('click',()=>location.reload());
$('start-sources').addEventListener('click',showSources);
$('phone').addEventListener('click',showPhone);
$('notebook').addEventListener('click',showNotebook);
$('pause').addEventListener('click',showPause);
$('interact').addEventListener('click',interact);
$('close-panel').addEventListener('click',closePanel);
panel.addEventListener('close',()=>{
  const wasConversation=panelKind==='conversation';documentToken++;stopInput();
  if(state.ended||crossedGate){state.ended=false;crossedGate=false;world?.returnToCourtyard();}
  paused=false;if(!document.hidden)audio.resume();ensureLoop();
  if(wasConversation&&touchedConversation&&state.phase===0)advanceScene();
  if(reading&&started){showReadingMenu();return;}
  if(returnFocus?.isConnected&&returnFocus!==document.body&&!returnFocus.closest('[hidden]'))returnFocus.focus({preventScroll:true});
});
window.addEventListener('keydown',event=>{
  if(panel.open)return;
  if(!started)return;
  if(event.metaKey||event.ctrlKey||event.altKey){stopInput();return;}
  const key=event.key.toLowerCase();
  if(['w','a','s','d','arrowup','arrowdown','arrowleft','arrowright','e','j','t','escape','p'].includes(key))event.preventDefault();
  if(event.repeat&&['e','j','t','escape','p'].includes(key))return;
  if(key==='e')interact();else if(key==='j')showNotebook();else if(key==='t')showPhone();else if(key==='escape'||key==='p')showPause();else keys.add(key);
});
window.addEventListener('keyup',event=>keys.delete(event.key.toLowerCase()));
window.addEventListener('blur',()=>{stopInput();audio.suspend();});
window.addEventListener('focus',()=>{if(started&&!paused&&!document.hidden)audio.resume();});
document.addEventListener('visibilitychange',()=>{
  stopInput();
  if(document.hidden){if(raf!==null)cancelAnimationFrame(raf);raf=null;audio.suspend();}
  else{last=performance.now();if(!paused)audio.resume();ensureLoop();}
});
window.addEventListener('pagehide',()=>{if(raf!==null)cancelAnimationFrame(raf);raf=null;stopInput();audio.suspend();});
window.addEventListener('pageshow',()=>{ensureLoop();});

const stick=$('joystick');
function moveStick(event){
  const r=stick.getBoundingClientRect(),dx=event.clientX-(r.left+r.width/2),dy=event.clientY-(r.top+56),distance=Math.hypot(dx,dy),limit=34,scale=distance>limit?limit/distance:1;
  touch={x:dx*scale/limit,z:-dy*scale/limit};$('joystick-knob').style.transform=`translate(${dx*scale}px, ${dy*scale}px)`;
}
stick.addEventListener('pointerdown',event=>{if(panel.open)return;event.preventDefault();joyPointer=event.pointerId;stick.setPointerCapture(event.pointerId);moveStick(event);});
stick.addEventListener('pointermove',event=>{if(event.pointerId===joyPointer)moveStick(event);});
function releaseStick(event){if(event.pointerId!==joyPointer)return;joyPointer=null;touch={x:0,z:0};$('joystick-knob').style.transform='';}
stick.addEventListener('pointerup',releaseStick);stick.addEventListener('pointercancel',releaseStick);stick.addEventListener('lostpointercapture',releaseStick);
$('world').addEventListener('pointerdown',event=>{if(!started||panel.open||!world)return;lookPointer=event.pointerId;lookX=event.clientX;lookY=event.clientY;event.target.setPointerCapture(event.pointerId);});
$('world').addEventListener('pointermove',event=>{if(lookPointer!==event.pointerId||!world)return;world.setLook(event.clientX-lookX,event.clientY-lookY);lookX=event.clientX;lookY=event.clientY;});
function releaseLook(event){if(lookPointer===event.pointerId)lookPointer=null;}
$('world').addEventListener('pointerup',releaseLook);$('world').addEventListener('pointercancel',releaseLook);$('world').addEventListener('lostpointercapture',releaseLook);

for(const id of Object.keys(PEOPLE)){const label=el('div',PEOPLE[id].name,'npc-label');label.id=`label-${id}`;label.hidden=true;$('npc-labels').append(label);}
(async()=>{
  try{
    const {createWorld}=await import('./world.mjs');
    world=createWorld($('world'),{onContextLost:contextLost,reducedMotion});
    $('start').disabled=false;$('loading').hidden=true;ensureLoop();
  }catch(error){
    $('loading').textContent='O modo 3D não está disponível. Use a alternativa sem movimento ou tente novamente.';
    $('start').textContent='3D indisponível';$('fallback').hidden=false;$('start-screen').hidden=true;
  }
})();
