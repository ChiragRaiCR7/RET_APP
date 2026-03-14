# RET v4 — Cutover Validation Playbook

## Purpose

This document provides a staged validation plan for enabling the new backend
features introduced in Phases 1–7.  Each stage activates one feature flag,
verifies correct behaviour, and establishes a rollback point before proceeding.

---

## Prerequisites

| Item | Command / Action |
|------|-----------------|
| Backend installed | `cd backend && pip install -e ".[dev]"` |
| Tests green | `pytest tests/ -v` (expect **87 passed**) |
| DB migrated | `alembic upgrade head` |
| `.env` populated | JWT_SECRET_KEY, AZURE_OPENAI_* variables set |
| Frontend built | `cd frontend && npm install && npm run build` |

---

## Stage 0 — Baseline (all flags `False`)

| Flag | Value |
|------|-------|
| `FEATURE_LANGGRAPH_ENABLED` | `False` |
| `FEATURE_CHAT_STREAMING` | `False` |
| `FEATURE_TOKEN_ROTATION` | `False` |
| `FEATURE_HITL_ENABLED` | `False` |
| `FEATURE_DSPY_ENABLED` | `False` |
| `FEATURE_LLM_CACHE` | `False` |
| `FEATURE_LANGSMITH_TRACING` | `False` |
| `FEATURE_SESSION_LOGGING` | `False` |

### Validation

1. Start backend: `uvicorn api.main:app --reload --port 8000`
2. Login with admin → verify JWT access + refresh tokens work
3. Upload a test ZIP → scan → convert → download CSV
4. AI chat (non-streamed) returns answers with citations
5. Admin console loads, lists users, shows config

**Pass criteria:** All 5 steps succeed. This is the rollback target.

---

## Stage 1 — LangGraph RAG Engine

```env
FEATURE_LANGGRAPH_ENABLED=true
```

### Validation

1. Restart backend
2. AI chat produces answers — verify `response_type` in JSON includes
   `"response_type": "langgraph"` or graph node metadata
3. Query transformation works — send an analytical query, check
   `query_transformation.intent` in response
4. Early-exit: ask an out-of-domain question → should get
   "insufficient context" refusal, not a crash
5. Performance: typical query completes in < 5 s (vs baseline)

### Rollback

Set `FEATURE_LANGGRAPH_ENABLED=false`, restart.

---

## Stage 2 — Streaming Chat (SSE)

```env
FEATURE_CHAT_STREAMING=true
```

### Validation

1. Open browser DevTools → Network tab
2. Send a chat message via the frontend
3. Verify the request is `POST /api/v2/ai/chat/stream`
4. Response headers include `content-type: text/event-stream`
5. Answer appears token-by-token in the UI (progressive rendering)
6. Final `[DONE]` event is received; sources and citations render

### Rollback

Set `FEATURE_CHAT_STREAMING=false`, restart. Frontend falls back to
non-streamed endpoint.

---

## Stage 3 — Token Rotation + Session Logging

```env
FEATURE_TOKEN_ROTATION=true
FEATURE_SESSION_LOGGING=true
```

### Validation

1. Login → note refresh token in HttpOnly cookie
2. Wait for access token to expire (or call `/api/auth/refresh`)
3. Verify a **new** refresh token is returned in the response
4. Decode both JWTs — confirm they share the same `token_family`
5. **Reuse detection:** replay the old refresh token →
   expect `401 Unauthorized` and full family revoked in DB
6. Check `runtime/logs/sessions/` for per-session log files
7. Run `pytest tests/test_session_service.py -v` — all pass

### Rollback

Set `FEATURE_TOKEN_ROTATION=false`, restart. Existing sessions
continue with non-rotating behaviour.

---

## Stage 4 — Human-in-the-Loop (HITL)

```env
FEATURE_HITL_ENABLED=true
RAG_HITL_CONFIDENCE_THRESHOLD=0.35
```

### Validation

1. Set threshold high temporarily (`0.99`) to force HITL
2. Send a chat message → response should indicate `hitl_required: true`
3. Admin panel HITL section shows pending review
4. Approve the review → answer is delivered to user
5. Test "reject" and "edit" decisions
6. Reset threshold to `0.35` → normal queries bypass HITL

### Rollback

Set `FEATURE_HITL_ENABLED=false`, restart. Graph skips HITL node.

