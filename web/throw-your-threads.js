const canvas = document.querySelector('#world');
const ctx = canvas.getContext('2d');
const game = document.querySelector('#game');
const intro = document.querySelector('#intro');
const play = document.querySelector('#play');
const fullscreen = document.querySelector('#fullscreen');
const sound = document.querySelector('#sound');
const status = document.querySelector('#status');
const sceneLabel = document.querySelector('#scene-label');
const chapterCard = document.querySelector('#chapter-card');
const chapterTitle = document.querySelector('#chapter-title');
const chapterCopy = document.querySelector('#chapter-copy');
const sceneButtons = [...document.querySelectorAll('[data-scene]')];

const scenes = {
  woods: { label: 'THE WOODS REMEMBER', title: 'The Woods Remember', copy: 'Something moves between the pines. Keep the red thread taut.', palette: ['#070c0a', '#15261c', '#4b291d'] },
  cinema: { label: 'THE EMPTY CINEMA', title: 'The Empty Cinema', copy: 'The projector still knows your name. Do not sit in the front row.', palette: ['#0e080a', '#34171a', '#a25532'] },
  attic: { label: 'THE THREAD ROOM', title: 'The Thread Room', copy: 'Every strand leads somewhere. Do not cut the one that breathes.', palette: ['#120a08', '#3a2115', '#9a5530'] },
};
const sceneKeys = Object.keys(scenes);
let activeScene = 'woods';
let playing = false;
let audioOn = false;
let audioContext;
let drone;
let droneGain;
let frame = 0;
let width = 0;
let height = 0;
let dpr = 1;
let pointer = { x: .5, y: .5 };
let particles = [];

const rand = (min, max) => min + Math.random() * (max - min);
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

function resize() {
  dpr = Math.min(window.devicePixelRatio || 1, 2);
  width = canvas.clientWidth;
  height = canvas.clientHeight;
  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  particles = Array.from({ length: Math.max(70, Math.floor(width / 13)) }, () => ({ x: rand(0, width), y: rand(0, height), r: rand(.3, 2.2), speed: rand(.08, .5), drift: rand(-.18, .18), alpha: rand(.12, .7) }));
}

function gradient() {
  const [dark, mid, glow] = scenes[activeScene].palette;
  const sky = ctx.createLinearGradient(0, 0, 0, height);
  sky.addColorStop(0, dark); sky.addColorStop(.55, mid); sky.addColorStop(1, '#080505');
  ctx.fillStyle = sky; ctx.fillRect(0, 0, width, height);
  const light = ctx.createRadialGradient(width * (.52 + (pointer.x - .5) * .08), height * (.32 + (pointer.y - .5) * .08), 0, width * .52, height * .36, width * .7);
  light.addColorStop(0, `${glow}66`); light.addColorStop(.32, `${glow}18`); light.addColorStop(1, 'transparent');
  ctx.fillStyle = light; ctx.fillRect(0, 0, width, height);
}

function drawWoods(t) {
  const horizon = height * .62;
  ctx.fillStyle = '#080d0b'; ctx.fillRect(0, horizon, width, height - horizon);
  for (let i = -2; i < 19; i += 1) {
    const x = i * (width / 17) + Math.sin(i * 2.3) * 34 + (pointer.x - .5) * -18;
    const h = height * (.25 + (i % 4) * .07);
    ctx.fillStyle = i % 3 === 0 ? '#0b1713' : '#13231a';
    ctx.beginPath(); ctx.moveTo(x, horizon + 12); ctx.lineTo(x + 25, horizon - h); ctx.lineTo(x + 50, horizon + 12); ctx.closePath(); ctx.fill();
    ctx.fillStyle = '#0a100d'; ctx.fillRect(x + 22, horizon - h, 7, h + 35);
  }
  ctx.strokeStyle = '#ae5334'; ctx.lineWidth = 1.5; ctx.globalAlpha = .7;
  ctx.beginPath(); ctx.moveTo(width * .08, height * .25 + Math.sin(t * .001) * 8); ctx.bezierCurveTo(width * .35, height * .44, width * .58, height * .12, width * .96, height * .33); ctx.stroke(); ctx.globalAlpha = 1;
  drawCharacter(width * .53 + Math.sin(t * .0014) * 8, horizon + 15, .95, '#120b0a');
}

