# Code Review

Reviewed the complete tracked repository line by line: 1,183 lines across application code, templates, styles, tests, configuration, and documentation. The findings below are actionable issues; file-by-file coverage is recorded at the end. Concise comments were also added to clarify the main request flows and controller responsibilities.

## Findings

| # | Severity | Location | Finding | Suggested action |
|---|---|---|---|---|
| 1 | High | `ai.py:38-41` | `_chat` reads `OPENAI_API_KEY` into `key`, but sends the literal `******` as the authorization header. Live chat and translation requests therefore cannot authenticate with the configured provider and fail. | Use the provider's expected authorization-header format and add a test that verifies it without exposing the key. |
| 2 | High | `app.py:37-38` | If `SECRET_KEY` is unset, Flask uses the public `dev-only-change-me` value. A deployed app using this fallback has forgeable session cookies. | Require a strong deployment secret and reserve an explicit test-only secret for tests. |
| 3 | Medium | `.env.example:7-8`, `db.py:63-68` | The sample environment enables demo seeding with the shared password `password`. Seeded accounts are not removed when seeding is later disabled, so copying the sample into a deployment can leave predictable accounts active. | Default seeding off in the sample and explicitly remove or rotate demo users before deployment. |
| 4 | Medium | `app.py:43-45` | Session cookies are marked HttpOnly and SameSite, but `SESSION_COOKIE_SECURE` is not enabled. Over an HTTP connection, browsers can send the session cookie in cleartext. | Enable the secure-cookie flag for HTTPS deployments. |
| 5 | Medium | `app.py:143-150` | Registration catches every exception and reports that the username is taken. Database outages and other unexpected write failures are hidden as a user-input error. | Catch the expected uniqueness violation separately and log or surface other database failures. |
| 6 | Low | `app.py:169-173` | The chat endpoint assumes the JSON body is an object and `messages` is a sliceable list. Valid JSON with another shape can raise an uncaught exception and return a 500 instead of the API's 400 invalid-request response. | Validate the body and field types before indexing or slicing. |
| 7 | Low | `static/issue.js:21-24` | Original field text is saved in `originals` but never used. Each translation click translates the already-translated text again rather than translating the original content. | Translate from the saved original or remove the unused cache if repeated translation is intentional. |

## Line-by-line coverage

Every line in each listed tracked file was reviewed. Ranges include blank lines and comments.

| File | Lines reviewed |
|---|---:|
| `.env.example` | 1-11 |
| `.gitignore` | 1-6 |
| `README.md` | 1-30 |
| `ai.py` | 1-114 |
| `app.py` | 1-376 |
| `db.py` | 1-70 |
| `requirements.txt` | 1-4 |
| `static/chat.js` | 1-138 |
| `static/issue.js` | 1-39 |
| `static/style.css` | 1-115 |
| `templates/base.html` | 1-26 |
| `templates/chat.html` | 1-31 |
| `templates/issue.html` | 1-52 |
| `templates/issues.html` | 1-30 |
| `templates/login.html` | 1-14 |
| `templates/register.html` | 1-15 |
| `tests/test_app.py` | 1-112 |
