# Issue Reporter

AI chat assistant that interviews employees (in their own language), files a structured English
report, and lets IT / QA / managers review, translate, comment on, and triage issues.

## Run
```
pip install -r requirements.txt
cp .env.example .env      # set OPENAI_API_KEY (any OpenAI-compatible API); empty = offline mock AI
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

## Next ideas
Assignment to teams, email/Teams notifications, attachments/screenshots, admin user management, Postgres.
