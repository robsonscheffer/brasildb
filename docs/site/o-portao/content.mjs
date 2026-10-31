// Original fictional dialogue. Historical documents belong only in DOCUMENTS below.
const say = (speaker, text) => ({ speaker, text });
const choice = (id, label, lines, text, source, kind = 'Ouvido') => ({ id, label, lines, note: text ? { key: id, text, kind, source } : null });

export const PEOPLE = {
  lia: { name: 'Lia', role: 'Eleitora · espera transporte' },
  davi: { name: 'Davi', role: 'Eleitor · perto do portão' },
  celia: { name: 'Célia', role: 'Mesária da sua seção' },
};

export function conversation(id, state) {
  if (id === 'lia') return {
    ...PEOPLE.lia,
    greeting: [say('Lia', state.phase >= 3 ? 'Pra quem já estava aqui, dá pra perguntar. Eu continuo sem saber se minha irmã vai chegar.' : state.phase >= 1 ? 'Até as sete… então talvez ela consiga. Mas a seção dela é longe daqui.' : 'Ela ainda tá esperando ônibus. E a seção dela é longe.')],
    choices: [
      choice('lia-transport', 'Você está esperando alguém?', [say('Lia', 'Minha irmã. Não aqui. Ela vota na seção dela, do outro lado do bairro. Eu só queria saber se ela consegue chegar.'), say('Lia', 'Eu já votei. Agora também tô tentando voltar pra casa.')], 'Lia diz que a irmã ainda tenta chegar à própria seção. O desfecho não é conhecido.', 'Lia · fala ficcional'),
      choice('lia-corridor', 'Você viu o que acontece no corredor?', [say('Lia', 'Eu vi gente ali. Então ainda tem voto entrando, não tem?'), say('Você', 'Eu ainda não sei o que aquele movimento significa.')], 'Lia interpretou o movimento no corredor como possível votação. Ela não viu o interior de cada seção.', 'Lia · fala ficcional'),
      ...(state.phase >= 1 ? [choice('lia-news', 'A notícia resolve o problema da sua irmã?', [say('Lia', 'Tomara que ajude. Mas ter mais tempo não faz aparecer um ônibus. Ela ainda precisa chegar na seção dela.')], 'Para Lia, a possibilidade de mais tempo não resolve sozinha o deslocamento da irmã.', 'Lia · fala ficcional')] : []),
    ],
  };
  if (id === 'davi') return {
    ...PEOPLE.davi,
    greeting: [say('Davi', state.phase === 0 ? 'Você também tá esperando carona? O pessoal tá saindo, mas ainda tem movimento lá dentro.' : state.phase >= 3 ? 'Tá. Mas quantas ainda estavam abertas no país inteiro? Quem aqui sabe disso?' : 'Estenderam até as sete. E quem já fechou? Vai abrir de novo? Isso não aumenta o risco de fraude?')],
    choices: state.phase === 0 ? [
      choice('davi-wait', 'O que você viu?', [say('Davi', 'Gente saindo. Papel sendo impresso. O resto eu não vi.')], 'Davi viu pessoas saindo e ouviu uma impressão. Não observou o funcionamento de todas as seções.', 'Davi · fala ficcional'),
    ] : [
      choice('davi-source', 'Mostra o que chegou.', [say('Davi', 'É essa notícia de prorrogação. Não diz o que acontece em cada sala.'), say('Você', 'Então a notícia e o estado desta seção são coisas diferentes.')], 'A notícia de prorrogação não informa o estado de cada seção desta escola.', 'Davi · fala ficcional'),
      choice('davi-witness', 'Você viu alguém voltar a votar?', [say('Davi', 'Voltar, eu não vi. Eu tô perguntando como vão fazer isso.')], 'Davi não presenciou reabertura. Sua fala expressa uma preocupação.', 'Davi · fala ficcional'),
      choice('davi-risk', 'O que exatamente te preocupa?', [say('Davi', 'Mudar o horário depois de tanta gente ter votado. Como eu sei se o tratamento vai ser igual?'), say('Davi', 'Eu não tenho o quadro inteiro. É por isso que eu tô perguntando.')], 'Davi teme tratamento desigual após uma mudança tardia. Ele não demonstra uma irregularidade.', 'Davi · fala ficcional'),
      ...(state.phase >= 2 ? [choice('davi-pause', 'Parou de divulgar ou mudou algum voto?', [say('Davi', 'Eu só sei que parou de atualizar. Sobre voto mudado, eu não vi nada.')], 'Davi diz que a atualização parou. Não viu alteração de voto.', 'Davi · fala ficcional')] : []),
      ...(state.known.has('clarification') ? [choice('davi-return', 'A orientação distingue continuar de reabrir.', [say('Davi', 'Então o anúncio não queria dizer reabrir tudo?'), say('Davi', 'Tá. Mas quantas ainda estavam abertas? Isso daqui não responde pelo país inteiro.')], 'Davi pergunta pela escala nacional. Uma explicação local não responde sozinha a essa questão.', 'Davi · fala ficcional')] : []),
    ],
  };
  return {
    ...PEOPLE.celia,
    greeting: [say('Célia', state.phase >= 3 ? 'A orientação agora está mais clara: continuar onde ainda não encerrou. Não é começar outra votação aqui.' : 'A nossa equipe está no encerramento. Posso conversar um instante aqui no corredor.')],
    choices: [
      choice('celia-local', 'O que a sua equipe está fazendo?', [say('Célia', 'Encerrando o trabalho desta seção. Esse barulho de impressão faz parte do que estamos terminando.'), say('Célia', 'Eu posso falar desta equipe. Não vou te dizer o que acontece em todas as outras.')], 'Célia disse que sua equipe estava encerrando. É um relato local da cena, não um registro histórico.', 'Célia · fala ficcional', 'Explicado por alguém'),
      choice('celia-other', 'E a outra sala?', [say('Célia', 'É outra seção. Eu não vou te dizer o que está acontecendo lá sem saber.')], 'Célia não afirma conhecer o estado da outra seção.', 'Célia · fala ficcional'),
      ...(state.phase >= 1 && state.phase < 3 ? [choice('celia-news', 'Vai começar de novo aqui?', [say('Célia', 'A nossa equipe está no encerramento. Eu preciso conferir a orientação sobre essa notícia.')], 'Célia ainda precisa conferir a orientação. Ela não apresenta o esclarecimento posterior como conhecido.', 'Célia · fala ficcional')] : []),
      ...(state.phase >= 3 ? [choice('clarification', 'O que a orientação distingue?', [say('Célia', 'Continuar onde ainda não encerrou. Não é começar outra votação nesta seção.'), say('Você', 'E isso explica o país inteiro?'), say('Célia', 'Não. Eu posso falar do que estamos fazendo aqui.')], 'Na passagem posterior da ficção, Célia explica a distinção entre continuar e reabrir. Isso não é um depoimento real.', 'Célia · fala ficcional posterior', 'Explicado por alguém')] : []),
      choice('celia-certainty', 'Então não existe risco nenhum?', [say('Célia', 'Eu posso explicar o que a gente está fazendo aqui. O resto precisa conferir.')], 'Célia não oferece garantia nacional com base na experiência desta seção.', 'Célia · fala ficcional'),
    ],
  };
}