function drawCinema(t) {
  const floor = height * .69;
  ctx.fillStyle = '#180b0d'; ctx.fillRect(0, floor, width, height - floor);
  ctx.fillStyle = '#100708'; ctx.fillRect(width * .12, height * .16, width * .76, height * .55);
  ctx.strokeStyle = '#8f4430'; ctx.lineWidth = 2; ctx.strokeRect(width * .13, height * .17, width * .74, height * .52);
  ctx.fillStyle = '#d58245'; ctx.globalAlpha = .75; ctx.beginPath(); ctx.arc(width * .5, height * .4, height * .18, 0, Math.PI * 2); ctx.fill(); ctx.globalAlpha = 1;
  ctx.fillStyle = '#080506'; ctx.beginPath(); ctx.moveTo(width * .33, floor); ctx.lineTo(width * .39, floor - 60); ctx.lineTo(width * .46, floor); ctx.lineTo(width * .55, floor); ctx.lineTo(width * .61, floor - 60); ctx.lineTo(width * .67, floor); ctx.closePath(); ctx.fill();
  for (let i = 0; i < 7; i += 1) { ctx.fillStyle = i % 2 ? '#301216' : '#421a18'; ctx.fillRect(width * .1 + i * width * .12, floor + 15, width * .08, 18); }
  ctx.globalAlpha = .2; ctx.fillStyle = '#f2c06d'; ctx.fillRect(width * .5, height * .25, Math.sin(t * .004) * 30, height * .45); ctx.globalAlpha = 1;
  drawCharacter(width * .5, floor - 2, 1.2, '#080405');
}

function drawAttic(t) {
  ctx.strokeStyle = '#6e3d29'; ctx.lineWidth = 2;
  for (let x = -width; x < width * 2; x += 80) { ctx.beginPath(); ctx.moveTo(width * .5, 0); ctx.lineTo(x, height); ctx.stroke(); }
  ctx.fillStyle = '#0d0706'; ctx.fillRect(0, height * .78, width, height * .22);
  const cx = width * .5 + Math.sin(t * .0007) * 16; const cy = height * .49;
  ctx.strokeStyle = '#d66e3d'; ctx.lineWidth = 2; ctx.globalAlpha = .8;
  for (let i = 0; i < 17; i += 1) { const angle = i * .63 + t * .0002; ctx.beginPath(); ctx.moveTo(cx, cy); ctx.bezierCurveTo(cx + Math.cos(angle) * width * .18, cy + Math.sin(angle) * height * .18, cx + Math.cos(angle + .4) * width * .45, cy + Math.sin(angle + .4) * height * .42, cx + Math.cos(angle) * width * .7, cy + Math.sin(angle) * height * .64); ctx.stroke(); }
  ctx.globalAlpha = 1; drawCharacter(cx, cy + 40, 1.1, '#0b0605');
}

function drawCharacter(x, y, scale, color) {
  ctx.save(); ctx.translate(x, y); ctx.scale(scale, scale); ctx.fillStyle = color;
  ctx.beginPath(); ctx.ellipse(0, -65, 18, 28, 0, 0, Math.PI * 2); ctx.fill();
  ctx.beginPath(); ctx.moveTo(-18, -40); ctx.quadraticCurveTo(-42, 5, -30, 55); ctx.lineTo(30, 55); ctx.quadraticCurveTo(42, 5, 18, -40); ctx.closePath(); ctx.fill();
  ctx.strokeStyle = '#ca6c3a'; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(-8, -74); ctx.lineTo(34, -88); ctx.stroke();
  ctx.restore();
}

