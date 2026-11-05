const csrf = document.querySelector('meta[name=csrf-token]').content;
const $ = (id) => document.getElementById(id);
const log = $('log'), form = $('form'), input = $('msg'), lang = $('lang'), tray = $('tray'), box = $('chatbox');
const MAX_FILES = 5;
let messages = [];
let pending = []; // uploaded attachments not yet sent: {id, filename, mime, size, url}
let uploading = 0;
let sentIds = []; // attachments already sent in this conversation; linked to the ticket when filed

function scroll() { log.scrollTop = log.scrollHeight; }

function add(role, text, files = []) {
  const d = document.createElement('div');
  d.className = 'bubble ' + role;
  if (text) d.append(text);
  for (const f of files) {
    if (f.mime.startsWith('image/')) {
      const img = document.createElement('img');
      img.src = f.url; img.alt = f.filename;
      d.appendChild(img);
    } else {
      const c = document.createElement('div');
      c.className = 'filechip'; c.textContent = '📄 ' + f.filename;
      d.appendChild(c);
    }
  }
  log.appendChild(d);
  scroll();
  return d;
}

function typing() {
  const d = document.createElement('div');
  d.className = 'bubble assistant typing';
  d.innerHTML = '<span></span><span></span><span></span>';
  log.appendChild(d); scroll();
  return d;
}

function fmt(n) { return n > 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB'; }

function thumb(file) {
  const t = document.createElement('div');
  t.className = 'thumb uploading';
  const isImg = file.type && file.type.startsWith('image/');
  const visual = document.createElement(isImg ? 'img' : 'div');
  if (isImg) visual.src = URL.createObjectURL(file); else { visual.className = 'ico'; visual.textContent = (file.name.split('.').pop() || 'file').toUpperCase().slice(0, 4); }
  const meta = document.createElement('div');
  meta.className = 'meta';
  const b = document.createElement('b'); b.textContent = file.name;
  const s = document.createElement('small'); s.textContent = 'Uploading…';
  meta.append(b, s);
  t.append(visual, meta);
  tray.appendChild(t);
  return { t, s };
}

async function upload(file) {
  if (pending.length + uploading >= MAX_FILES) { flash(`Max ${MAX_FILES} attachments`); return; }
  const { t, s } = thumb(file);
  uploading++;
  try {
    const fd = new FormData(); fd.append('file', file, file.name);
    const r = await fetch('/api/attachments', { method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: fd });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(r.status === 413 ? 'File too large (max 10 MB)' : data.error || 'Upload failed');
    pending.push(data);
    t.classList.remove('uploading');
    s.textContent = fmt(data.size);
    const x = document.createElement('button');
    x.type = 'button'; x.className = 'x'; x.textContent = '×'; x.title = 'Remove';
    x.onclick = async () => {
      pending = pending.filter((p) => p.id !== data.id); t.remove();
      fetch(`/api/attachments/${data.id}/delete`, { method: 'POST', headers: { 'X-CSRF-Token': csrf } });
    };
    t.appendChild(x);
  } catch (e) {
    t.classList.remove('uploading'); t.classList.add('err'); s.textContent = e.message;
    setTimeout(() => t.remove(), 4000);
  } finally { uploading--; }
}

function flash(msg) {
  const d = document.createElement('div'); d.className = 'thumb err'; d.textContent = msg;
  tray.appendChild(d); setTimeout(() => d.remove(), 3500);
}

const addFiles = (files) => [...files].forEach(upload);
$('attach').onclick = () => $('file').click();
$('file').onchange = (e) => { addFiles(e.target.files); e.target.value = ''; };
document.addEventListener('paste', (e) => {
  const files = [...(e.clipboardData?.files || [])];
  if (files.length) { e.preventDefault(); addFiles(files); }
});
let depth = 0;
box.addEventListener('dragenter', (e) => { e.preventDefault(); depth++; box.classList.add('dragging'); });
box.addEventListener('dragleave', () => { if (--depth <= 0) { depth = 0; box.classList.remove('dragging'); } });
box.addEventListener('dragover', (e) => e.preventDefault());
box.addEventListener('drop', (e) => { e.preventDefault(); depth = 0; box.classList.remove('dragging'); addFiles(e.dataTransfer.files); });

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  if (uploading) return;
  let text = input.value.trim();
  if (!text && !pending.length) return;
  if (!text) text = 'Please see the attached file(s).';
  const files = pending; pending = []; tray.innerHTML = ''; input.value = '';
  add('user', text, files);
  messages.push({ role: 'user', content: text });
  const wait = typing();
  try {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
      body: JSON.stringify({ messages, language: lang.value, attachment_ids: [...sentIds, ...files.map((f) => f.id)], new_attachment_ids: files.map((f) => f.id) }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || 'Request failed');
    wait.remove();
    sentIds.push(...files.map((f) => f.id));
    add('assistant', data.reply);
    messages.push({ role: 'assistant', content: data.reply });
    if (data.ready) {
      const a = document.createElement('a');
      a.className = 'success';
      a.href = '/issues/' + data.issue_id;
      a.textContent = '✓ Ticket #' + data.issue_id + ' created. View it →';
      log.appendChild(a); scroll();
      messages = []; sentIds = [];
    }
  } catch (err) {
    wait.remove();
    add('assistant', 'Error: ' + err.message);
    messages.pop();
    pending = files; // keep uploads so the user can retry
    files.forEach((f) => { const d = document.createElement('div'); d.className = 'thumb'; d.textContent = f.filename; tray.appendChild(d); });
  }
});