export const PHASE_LINES = {
  1: [say('Davi', 'Pera aí. Estenderam até as sete.'), say('Lia', 'Então talvez ela consiga.'), say('Davi', 'E quem já fechou? Vai abrir de novo?')],
  2: [say('Telefone', 'Atualização dramatizada: a apuração foi interrompida.'), say('Davi', 'Agora até a apuração parou.')],
  3: [say('Passagem de tempo', 'Mais tarde, no mesmo pátio. A orientação ficou mais específica. O momento de chegada a esta escola é ficcional.')],
};

export const SOURCES = {
  chronology: { label: 'Exame · cronologia dos pedidos e da apuração', url: 'https://exame.com/brasil/veja-a-cronologia-dos-pedidos-de-lula-e-flavio-para-prorrogar-a-votacao-no-2o-turno/' },
  clarification: { label: 'STF · despacho posterior na Reclamação 101.673', url: 'https://portal.stf.jus.br/processos/downloadPeca.asp?id=15391720790&ext=.pdf' },
  letter: { label: 'Times Brasil · esclarecimento e ofício do TSE', url: 'https://timesbrasil.com.br/brasil/decisao-2026-tse-orienta-que-votacao-ate-as-19h-continue-apenas-nas-secoes-ainda-abertas/' },
  statement: { label: 'Correio do Estado / Estadão Conteúdo · declaração de Nunes Marques', url: 'https://correiodoestado.com.br/politica/nunes-marques-nao-houve-nenhuma-alteracao-advinda-de-decisao-do-stf/475528/' },
  facts: { label: 'BrasilDB · fatos e consultas SQL', url: '../data/curiosidades.json' },
  method: { label: 'BrasilDB · fontes, método e diferenças', url: '../como.html#fontes' },
};

