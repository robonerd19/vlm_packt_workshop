const form = document.querySelector('#instruction');
const send = document.querySelector('#send');
const progress = document.querySelector('#progress');
const response = document.querySelector('#response');
const timing = document.querySelector('#timing') || document.createElement('p');
// Support an already-cached HTML template when updating a running demo.
if (!timing.id) {
  timing.id = 'timing';
  timing.hidden = true;
  timing.setAttribute('role', 'timer');
  timing.setAttribute('aria-live', 'off');
  progress.insertAdjacentElement('afterend', timing);
}
let phase = null;
let phaseStarted = 0;
let timer = null;
let modelTime = {thinking: 0, confirming: 0};

function observation(text) {
  const list = document.querySelector('#observations');
  const item = document.createElement('li');
  item.textContent = text;
  list.append(item);
  // Retain a useful history without allowing an unbounded page.
  while (list.children.length > 24) list.removeChild(list.firstElementChild);
}

function duration(milliseconds) {
  const seconds = Math.floor(milliseconds / 1000);
  return `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`;
}

function renderTiming() {
  const elapsed = phase ? performance.now() - phaseStarted : 0;
  const total = modelTime.thinking + modelTime.confirming + elapsed;
  timing.hidden = false;
  timing.textContent = phase
    ? `${phase === 'thinking' ? 'Thinking' : 'Confirming object'} · ${duration(elapsed)} elapsed · Model total ${duration(total)}`
    : `Model time ${duration(total)} · Thinking ${duration(modelTime.thinking)} · Confirmation ${duration(modelTime.confirming)}`;
}

function stopPhase() {
  if (phase) {
    modelTime[phase] += performance.now() - phaseStarted;
    phase = null;
    renderTiming();
  }
  clearInterval(timer);
  timer = null;
}

function updatePhase(state) {
  const next = ['thinking', 'confirming'].includes(state) ? state : null;
  if (next === phase) return; // Repeated feedback must not reset elapsed time.
  stopPhase();
  if (next) {
    phase = next;
    phaseStarted = performance.now();
    renderTiming();
    timer = setInterval(renderTiming, 250);
  }
}

function detection(text) {
  try {
    const data = JSON.parse(text);
    const box = document.querySelector('#box');
    if (!data.bbox) return;
    const [x1, y1, x2, y2] = data.bbox;
    for (const [name, value] of Object.entries({x: x1, y: y1, width: x2-x1, height: y2-y1, visibility: 'visible'})) {
      box.setAttribute(name, value);
    }
  } catch {}
}

async function status() {
  try {
    const r = await fetch('/status');
    const s = await r.json();
    document.querySelector('#readiness').textContent = s.ready
      ? 'Camera, model, transforms, and navigation ready.'
      : (s.reasons || ['Starting…']).join(' · ');
    document.querySelector('#target').textContent = s.target
      ? `Last target (${s.target.frame}): ${s.target.x.toFixed(2)}, ${s.target.y.toFixed(2)} m` : '';
    if (s.objects && s.objects.length) {
      document.querySelector('#objects').replaceChildren(...s.objects.map(o => {
        const item = document.createElement('li');
        const pick = document.createElement('button');
        pick.type = 'button';
        pick.textContent = `${o.label} · ${o.x.toFixed(1)}, ${o.y.toFixed(1)} m`;
        pick.addEventListener('click', () => { document.querySelector('#prompt').value = `go to the ${o.label}`; });
        item.append(pick);
        return item;
      }));
    }
  } catch {
    document.querySelector('#readiness').textContent = 'Application unavailable.';
  }
}
setInterval(status, 3000);
status();

form.addEventListener('submit', async e => {
  e.preventDefault();
  stopPhase();
  modelTime = {thinking: 0, confirming: 0};
  timing.hidden = true;
  timing.textContent = '';
  send.disabled = true;
  response.textContent = '';
  document.querySelector('#observations').replaceChildren();
  document.querySelector('#box').setAttribute('visibility', 'hidden');
  progress.textContent = 'Submitting…';
  try {
    const r = await fetch('/infer', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({prompt: document.querySelector('#prompt').value})
    });
    if (!r.ok) throw new Error((await r.json()).error);
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      let end;
      while ((end = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, end);
        buffer = buffer.slice(end+1);
        if (!line) continue;
        const event = JSON.parse(line);
        if (event.type === 'feedback') {
          updatePhase(event.status);
          if (['navigating', 'searching', 'searching_navigation', 'seeing', 'thinking', 'confirming'].includes(event.status)) {
            document.querySelector('#box').setAttribute('visibility', 'hidden');
          }
          const labels = {seeing: 'Inspecting frame', thinking: 'Thinking', confirming: 'Confirming object', searching: 'Searching', searching_navigation: 'Moving to search view', navigating: 'Navigating', validating: 'Validating detection'};
          progress.textContent = (labels[event.status] || event.status)
            + (['navigating', 'searching_navigation'].includes(event.status) ? ` · ${event.distance.toFixed(2)} m remaining` : '');
          if (event.status === 'seeing' && event.text) {
            observation(event.text);
          } else if (event.text) {
            response.textContent = event.text;
            detection(event.text);
          }
        } else if (event.type === 'done') {
          stopPhase();
          progress.textContent = event.success ? 'Navigation complete.' : 'Request ended.';
          response.textContent = (event.response || '') + '\n' + event.message;
        } else if (event.type === 'error') {
          throw new Error(event.message);
        }
      }
    }
  } catch (err) {
    progress.textContent = err.message;
  } finally {
    stopPhase();
    send.disabled = false;
    status();
  }
});

document.querySelector('#cancel').addEventListener('click', async () => {
  try {
    const r = await fetch('/cancel', {method: 'POST'});
    const s = await r.json();
    progress.textContent = s.cancellation_requested
      ? 'Cancellation requested; waiting for confirmation.' : 'No active request.';
  } catch {
    progress.textContent = 'Unable to request cancellation.';
  }
});
