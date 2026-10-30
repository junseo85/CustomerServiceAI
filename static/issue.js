const csrf = document.querySelector('meta[name=csrf-token]').content;
const targets = [...document.querySelectorAll('#title, #desc, .cbody')];
const originals = new Map(targets.map((el) => [el, el.textContent]));

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
  const btn = document.getElementById('tbtn');
  btn.disabled = true;
  try {
    // Always translate from the original text so repeated clicks don't compound.
    for (const el of targets) el.textContent = await tr(originals.get(el), language);
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
  }
});