function drawParticles(t) {
  ctx.fillStyle = '#f2c27a';
  particles.forEach((particle) => { particle.y -= particle.speed; particle.x += particle.drift + Math.sin(t * .001 + particle.y) * .03; if (particle.y < -5) particle.y = height + 5; if (particle.x < -5) particle.x = width + 5; if (particle.x > width + 5) particle.x = -5; ctx.globalAlpha = particle.alpha * (.6 + Math.sin(t * .002 + particle.x) * .4); ctx.beginPath(); ctx.arc(particle.x, particle.y, particle.r, 0, Math.PI * 2); ctx.fill(); }); ctx.globalAlpha = 1;
}

function render(time = 0) {
  frame = time; gradient();
  if (activeScene === 'woods') drawWoods(time); else if (activeScene === 'cinema') drawCinema(time); else drawAttic(time);
  drawParticles(time);
  if (playing) requestAnimationFrame(render);
}

async function enterFullscreen() {
  if (document.fullscreenElement) return true;
  if (!document.fullscreenEnabled || !game.requestFullscreen) return false;
  try {
    await game.requestFullscreen({ navigationUI: 'hide' });
    await new Promise((resolve) => requestAnimationFrame(resolve));
    return Boolean(document.fullscreenElement || game.matches(':fullscreen'));
  } catch { return false; }
}

async function startGame() {
  playing = true; resize(); requestAnimationFrame(render); intro.classList.add('is-leaving');
  const full = await enterFullscreen();
  status.textContent = full ? 'Immersive mode enabled.' : 'Fullscreen was unavailable; the game continues in the current window.';
  document.body.classList.add('is-playing');
}

function setScene(name) {
  if (!scenes[name] || name === activeScene) return;
  activeScene = name; sceneLabel.textContent = scenes[name].label;
  sceneButtons.forEach((button) => button.classList.toggle('is-active', button.dataset.scene === name));
  chapterTitle.textContent = scenes[name].title; chapterCopy.textContent = scenes[name].copy; chapterCard.hidden = false;
  window.clearTimeout(setScene.timer); setScene.timer = window.setTimeout(() => { chapterCard.hidden = true; }, 3500);
  if (!playing) { resize(); render(frame); }
}

play.addEventListener('click', startGame);
fullscreen.addEventListener('click', async () => { const full = await enterFullscreen(); status.textContent = full ? 'Immersive mode enabled.' : 'Fullscreen was unavailable in this browser.'; });
sound.addEventListener('click', async () => {
  audioOn = !audioOn;
  if (audioOn) {
    try {
      audioContext ??= new AudioContext();
      await audioContext.resume();
      drone = audioContext.createOscillator();
      droneGain = audioContext.createGain();
      drone.type = 'sine'; drone.frequency.value = 58;
      droneGain.gain.value = .018; drone.connect(droneGain).connect(audioContext.destination); drone.start();
    } catch {
      audioOn = false;
      status.textContent = 'Sound is unavailable in this browser.';
    }
  } else if (drone) {
    drone.stop(); drone.disconnect(); drone = undefined;
  }
  sound.setAttribute('aria-pressed', String(audioOn)); sound.textContent = `Sound: ${audioOn ? 'on' : 'off'}`; status.textContent = audioOn ? 'The room is humming.' : 'Sound muted.';
});
sceneButtons.forEach((button) => button.addEventListener('click', () => setScene(button.dataset.scene)));
window.addEventListener('resize', () => { resize(); if (!playing) render(frame); });
window.addEventListener('pointermove', (event) => { pointer.x = clamp(event.clientX / window.innerWidth, 0, 1); pointer.y = clamp(event.clientY / window.innerHeight, 0, 1); });
window.addEventListener('keydown', (event) => { if (event.key.toLowerCase() === 'a' || event.key === 'ArrowLeft') setScene(sceneKeys[(sceneKeys.indexOf(activeScene) + sceneKeys.length - 1) % sceneKeys.length]); if (event.key.toLowerCase() === 'd' || event.key === 'ArrowRight') setScene(sceneKeys[(sceneKeys.indexOf(activeScene) + 1) % sceneKeys.length]); if (event.key === 'Escape' && document.fullscreenElement) document.exitFullscreen(); });
document.addEventListener('fullscreenchange', () => { fullscreen.textContent = document.fullscreenElement ? 'Exit fullscreen' : 'Fullscreen'; resize(); });

resize(); render(0);
