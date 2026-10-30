"""AI chat + translation. Uses an OpenAI-compatible API, or an offline mock when no key is set."""
import json
import os
import re

import requests

from db import CATEGORIES, SEVERITIES

LANGUAGES = {
    "en": "English", "ko": "Korean", "es": "Spanish", "zh": "Chinese", "ja": "Japanese",
    "fr": "French", "de": "German", "pt": "Portuguese", "vi": "Vietnamese", "ar": "Arabic",
    "hi": "Hindi", "ru": "Russian", "tl": "Tagalog",
}

SYSTEM_PROMPT = """You are a friendly workplace issue-reporting assistant. The user speaks {lang_name} (code {lang}).
Always reply in {lang_name}. Interview the user briefly (one or two questions at a time) to learn:
what happened, where/which system, when, impact, and urgency. Once you have enough detail,
finish by returning the final report.

Respond ONLY with JSON of this shape:
{{"reply": "<message to user in {lang_name}>",
  "ready": <true when enough info was collected, else false>,
  "issue": {{"title": "<English, <=80 chars>", "description": "<English, full detail>",
             "category": "one of {categories}", "severity": "one of {severities}"}} }}
"issue" must be present only when ready is true. Never invent facts."""


def _chat(messages, json_mode=False):
    key = os.environ.get("OPENAI_API_KEY")
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    body = {"model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), "messages": messages, "temperature": 0.2}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    r = requests.post(f"{base}/chat/completions", json=body, timeout=60,
                      headers={"Authorization": f"Bearer {key}"})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def mock_enabled():
    return not os.environ.get("OPENAI_API_KEY")


def _parse_json(text):
    m = re.search(r"\{.*\}", text.strip(), re.S)
    return json.loads(m.group(0) if m else text)


def _normalize(data):
    issue = data.get("issue")
    ready = bool(data.get("ready")) and isinstance(issue, dict)
    if ready:
        issue = {
            "title": str(issue.get("title", "Untitled issue"))[:120],
            "description": str(issue.get("description", "")),
            "category": issue.get("category") if issue.get("category") in CATEGORIES else "other",
            "severity": issue.get("severity") if issue.get("severity") in SEVERITIES else "medium",
        }
    else:
        issue = None
    return {"reply": str(data.get("reply", "")), "ready": ready, "issue": issue}


def chat(messages, lang):
    """messages: [{role: user|assistant, content}]. Returns {reply, ready, issue}."""
    if mock_enabled():
        return _mock_chat(messages)
    system = SYSTEM_PROMPT.format(lang_name=LANGUAGES.get(lang, lang), lang=lang,
                                  categories=CATEGORIES, severities=SEVERITIES)
    out = _chat([{"role": "system", "content": system}] + messages, json_mode=True)
    return _normalize(_parse_json(out))


def translate(text, target_lang):
    if not text.strip():
        return text
    if mock_enabled():
        return f"[{target_lang}] {text}"
    name = LANGUAGES.get(target_lang, target_lang)
    return _chat([
        {"role": "system", "content": f"Translate the user's text to {name}. Output only the translation."},
        {"role": "user", "content": text},
    ]).strip()


def _mock_chat(messages):
    """Offline stand-in: asks one follow-up, then files the report."""
    user_msgs = [m["content"] for m in messages if m["role"] == "user"]
    if len(user_msgs) < 2:
        return {"reply": "(mock AI) Thanks. Where did this happen, and how urgent is it?",
                "ready": False, "issue": None}
    text = " ".join(user_msgs)
    sev = "high" if re.search(r"urgent|down|fire|injur|critical", text, re.I) else "medium"
    return {"reply": "(mock AI) Thank you, I've filed your report.", "ready": True,
            "issue": {"title": user_msgs[0][:80], "description": text,
                      "category": "other", "severity": sev}}
