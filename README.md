# Issue Reporter

AI chat assistant that interviews employees (in their own language), files a structured English
report, and lets IT / QA / managers review, translate, comment on, and triage issues.

## Run
```
pip install -r requirements.txt
cp .env.example .env      # set OPENAI_API_KEY (any OpenAI-compatible API); required for chat and translation
python app.py
```
Demo logins (when `SEED_DEMO=1`): `employee`, `it`, `qa`, `manager`, password `password`. Change/disable before deploying.

## Features
- `/` AI chat in 13 languages; replies in the user's language, reports saved in English with the original transcript.
- `/issues` dashboard: employees see their own; IT/QA/manager see all, with status/category/severity filters.
- Issue page: on-demand AI translation of title/description/comments, comments, status updates (staff only).
- Session auth, CSRF tokens, role checks. Tests: `pytest`.

## Layout
`app.py` routes · `ai.py` chat + translation · `db.py` SQLite schema · `templates/`, `static/` UI · `tests/`

## LAN deployment (works over wired and Wi-Fi)
1. On the server machine: `pip install -r requirements.txt`, copy `.env.example` to `.env`, set a long random `SECRET_KEY`, set `SEED_DEMO=0`.
2. Give the server a fixed IP (static or DHCP reservation), e.g. `192.168.1.50`.
3. Allow the port in the server firewall (Windows, admin PowerShell):
   `New-NetFirewallRule -DisplayName "IssueReporter" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow`
4. Start with `python serve.py` (waitress; listens on all interfaces by default). Users open `http://192.168.1.50:5000` from any device on the same network.
5. Create staff accounts: register in the UI, then promote, e.g.
   `sqlite3 issues.db "UPDATE users SET role='it' WHERE username='alice'"` (roles: employee, it, qa, manager).

Clients only need the local network, so the site works when the internet is down. AI chat and translation
still need internet unless you run a local model (e.g. Ollama): set `OPENAI_BASE_URL=http://localhost:11434/v1`,
`OPENAI_MODEL=<model>` and any non-empty `OPENAI_API_KEY`. HTTPS is not configured; keep it on the trusted company network.

## Next ideas
Assignment to teams, email/Teams notifications, attachments/screenshots, admin user management, Postgres.