// These are attributed documentary statements, not dialogue or proof of hidden motives.
// Editorial source review: 2026-10-31. No national query is recomputed by the game.
export const DOCUMENTS = [
  {
    tag: 'O motivo declarado', title: 'Antes da suspeita, um problema de acesso.',
    paragraphs: [
      'Segundo a Exame, as duas campanhas pediram prorrogação, mas com problemas e alcances distintos. A campanha de Lula invocou dificuldades de transporte; a de Flávio Bolsonaro citou chuvas, alagamentos, interdições e falta de energia em localidades determinadas.',
      'No esclarecimento posterior, Zanin declarou que as duas candidaturas alegaram problemas de transporte, razão pela qual concedeu a liminar. Essa é a justificativa declarada no documento, não uma comprovação de cada alegação nem da intenção íntima dos envolvidos.',
      'Lia e sua irmã são ficção. A história delas não comprova nenhuma das denúncias reais.',
    ], sources: ['chronology', 'clarification', 'letter'],
  },
  {
    tag: 'A notícia e a pausa', title: 'O anúncio não era um retrato de cada urna.',
    paragraphs: [
      'A Exame situa a divulgação da prorrogação às 17h03 e a interrupção da contagem e da divulgação às 17h06. A mesma cronologia informa a retomada da apuração às 19h.',
      'São marcos distintos. O minuto de divulgação não é um horário confirmado de assinatura. Uma pausa na apuração não é, por si, evidência de alteração de votos.',
      'Os alertas e o telefone vistos no pátio foram dramatizados. Não são capturas preservadas de uma notificação ou do sistema do TSE.',
    ], sources: ['chronology'],
  },
  {
    tag: 'O alcance da orientação', title: 'Continuar não é reabrir tudo.',
    paragraphs: [
      'No despacho posterior, Zanin determinou o cumprimento nos locais onde as urnas não tinham sido fechadas. Para as já fechadas, o texto prevê o cômputo e a totalização dos votos.',
      'O Times Brasil informa que o ofício de Nunes Marques aos presidentes dos tribunais regionais foi assinado às 17h49. Esse é o horário reportado para o ofício, não o momento em que cada mesária recebeu orientação.',
      'Não atribuímos um minuto exato ao despacho posterior nem à chegada da orientação à escola fictícia. O original integral do ofício do TSE e o horário exato de assinatura da primeira decisão não foram confirmados para esta experiência.',
    ], sources: ['clarification', 'letter'],
  },
  {
    tag: 'Os registros, depois', title: 'Quantas seções já tinham encerrado?',
    paragraphs: [
      'A análise publicada pelo BrasilDB informa 79,1% de seções encerradas às 17h03 e 98,5% às 17h49. Os percentuais vêm dos logs analisados, não das conversas da escola.',
      'O encerramento é diferente do último voto. Você pode inspecionar abaixo a sequência publicada para uma seção real, distinta da escola fictícia.',
      'Horários não identificam quem já estava na fila, quem votou por causa da prorrogação, a intenção do eleitor ou efeito causal sobre o resultado. As diferenças de cobertura estão no método.',
    ], sources: ['facts', 'method'], records: true,
  },
  {
    tag: 'O que foi dito e o que você conclui', title: 'Uma declaração não substitui os registros.',
    paragraphs: [
      'O Correio do Estado, com texto do Estadão Conteúdo, atribui a Nunes Marques a afirmação: “Não houve nenhuma alteração advinda da decisão judicial”. A mesma reportagem reproduz sua avaliação de que a hiperjudicialização produz consequências para o tempo de resposta jurisdicional.',
      'São declarações públicas identificadas. Não as tratamos como prova independente de ausência de toda irregularidade ou como demonstração da causa da demora.',
      'Você pode manter sua interpretação ou revê-la. Não há pontuação de confiança, resposta política correta ou avaliação automática do que você escrever.',
    ], sources: ['statement'], reflection: true,
  },
];
