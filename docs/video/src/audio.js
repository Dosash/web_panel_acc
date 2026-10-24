"use strict";
/* Музыка и звуковой дизайн демо-ролика: Web Audio, offline-рендер в WAV. Все события берутся из DEMO.TL,
   поэтому звук и картинка идут по одному таймлайну. 100 BPM: такт 2,4 с — границы сцен лежат на тактах. */
async function renderAudio(dur = DEMO.DUR, sr = 48000) {
  const TL = DEMO.TL, ctx = new OfflineAudioContext(2, Math.ceil(sr * dur), sr);
  const BEAT = .6, BAR = 2.4, mtof = n => 440 * Math.pow(2, (n - 69) / 12);
  // --- шины ---
  const comp = ctx.createDynamicsCompressor(); comp.threshold.value = -12; comp.knee.value = 10; comp.ratio.value = 3.5; comp.attack.value = .004; comp.release.value = .18;
  const master = ctx.createGain(); master.gain.value = .66; master.connect(comp).connect(ctx.destination);
  master.gain.setValueAtTime(.66, dur - .5); master.gain.linearRampToValueAtTime(0, dur - .02);
  const music = ctx.createGain(); music.gain.value = .6; music.connect(master);
  const sfx = ctx.createGain(); sfx.gain.value = 1; sfx.connect(master);
  const lcg = s => () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296 * 2 - 1; };
  const rev = ctx.createConvolver(); {
    const len = sr * 2.6, b = ctx.createBuffer(2, len, sr);
    for (let ch = 0; ch < 2; ch++) { const d = b.getChannelData(ch), r = lcg(77 + ch); for (let i = 0; i < len; i++) d[i] = r() * Math.pow(1 - i / len, 3.2); }
    rev.buffer = b;
  }
  const revOut = ctx.createGain(); revOut.gain.value = .8; rev.connect(revOut).connect(master);
  const send = (node, amt) => { const g = ctx.createGain(); g.gain.value = amt; node.connect(g).connect(rev); };
  const noiseBuf = (() => { const b = ctx.createBuffer(1, sr * 2, sr), d = b.getChannelData(0), r = lcg(42); for (let i = 0; i < d.length; i++) d[i] = r(); return b; })();
  const noise = (t, d) => { const s = ctx.createBufferSource(); s.buffer = noiseBuf; s.loop = true; s.start(t); s.stop(t + d + .05); return s; };
  const osc = (type, f, t, d, det = 0) => { const o = ctx.createOscillator(); o.type = type; o.frequency.value = f; o.detune.value = det; o.start(t); o.stop(t + d + .05); return o; };
  const gainAt = (t, a, peak, hold, r, dest) => { const g = ctx.createGain(); g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(peak, t + a); g.gain.setValueAtTime(peak, t + a + hold); g.gain.exponentialRampToValueAtTime(.0005, t + a + hold + r); g.connect(dest); return g; };
  const filt = (type, f, q = 1) => { const x = ctx.createBiquadFilter(); x.type = type; x.frequency.value = f; x.Q.value = q; return x; };
  const panner = v => { const p = ctx.createStereoPanner(); p.pan.value = v; return p; };

  // ================= музыка =================
  const CH = { Dm7: [50, 53, 57, 60, 64], Bb: [46, 50, 53, 57, 60], F: [53, 57, 60, 64, 67], C9: [48, 52, 55, 62, 67], Fin: [41, 53, 57, 60, 64, 69] };
  const BARS = ["Dm7", "Bb", "Dm7", "Bb", "F", "C9", "Dm7", "Bb", "F", "C9", "Dm7", "Bb", "F", "Bb", "C9", "F", "Dm7", "Bb", "Fin"];
  const drumsOn = t => (t >= 4.8 && t < 31.2) || (t >= 33.6 && t < 40.8);
  // пэд
  const padLP = filt("lowpass", 760, .7); padLP.connect(music); send(padLP, .4);
  padLP.frequency.setValueAtTime(760, 0); padLP.frequency.setValueAtTime(760, 31.2); padLP.frequency.exponentialRampToValueAtTime(2600, 31.85); padLP.frequency.exponentialRampToValueAtTime(900, 34); padLP.frequency.setValueAtTime(900, 43.2); padLP.frequency.exponentialRampToValueAtTime(1800, 44.4);
  BARS.forEach((name, b) => {
    const t0 = b * BAR, last = b === BARS.length - 1, len = last ? dur - t0 : BAR;
    const lvl = b < 2 ? .03 : b === 13 || b === 14 ? .045 : .036;
    CH[name].forEach((n, i) => {
      [-7, 7].forEach(det => {
        const o = osc("sawtooth", mtof(n), t0, len + .9, det + (i - 2) * 2);
        o.connect(gainAt(t0, .55, lvl, len - .2, last ? 1.4 : .7, padLP));
      });
    });
  });
  // арпеджио (16-е): плоский перебор по тонам аккорда, через задержку
  const dly = ctx.createDelay(1); dly.delayTime.value = .45; const dlyFb = ctx.createGain(); dlyFb.gain.value = .36; const dlyLP = filt("lowpass", 2400);
  dly.connect(dlyLP).connect(dlyFb).connect(dly); const dlyOut = ctx.createGain(); dlyOut.gain.value = .35; dlyLP.connect(dlyOut).connect(music);
  const arpBus = ctx.createGain(); arpBus.gain.value = 1; arpBus.connect(music); arpBus.connect(dly); send(arpBus, .18);
  const arpOn = t => (t >= 2.4 && t < 31.2) || (t >= 33.6 && t < 40.8);
  BARS.forEach((name, b) => {
    const c = CH[name], pat = [c[1] + 12, c[3] + 12, c[2] + 12, c[4] + 12, c[1] + 24, c[3] + 12, c[2] + 24, c[4] + 12];
    for (let k = 0; k < 16; k++) {
      const t = b * BAR + k * .15; if (!arpOn(t)) continue;
      const vel = (t < 4.8 ? .45 : 1) * (k % 4 === 0 ? 1 : .72) * (t >= 36 ? Math.max(.2, 1 - (t - 36) / 5) : 1);
      const o = osc("triangle", mtof(pat[k % 8]), t, .35); const lp = filt("lowpass", 3800, 1.2);
      lp.frequency.setValueAtTime(3800, t); lp.frequency.exponentialRampToValueAtTime(600, t + .18);
      o.connect(lp).connect(gainAt(t, .004, .11 * vel, 0, .28, panner(k % 2 ? .25 : -.25))).connect(arpBus);
    }
  });
  // бас
  const bassOn = t => (t >= 4.8 && t < 31.2) || (t >= 33.6 && t < 40.8);
  BARS.forEach((name, b) => {
    const root = CH[name][0] - 12 + (name === "Fin" ? 12 : 0);
    [0, 1.5, 2.5, 3].forEach((beat, i) => {
      const t = b * BAR + beat * BEAT; if (!bassOn(t)) return;
      const d = i === 1 ? .32 : .42;
      const o1 = osc("sine", mtof(root), t, d), o2 = osc("sawtooth", mtof(root), t, d); const lp = filt("lowpass", 420, .8);
      o1.connect(gainAt(t, .01, .26, d * .6, .12, music)); o2.connect(lp).connect(gainAt(t, .01, .09, d * .5, .12, music));
    });
  });
  // ударные
  const kick = (t, lvl = .85) => {
    const o = osc("sine", 165, t, .45); o.frequency.setValueAtTime(165, t); o.frequency.exponentialRampToValueAtTime(44, t + .09);
    o.connect(gainAt(t, .003, lvl, .02, .3, music));
    const n = noise(t, .02); n.connect(filt("highpass", 1500)).connect(gainAt(t, .001, .18, 0, .02, music));
  };
  const hat = (t, lvl) => { const n = noise(t, .05); n.connect(filt("highpass", 6500, .7)).connect(gainAt(t, .002, lvl, 0, .045, panner(.18))).connect(music); };
  const clap = (t) => { [0, .011, .024].forEach((o, i) => { const n = noise(t + o, .2); n.connect(filt("bandpass", 1700, 1.1)).connect(gainAt(t + o, .002, i === 2 ? .17 : .09, 0, i === 2 ? .17 : .03, music)); }); const n = noise(t, .25); n.connect(filt("bandpass", 1700, 1)); send(n, .25); };
  for (let t = 4.8; t < 44; t += BEAT) {
    const beat = Math.round((t % BAR) / BEAT) % 4;
    if (drumsOn(t)) {
      if (!(t >= 36 && beat % 2)) kick(t, t >= 36 ? .6 : .72);
      if ((beat === 1 || beat === 3) && t >= 7.2 && t < 36) clap(t);
      hat(t, .03); hat(t + BEAT / 2, .05);
    }
  }
  // мелодия: мягкий синус с вибрато, фразы по 2 такта
  const lead = (t0, phrase, lvl = .07) => phrase.forEach(([beat, n, len]) => {
    const t = t0 + beat * BEAT, d = len * BEAT, f = mtof(n);
    const o = osc("sine", f, t, d), o2 = osc("triangle", f, t, d, 4), lp = filt("lowpass", 2200);
    const vib = osc("sine", 5.5, t, d); const vg = ctx.createGain(); vg.gain.setValueAtTime(0, t); vg.gain.linearRampToValueAtTime(f * .006, t + .25); vib.connect(vg); vg.connect(o.frequency); vg.connect(o2.frequency);
    const g = gainAt(t, .03, lvl, Math.max(0, d - .25), .35, lp); o.connect(g); const g2 = gainAt(t, .03, lvl * .35, Math.max(0, d - .25), .35, lp); o2.connect(g2);
    lp.connect(music); lp.connect(dly); send(lp, .5);
  });
  const P1 = [[0, 69, .5], [.5, 72, .5], [1, 74, .9], [2.5, 77, .5], [3, 76, .5], [3.5, 74, 1.2], [5, 72, .5], [5.5, 69, 1.6]];
  const P2 = [[0, 72, .5], [.5, 74, .5], [1, 76, .9], [2.5, 77, .5], [3, 79, .5], [3.5, 76, 1.2], [5, 74, .5], [5.5, 72, 1.6]];
  lead(4.8, P1); lead(9.6, P2); lead(14.4, P1); lead(19.2, P2, .06); lead(24, P1); lead(28.8, [[0, 76, .5], [.5, 77, .5], [1, 79, 1.4]], .07);
  lead(33.6, P2, .065); lead(38.4, [[0, 69, .5], [.5, 72, .5], [1, 74, .9], [2.5, 77, .5], [3, 76, .5], [3.5, 81, 2.2]], .08);
  // финальный аккорд: светлый слой сверху
  CH.Fin.forEach((n, i) => { const o = osc("triangle", mtof(n + 12), 43.2, 1.3, (i - 2) * 3); const g = gainAt(43.2, .02, .05, .4, .8, music); o.connect(g); send(g, .7); });

  // ================= звуковой дизайн =================
  const whoosh = (t, d = .5, dir = 1, lvl = .4, up = true) => {
    const n = noise(t, d), bp = filt("bandpass", 600, 1.1);
    bp.frequency.setValueAtTime(up ? 220 : 3200, t); bp.frequency.exponentialRampToValueAtTime(up ? 3200 : 220, t + d);
    const g = ctx.createGain(); g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(lvl, t + d * .45); g.gain.exponentialRampToValueAtTime(.0005, t + d);
    const p = ctx.createStereoPanner(); p.pan.setValueAtTime(-.6 * dir, t); p.pan.linearRampToValueAtTime(.6 * dir, t + d);
    n.connect(bp).connect(g).connect(p).connect(sfx); send(g, .3);
  };
  const impact = (t, lvl = .9) => {
    const o = osc("sine", 120, t, .7); o.frequency.setValueAtTime(120, t); o.frequency.exponentialRampToValueAtTime(36, t + .16);
    o.connect(gainAt(t, .004, lvl, .05, .55, sfx));
    const n = noise(t, .3); n.connect(filt("lowpass", 900)).connect(gainAt(t, .002, .3 * lvl, 0, .22, sfx));
    const n2 = noise(t, .6); n2.connect(filt("bandpass", 2500, .8)); send(n2, .35 * lvl);
  };
  const click = (t, lvl = .5) => {
    const n = noise(t, .02); n.connect(filt("highpass", 2800)).connect(gainAt(t, .001, lvl, 0, .014, sfx));
    const o = osc("sine", 1900, t, .05); o.connect(gainAt(t, .001, lvl * .35, 0, .035, sfx));
    const n2 = noise(t + .07, .02); n2.connect(filt("highpass", 2200)).connect(gainAt(t + .07, .001, lvl * .5, 0, .012, sfx));   // отпускание кнопки
  };
  const tick = (t, lvl = .22, i = 0) => {
    const n = noise(t, .015); n.connect(filt("bandpass", 3600 + (i % 5) * 260, 1.6)).connect(gainAt(t, .001, lvl, 0, .012, sfx));
    const o = osc("sine", 2100 + (i % 7) * 90, t, .04); o.connect(gainAt(t, .001, lvl * .25, 0, .03, sfx));
  };
  const pop = (t, f = 600, lvl = .35) => { const o = osc("sine", f, t, .25); o.frequency.setValueAtTime(f * 1.6, t); o.frequency.exponentialRampToValueAtTime(f, t + .06); o.connect(gainAt(t, .003, lvl, 0, .16, sfx)); };
  const chime = (t, notes = [1318, 1760], lvl = .2, gap = .07) => notes.forEach((f, i) => { const o = osc("sine", f, t + i * gap, .7); const g = gainAt(t + i * gap, .004, lvl, .05, .5, sfx); o.connect(g); send(g, .6); });
  const shimmer = (t, lvl = .08) => { const o = osc("sine", 2400, t, .5); o.frequency.exponentialRampToValueAtTime(3400, t + .3); const g = gainAt(t, .01, lvl, 0, .4, sfx); o.connect(g); send(g, .8); };
  const sendSfx = t => { const o = osc("sine", 880, t, .3); o.frequency.exponentialRampToValueAtTime(1320, t + .09); o.connect(gainAt(t, .004, .22, 0, .18, sfx)); const o2 = osc("triangle", 1760, t + .09, .4); const g = gainAt(t + .09, .004, .14, 0, .3, sfx); o2.connect(g); send(g, .5); whoosh(t, .28, 1, .18); };
  const riser = (t0, t1) => {
    const n = noise(t0, t1 - t0), bp = filt("bandpass", 400, 1.4); bp.frequency.setValueAtTime(400, t0); bp.frequency.exponentialRampToValueAtTime(5200, t1);
    const g = ctx.createGain(); g.gain.setValueAtTime(0, t0); g.gain.linearRampToValueAtTime(.42, t1); g.gain.setValueAtTime(0, t1 + .01);
    n.connect(bp).connect(g).connect(sfx); send(g, .4);
    const o = osc("sine", 180, t0, t1 - t0); o.frequency.exponentialRampToValueAtTime(820, t1); o.connect(gainAt(t0, t1 - t0 - .05, .12, 0, .05, sfx));
  };

  // интро: окна появляются, слова, слёт в рейку, раскрытие панели
  [0, 1, 2, 3, 4].forEach(i => shimmer(.35 + i * .28, .07));
  [1.9, 2.12, 2.34].forEach(t => pop(t, 380, .22)); [3.55, 3.67, 3.79].forEach(t => pop(t, 520, .22));
  whoosh(TL.flyStart, 1.25, 1, .45, true); impact(TL.panel, .9); whoosh(TL.panel + .05, .7, -1, .35, false);
  for (let i = 0; i < 11; i++) tick(TL.panel + .25 + i * .055, .07, i);
  // клики курсора и реакции интерфейса
  DEMO.CLICKS.forEach(t => click(t));
  for (let i = 0; i < 4; i++) tick(TL.clickAcc + .05 + i * .055, .07, i);
  pop(TL.newMsg, 900, .3); chime(TL.newMsg + .04, [1318, 1760], .18);
  whoosh(TL.chatOpen, .4, 1, .22); for (let i = 0; i < 8; i++) tick(TL.chatOpen + i * .05, .05, i);
  DEMO.CHAR_T.forEach((t, i) => tick(t, .2, i));
  sendSfx(TL.sent);
  for (let i = 0; i < 11; i++) tick(TL.clickAll + .05 + i * .055, .06, i);
  whoosh(TL.chOpen, .45, 1, .22); for (let i = 0; i < 5; i++) tick(TL.chOpen + i * .05, .05, i);
  pop(TL.overlayOpen, 500, .3); chime(TL.overlayLoaded, [1568, 2093], .13); for (let i = 0; i < 4; i++) pop(TL.overlayLoaded + .05 + i * .09, 700 + i * 80, .12);
  whoosh(TL.overlayClose, .3, -1, .18, false);
  whoosh(TL.botOpen, .6, 1, .4); for (let i = 0; i < 5; i++) pop(TL.botOpen + .3 + i * .09, 520 + i * 70, .22);
  for (let i = 0; i < 16; i++) tick(TL.botOpen + .45 + i * .07, .05, i);
  for (let i = 0; i < 2; i++) pop(TL.botOpen + .75 + i * .12, 420, .18);
  // смена темы: подъём → щелчок → вспышка
  riser(31.2, TL.themeClick); impact(TL.themeClick + .04, .7); shimmer(TL.themeClick + .05, .14); chime(TL.themeClick + .1, [1760, 2349, 2637], .12, .06);
  whoosh(TL.phone, .7, -1, .4); for (let i = 0; i < 7; i++) tick(TL.phone + .5 + i * .06, .06, i);
  // финал
  whoosh(TL.outro, .9, 1, .45, false); pop(TL.outro + 1.2, 380, .4); shimmer(TL.outro + 1.25, .12);
  for (let i = 0; i < 8; i++) { const t = 37.0 + i * .07; pop(t, 700 + i * 60, .16); }
  whoosh(38.3, .35, 1, .16); pop(39.3, 460, .28);
  DEMO.TERM_T.forEach((t, i) => tick(t, .22, i));
  click(41.3, .45); chime(41.4, [1047, 1568, 2093], .16, .07);
  impact(43.2, 1.0); shimmer(43.25, .14);

  // ================= рендер в WAV =================
  const buf = await ctx.startRendering();
  const L = buf.getChannelData(0), R = buf.getChannelData(1), n = buf.length;
  const out = new DataView(new ArrayBuffer(44 + n * 4));
  const str = (o, s) => { for (let i = 0; i < s.length; i++) out.setUint8(o + i, s.charCodeAt(i)); };
  str(0, "RIFF"); out.setUint32(4, 36 + n * 4, true); str(8, "WAVE"); str(12, "fmt "); out.setUint32(16, 16, true); out.setUint16(20, 1, true); out.setUint16(22, 2, true);
  out.setUint32(24, sr, true); out.setUint32(28, sr * 4, true); out.setUint16(32, 4, true); out.setUint16(34, 16, true); str(36, "data"); out.setUint32(40, n * 4, true);
  let peak = 0, sq = 0;
  for (let i = 0; i < n; i++) {
    const l = Math.max(-1, Math.min(1, L[i])), r = Math.max(-1, Math.min(1, R[i]));
    peak = Math.max(peak, Math.abs(L[i]), Math.abs(R[i])); sq += l * l + r * r;
    out.setInt16(44 + i * 4, l * 32767, true); out.setInt16(46 + i * 4, r * 32767, true);
  }
  const bytes = new Uint8Array(out.buffer); let bin = ""; for (let i = 0; i < bytes.length; i += 8192) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 8192));
  return { wav: btoa(bin), peak: +peak.toFixed(3), rms: +Math.sqrt(sq / (2 * n)).toFixed(4), seconds: +(n / sr).toFixed(3) };
}
window.renderAudio = renderAudio;
