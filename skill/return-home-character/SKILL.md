---
name: return-home-character
description: Guide a local-first AI companion migration using an unchanged role prompt, imported JSON/TXT chat history, manual memories, Doubao-Seed-Character, Volcano TTS, authenticated session APIs, and a signed standalone Android APK. Use when Codex needs to configure, inspect, test, package, or explain a Return Home Character template without exposing secrets, omitting third-party attribution, or rewriting the user's persona.
---

# Return Home Character

Guide the user through the repository in the user's language. Explain each irreversible or paid action before executing it.

## Workflow

1. Inspect the repository and read `README.md` plus `docs/ARCHITECTURE.md`.
2. Confirm the intended runtime:
   - use `app/server.py` only for desktop technical verification;
   - use an Android client with Keystore and native HTTPS for a phone-independent release.
3. Check inputs without printing private content:
   - role setting exists and remains byte-for-byte unchanged;
   - history is valid JSON/TXT with roles and stable IDs;
   - manual memories contain only `shared_experiences`, `relationship`, and `role_setting`;
   - no key, voice ID, chat log, audio, signing file, or private database is tracked.
4. Configure the Character request with the exact model chosen by the user. Never silently substitute another model.
5. Build dynamic context from current time, 4 to 12 recent complete turns, and at most two locally retrieved older turns. Use a soft 1600-token recent budget and a hard 500-token retrieval budget. Run retrieval only after recall-intent detection, suppress frequent or near-duplicate candidates, and keep retrieved chat at its original user or assistant role; never interpolate it into a system message.
6. Keep the system prefix stable and calculate a SHA-256 fingerprint without logging its private text. Report cache usage only from provider-returned `cached_tokens`; if absent, mark it unknown instead of estimating a hit rate.
7. Require a strong `APP_ACCESS_TOKEN` on every `/api/*` route. Keep idempotency keys scoped by `session_id`, reject request ID reuse with different text, serialize Character calls per session, and persist new messages in SQLite.
8. Configure TTS only when the user supplies authorized credentials and voice ID. Remove parenthetical action text before synthesis while keeping the displayed reply unchanged. Apply session-scoped single-flight deduplication without persisting audio.
9. Validate:
   - run `python -m unittest discover -s tests`;
   - verify one user message creates one Character request;
   - verify disabled auto-read creates no TTS request;
   - verify failures remain explicit and do not trigger fallback models.
10. Treat desktop validation as an intermediate step. A complete delivery must produce a signed APK, run without a computer or localhost service, and pass the device checks in `docs/ARCHITECTURE.md`. The validated route is a Java shell, `WebViewAssetLoader`, a narrow JavaScript bridge, native HTTPS, Keystore, and in-memory audio.
11. Before packaging or GitHub publication, read `THIRD_PARTY_NOTICES.md`, preserve every applicable license and attribution, inspect staged files for secrets and private data, and publish only fictional examples.

## Guardrails

- Never print, commit, export, or place secrets in prompts, logs, examples, or backups.
- Never upload complete private history unless the user explicitly authorizes the exact service and scope.
- Never rewrite the user's role setting.
- Never generate or deploy a local model as part of this template.
- Never claim cloud inference is fully local. State which selected context is sent to each provider.
- Never build or publish an APK unless the user explicitly requests it after desktop validation.
