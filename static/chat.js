const csrf = document.querySelector('meta[name=csrf-token]').content;
const log = document.getElementById('log');
const form = document.getElementById('form');
const input = document.getElementById('msg');
const lang = document.getElementById('lang');
let messages = [];

function add(role, text) {
  const d = document.createElement('div');
  d.className = 'bubble ' + role;
  d.textContent = text;
  log.appendChild(d);
  log.scrollTop = log.scrollHeight;
  return d;
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  add('user', text);
  messages.push({ role: 'user', content: text });
  const pending = add('assistant', '…');
  try {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
      body: JSON.stringify({ messages, language: lang.value }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || 'Request failed');
    pending.textContent = data.reply;
    messages.push({ role: 'assistant', content: data.reply });
    if (data.ready) {
      const a = document.createElement('a');
      a.href = '/issues/' + data.issue_id;
      a.textContent = 'Report #' + data.issue_id + ' submitted. View it';
      log.appendChild(a);
      messages = [];
    }
  } catch (err) {
    pending.textContent = 'Error: ' + err.message;
    messages.pop();
  }
});