---

## Stage 5 — LLM Cache + LangSmith Tracing

```env
FEATURE_LLM_CACHE=true
FEATURE_LANGSMITH_TRACING=true
LANGCHAIN_API_KEY=<your-key>
```

### Validation

1. Send a query → note response time
2. Send the **exact same** query → should be significantly faster (cache hit)
3. Open LangSmith dashboard → verify trace appears with
   node-level timing, tags (`session_id`, `user_id`)
4. Cache lives in `runtime/cache/llm_cache.db`

### Rollback

Set both flags `false`, restart. Cache DB can be deleted safely.

---

## Stage 6 — DSPy Optimization (Optional)

```env
FEATURE_DSPY_ENABLED=true
```

### Pre-requisite

```bash
pip install dspy-ai>=2.5.0
# Optional: run offline optimization first
python -m api.services.ai.langgraph.optimize_prompts \
  --eval-path eval/rag_cases.json \
  --output-dir eval/optimised \
  --strategy bootstrap
```

### Validation

1. Restart backend — check logs for "DSPy LM configured" message
2. If optimised modules exist in `eval/optimised/`, check logs for
   "Loaded optimised DSPy module" messages
3. Send chat queries — answers should be comparable quality
4. Run evaluation: `python -m api.services.ai.langgraph.optimize_prompts`
5. Compare scores with and without DSPy

### Rollback

Set `FEATURE_DSPY_ENABLED=false`, restart. Falls back to raw LLM prompts.

---

## Stage 7 — Full Production Configuration

Enable all flags simultaneously:

```env
FEATURE_LANGGRAPH_ENABLED=true
FEATURE_CHAT_STREAMING=true
FEATURE_TOKEN_ROTATION=true
FEATURE_SESSION_LOGGING=true
FEATURE_HITL_ENABLED=true
FEATURE_LLM_CACHE=true
FEATURE_LANGSMITH_TRACING=true
RAG_HITL_CONFIDENCE_THRESHOLD=0.35
```

### Validation

1. Run full test suite: `pytest tests/ -v` — all pass
2. Complete end-to-end workflow:
   - Login → Upload ZIP → Scan → Convert → Download
   - Index groups → Chat (streamed) → Verify citations
   - Download transcript
3. Admin console: view sessions, config, HITL status
4. Monitor `runtime/logs/` for errors over 10-minute soak period
5. Performance: p95 chat latency < 8 s, token refresh < 200 ms

---

## Smoke Test Checklist

| # | Test | Expected | Stage |
|---|------|----------|-------|
| 1 | Login with valid credentials | 200 + JWT pair | 0 |
| 2 | Login with wrong password (5x) | Account locked (403) | 0 |
| 3 | Upload + scan ZIP | session_id + groups returned | 0 |
| 4 | Convert selected groups | CSV files generated | 0 |
| 5 | Download ZIP of CSVs | Valid ZIP with CSV contents | 0 |
| 6 | AI chat (non-streamed) | Answer with citations | 0 |
| 7 | AI chat (streamed) | SSE events, progressive render | 2 |
| 8 | Refresh token → new refresh returned | New cookie set | 3 |
| 9 | Replay old refresh token | 401 + family revoked | 3 |
| 10 | Low-confidence query triggers HITL | `hitl_required: true` | 4 |
| 11 | Cached query returns faster | < 50% of first query time | 5 |
| 12 | LangSmith trace visible | Node-level spans in dashboard | 5 |

---

## Rollback Summary

Every feature flag can be independently disabled. The system is designed for
**additive activation** — disabling a flag reverts to the previous behaviour
without data loss or migration.

| Flag | Rollback Impact |
|------|----------------|
| `FEATURE_LANGGRAPH_ENABLED` | Falls back to `UnifiedRAGService.chat()` |
| `FEATURE_CHAT_STREAMING` | Falls back to non-streamed POST |
| `FEATURE_TOKEN_ROTATION` | Sessions continue without rotation |
| `FEATURE_HITL_ENABLED` | Graph skips HITL node entirely |
| `FEATURE_DSPY_ENABLED` | Falls back to raw prompt templates |
| `FEATURE_LLM_CACHE` | Cache file can be safely deleted |
| `FEATURE_LANGSMITH_TRACING` | No traces sent; no performance impact |
