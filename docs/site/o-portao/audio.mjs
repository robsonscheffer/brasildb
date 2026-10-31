// Original synthesized ambience. No recorded voices, film audio or external assets.
export function createAudio() {
  let context = null, master = null, enabled = false;
  function ensure() {
    if (context) return;
    const Audio = window.AudioContext || window.webkitAudioContext;
    if (!Audio) return;
    context = new Audio();
    master = context.createGain(); master.gain.value = .16; master.connect(context.destination);
    const buffer = context.createBuffer(1, context.sampleRate * 3, context.sampleRate);
    const data = buffer.getChannelData(0);
    let previous = 0;
    for (let i=0;i<data.length;i++) { previous=(previous+(Math.random()*2-1)*.018)/1.018;data[i]=previous*2.5; }
    const noise=context.createBufferSource();noise.buffer=buffer;noise.loop=true;
    const filter=context.createBiquadFilter();filter.type='lowpass';filter.frequency.value=650;
    const volume=context.createGain();volume.gain.value=.35;
    noise.connect(filter);filter.connect(volume);volume.connect(master);noise.start();
    // A quiet fan hum, rather than music that assigns guilt or reassurance.
    const fan=context.createOscillator();fan.type='sine';fan.frequency.value=92;
    const fanGain=context.createGain();fanGain.gain.value=.025;fan.connect(fanGain);fanGain.connect(master);fan.start();
  }
  async function setEnabled(value) {
    enabled=value;
    try { if(value){ensure();await context?.resume();}else await context?.suspend(); }
    catch { enabled=false; }
    return enabled && !!context;
  }
  function tone(frequency, duration, volume) {
    if(!enabled||!context||context.state!=='running')return;
    const now=context.currentTime, oscillator=context.createOscillator(), gain=context.createGain();
    oscillator.type='sine';oscillator.frequency.setValueAtTime(frequency,now);
    oscillator.frequency.exponentialRampToValueAtTime(frequency*.65,now+duration);
    gain.gain.setValueAtTime(volume,now);gain.gain.exponentialRampToValueAtTime(.001,now+duration);
    oscillator.connect(gain);gain.connect(master);oscillator.start(now);oscillator.stop(now+duration);
  }
  return {
    setEnabled,
    step:()=>tone(110,.055,.16),
    notify:()=>tone(640,.16,.12),
    suspend:()=>context?.suspend().catch(()=>{}),
    resume:()=>enabled?context?.resume().catch(()=>{}):null,
    dispose:()=>context?.close().catch(()=>{}),
  };
}
