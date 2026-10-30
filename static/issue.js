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
