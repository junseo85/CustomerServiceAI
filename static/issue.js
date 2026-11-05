const csrf = document.querySelector('meta[name=csrf-token]').content;
const originals = {};

async function tr(text, language) {
  const r = await fetch('/api/translate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: JSON.stringify({ text, language }),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || 'Translation failed');
  return data.text;
}

document.getElementById('tbtn').addEventListener('click', async () => {
  const language = document.getElementById('tlang').value;
  const targets = [...document.querySelectorAll('#title, #desc, .cbody')];
  const btn = document.getElementById('tbtn');
  btn.disabled = true;
  try {
    for (const el of targets) {
      originals[el.id || el.textContent] ??= el.textContent;
      el.textContent = await tr(el.textContent, language);
    }
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
  }
});

const lb = document.getElementById('lb');
document.querySelectorAll('[data-lightbox]').forEach((a) => a.addEventListener('click', (e) => {
  e.preventDefault();
  lb.querySelector('img').src = a.href;
  lb.classList.add('open');
}));
lb.addEventListener('click', () => lb.classList.remove('open'));
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') lb.classList.remove('open'); });
