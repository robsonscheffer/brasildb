// Start a static server for docs/site, then run with Playwright installed.
// PLAYWRIGHT_MODULE=/path/to/playwright node scripts/portao_browser_check.cjs [base URL]
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.argv[2] || 'http://127.0.0.1:5185';
const gameURL = `${base}/o-portao/`;
async function walk(page, key, ms) {
  await page.keyboard.down(key); await page.waitForTimeout(ms); await page.keyboard.up(key);
  await page.waitForTimeout(80);
}
async function start(page) {
  await page.goto(gameURL);
  await page.waitForFunction(() => !document.querySelector('#start').disabled);
  await page.locator('#start').click();
  await page.locator('#hud').waitFor({state: 'visible'});
}
async function close(page) { await page.locator('#close-panel').click(); }
async function assertPanel(page, text) { await page.waitForFunction(t => document.getElementById('panel-title').textContent.includes(t), text); }
(async () => {
  const browser = await chromium.launch({headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 900}, reducedMotion: 'reduce'});
    const errors = [], failedRequests = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('response', response => { if(response.url().startsWith(base) && response.status() >= 400) failedRequests.push(response.url()); });
    await start(page);
    await page.screenshot({path:'/tmp/portao-game-desktop.png'});
    // The main path uses actual keyboard movement and proximity, not a test teleport.
    await walk(page,'a',1200); await walk(page,'w',1000);
    assert.equal(await page.locator('#interact').textContent(),'Conversar com Lia');
    await page.keyboard.press('e'); await assertPanel(page,'Lia');
    await page.getByRole('button',{name:'Você está esperando alguém?',exact:true}).click();
    assert.match(await page.locator('#panel-body').textContent(), /seção dela/);
    await page.screenshot({path:'/tmp/portao-game-conversation.png'});
    await page.getByRole('button',{name:'Voltar para o pátio',exact:true}).click();
    assert.equal(await page.locator('#clock').textContent(),'17h03');
    await page.keyboard.press('j'); assert.match(await page.locator('#panel-body').textContent(), /Lia · fala ficcional/); await close(page);
    await walk(page,'d',500); await walk(page,'w',2100); await walk(page,'a',1400); await walk(page,'w',250);
    assert.equal(await page.locator('#interact').textContent(),'Conversar com Célia');
    await page.keyboard.press('e'); await assertPanel(page,'Célia');
    assert.equal(await page.getByRole('button',{name:'O que a orientação distingue?',exact:true}).count(),0);
    await page.getByRole('button',{name:'O que a sua equipe está fazendo?',exact:true}).click();
    await page.getByRole('button',{name:'Voltar para o pátio',exact:true}).click();
    // Leave the corridor via an unobstructed path; walk to the actual waiting bench.
    await walk(page,'s',1000); await walk(page,'d',1000); await walk(page,'s',2500); await walk(page,'a',500);
    assert.equal(await page.locator('#interact').textContent(),'Sentar e esperar a carona');
    await page.keyboard.press('e'); await page.locator('#wait-forward').click();
    if(await page.locator('#clock').textContent() === '17h06') {
      await page.keyboard.press('e'); await page.locator('#wait-forward').click();
    }
    assert.equal(await page.locator('#clock').textContent(),'Mais tarde');
    await walk(page,'d',700); await walk(page,'w',3000); await walk(page,'a',1300); await walk(page,'w',450);
    assert.equal(await page.locator('#interact').textContent(),'Conversar com Célia');
    await page.keyboard.press('e');
    await page.getByRole('button',{name:'O que a orientação distingue?',exact:true}).click();
    assert.match(await page.locator('#panel-body').textContent(),/Não é começar outra votação/);
    await page.getByRole('button',{name:'Voltar para o pátio',exact:true}).click();
    await page.locator('#phone').click();
    await page.getByRole('button',{name:'A orientação que explicaram distingue continuar de reabrir.',exact:true}).click();
    assert.match(await page.locator('#panel-body').textContent(),/Não foi enviada a ninguém/); await close(page);
    await walk(page,'s',500); await walk(page,'d',2100); await walk(page,'s',6500);
    await assertPanel(page,'E aí, o que você acha');
    const opinion = 'Continuo com dúvidas. <img src=x onerror=alert(1)>';
    await page.locator('#conclusion').fill(opinion); await page.locator('#end-scene').click();
    assert.equal(await page.locator('#panel-body img').count(),0);
    await page.locator('#open-documents').click();
    await assertPanel(page,'Antes da suspeita');
    for(let i=0;i<3;i++) await page.locator('#next-document').click();
    await page.locator('.records-toggle').waitFor(); await page.locator('.records-toggle').click();
    assert.match(await page.locator('#panel-body').textContent(),/79,1%/);
    assert.match(await page.locator('.record-list').textContent(),/19:06:21/);
    assert.match(await page.locator('.record-list').textContent(),/19:10:29/);
    assert.match(await page.locator('.record-list').textContent(),/21:12/);
    await page.screenshot({path:'/tmp/portao-game-evidence.png'});
    await page.locator('#next-document').click();
    assert.equal(await page.locator('#revised').inputValue(),opinion);
    await page.locator('#revised').fill('Quero conferir mais fontes.'); await page.locator('#save-revision').click();
    assert.match(await page.locator('#panel-body').textContent(),/Quero conferir mais fontes/);
    assert.deepEqual(await page.evaluate(()=>({local:localStorage.length,session:sessionStorage.length})),{local:0,session:0});
    assert.deepEqual(errors,[]); assert.deepEqual(failedRequests,[]);
    console.log('Desktop: physical movement, proximity, NPCs, ordered time, conditional knowledge, exit, records and private reflection pass.');
    await page.close();

    const early = await browser.newPage({viewport:{width:1200,height:800}});
    await start(early); await walk(early,'s',4300); await assertPanel(early,'E aí, o que você acha');
    await early.getByRole('button',{name:'Ainda não sei',exact:true}).click();
    await early.locator('#open-documents').click(); await assertPanel(early,'Antes da suspeita');
    console.log('Early physical exit: no conversation or belief gates documentary access.');
    await early.close();

    const mobile=await browser.newPage({viewport:{width:390,height:844},hasTouch:true,isMobile:true,reducedMotion:'reduce'});
    const mobileErrors=[];mobile.on('pageerror',e=>mobileErrors.push(e.message));
    await start(mobile); await mobile.locator('#joystick').waitFor({state:'visible'});
    const rect=await mobile.locator('#joystick').boundingBox();
    const cx=rect.x+rect.width/2,cy=rect.y+56;
    await mobile.mouse.move(cx,cy);await mobile.mouse.down();await mobile.mouse.move(cx+30,cy+23);await mobile.waitForTimeout(1200);await mobile.mouse.up();
    await mobile.waitForTimeout(150);
    assert.equal(await mobile.locator('#interact').textContent(),'Conversar com Davi');
    await mobile.locator('#interact').click();await assertPanel(mobile,'Davi');
    await mobile.screenshot({path:'/tmp/portao-game-phone.png'});
    assert(await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    const panelRect=await mobile.locator('#panel').boundingBox();assert(panelRect.x>=0&&panelRect.x+panelRect.width<=390);
    await close(mobile);await mobile.locator('#pause').click();
    await mobile.getByRole('button',{name:'Modo sem movimento',exact:true}).click();
    await mobile.getByRole('button',{name:'Esperar a carona',exact:true}).click();
    await mobile.locator('#wait-forward').click();
    await assertPanel(mobile,'mesmo pátio');
    assert.deepEqual(mobileErrors,[]);
    console.log('Phone: on-screen movement reaches an NPC, dialogue fits, alternate controls preserve progression.');
    await mobile.close();

    const landscape=await browser.newPage({viewport:{width:844,height:390},hasTouch:true,isMobile:true});
    await start(landscape);await landscape.locator('#pause').click();
    assert(await landscape.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    const bounds=await landscape.locator('#panel').boundingBox();assert(bounds.y>=0&&bounds.y+bounds.height<=391);
    console.log('Landscape phone: scene and pause controls fit.');await landscape.close();

    const fallback=await browser.newPage();
    await fallback.route('**/world.mjs',route=>route.abort());await fallback.goto(gameURL);
    await fallback.locator('#fallback').waitFor({state:'visible'});await fallback.locator('#fallback-reading').click();
    await fallback.getByRole('button',{name:'Conversar com Lia',exact:true}).click();
    await assertPanel(fallback,'Lia');await close(fallback);
    await fallback.getByRole('button',{name:'Sair pelo portão',exact:true}).click();
    await fallback.getByRole('button',{name:'Ainda não sei',exact:true}).click();
    await fallback.locator('#open-documents').click();await assertPanel(fallback,'Antes da suspeita');
    console.log('No 3D: explicit accessible alternative retains conversations and documents.');await fallback.close();

    const failed=await browser.newPage();
    await failed.route('**/curiosidades.json',route=>route.fulfill({status:503,body:'Unavailable'}));
    await failed.goto(gameURL);await failed.locator('#start-sources').click();
    await failed.getByRole('button',{name:'Abrir o epílogo documental',exact:true}).click();
    for(let i=0;i<3;i++)await failed.locator('#next-document').click();
    await failed.waitForFunction(()=>document.querySelector('#panel-body').textContent.includes('não puderam ser carregados'));
    assert(! (await failed.locator('#panel-body').textContent()).includes('79,1%'));
    await failed.unroute('**/curiosidades.json');
    await failed.getByRole('button',{name:'← Documento anterior',exact:true}).click();
    await failed.locator('#next-document').click();await failed.locator('.records-toggle').waitFor();
    console.log('Evidence failure: no invented replacement; revisiting can retry successfully.');await failed.close();

    for(const [pattern,body] of [['**/curiosidades.json','{}'],['**/curiosidades.json',JSON.stringify({itens:[{id:'stf',certo:true}]})],['**/71072-0001.json','{}']]) {
      const malformed=await browser.newPage();const malformedErrors=[];malformed.on('pageerror',error=>malformedErrors.push(error.message));
      await malformed.route(pattern,route=>route.fulfill({status:200,contentType:'application/json',body}));
      await malformed.goto(gameURL);await malformed.locator('#start-sources').click();
      await malformed.getByRole('button',{name:'Abrir o epílogo documental',exact:true}).click();
      for(let i=0;i<3;i++)await malformed.locator('#next-document').click();
      await malformed.locator('#next-document').waitFor();await malformed.locator('#next-document').click();
      await assertPanel(malformed,'Uma declaração não substitui');assert.deepEqual(malformedErrors,[]);await malformed.close();
    }
    console.log('Malformed JSON shapes: source links and the final document remain accessible.');

    const lost=await browser.newPage();await start(lost);
    await lost.evaluate(()=>document.querySelector('#world canvas').getContext('webgl2').getExtension('WEBGL_lose_context').loseContext());
    await lost.locator('#fallback').waitFor({state:'visible'});await lost.keyboard.press('e');
    assert.equal(await lost.locator('#panel').isVisible(),false);
    await lost.locator('#fallback-reading').click();await assertPanel(lost,'mesmo pátio');await lost.close();
    console.log('Lost WebGL context: stale proximity controls stop; accessible mode remains usable.');

    const noJS=await browser.newPage({javaScriptEnabled:false});await noJS.goto(gameURL);
    assert(await noJS.locator('.no-js').isVisible());console.log('No JavaScript: source access remains available.');await noJS.close();
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
