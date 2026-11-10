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
- Microphone input in chat: record up to two minutes, then review and edit the transcription before sending. Audio is sent to the configured AI provider and is not stored by the app. A compatible speech-to-text API, an API key, browser microphone permission, and HTTPS (or localhost) are required; voice input is unavailable in offline demo mode. Provider retention policies and API charges apply.
- `/issues` dashboard: employees see their own; IT/QA/manager see all, with status/category/severity filters.
- Issue page: on-demand AI translation of title/description/comments, comments, status updates (staff only).
- Attachments: attach, paste or drag-drop screenshots/PDF/TXT/LOG (10 MB, 5 per report) in the chat. Images are sent to the AI (vision) and all files are linked to the ticket, shown as a gallery on the issue page. Uploads are type-checked by content, stored under `UPLOAD_DIR`, and only served to the reporter and staff.
- Session auth, CSRF tokens, role checks. Tests: `pytest`.

## Layout
`app.py` routes · `ai.py` chat + translation · `db.py` SQLite schema · `templates/`, `static/` UI · `tests/`

## Connecting the AI (live demo)
1. `cp .env.example .env`, then set `OPENAI_API_KEY=sk-...` (default model `gpt-4o-mini`, which supports screenshots).
2. Restart `python app.py`. The pill above the chat changes from "AI: demo mode" to "AI: <model>".
Any OpenAI-compatible provider works via `OPENAI_BASE_URL` / `OPENAI_MODEL` (e.g. Azure OpenAI, GitHub Models, Ollama with a vision model).
Voice input also requires that provider to support the `/audio/transcriptions` endpoint and the configured `OPENAI_TRANSCRIBE_MODEL` (default `gpt-transcribe`); chat compatibility alone does not guarantee speech support. Select the spoken language in the chat before recording.

## Next ideas
Assignment to teams, email/Teams notifications, admin user management, Postgres.
