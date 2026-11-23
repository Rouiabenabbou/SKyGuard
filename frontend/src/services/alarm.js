// Alarm sound in the dashboard when an attack is detected (also on a phone's browser).
// On by default. Made with the Web Audio API, so no sound file is needed. Browsers only
// allow sound after the first click on the page, which unlocks it automatically.
const KEY = "cybershield.alarm";
let ctx = null;
let playingUntil = 0;

export function alarmEnabled() {
  try {
    return localStorage.getItem(KEY) !== "off";
  } catch {
    return true;
  }
}

export function setAlarmEnabled(on) {
  try {
    localStorage.setItem(KEY, on ? "on" : "off");
  } catch {
    /* private mode: only for this page */
  }
  if (on) unlock();
}

function unlock() {
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) return null;
  if (!ctx) ctx = new AudioCtx();
  if (ctx.state === "suspended") ctx.resume();
  return ctx;
}

// A two-tone siren: `seconds` long, louder and faster for critical alerts.
export function playAlarm(severity = "high", seconds = 3) {
  if (!alarmEnabled()) return;
  const ac = unlock();
  if (!ac) return;
  const now = ac.currentTime;
  if (now < playingUntil) return; // already ringing
  playingUntil = now + seconds;
  const osc = ac.createOscillator();
  const gain = ac.createGain();
  osc.type = "square";
  const step = severity === "critical" ? 0.18 : 0.3;
  for (let t = 0; t < seconds; t += step * 2) {
    osc.frequency.setValueAtTime(880, now + t);
    osc.frequency.setValueAtTime(660, now + t + step);
  }
  gain.gain.setValueAtTime(0.0001, now);
  gain.gain.exponentialRampToValueAtTime(0.25, now + 0.05);
  gain.gain.setValueAtTime(0.25, now + seconds - 0.1);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + seconds);
  osc.connect(gain).connect(ac.destination);
  osc.start(now);
  osc.stop(now + seconds);
  if (navigator.vibrate) navigator.vibrate([400, 200, 400, 200, 400]); // phones (Android)
}

// The first click or key press anywhere on the page unlocks the sound.
if (typeof window !== "undefined") {
  const first = () => {
    if (alarmEnabled()) unlock();
  };
  window.addEventListener("pointerdown", first, { once: true });
  window.addEventListener("keydown", first, { once: true });
}
