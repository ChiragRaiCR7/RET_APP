"""The LangGraph checkpointer is keyed by thread id alone, so the router must scope ids per caller."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.routers import rag_router
from api.schemas.ai import MAX_CHAT_CHARS, HITLResumeRequest, RAGChatRequest


def test_scoped_thread_id_defaults_to_the_callers_session_thread() -> None:
    assert rag_router._scoped_thread_id("s1", "u1", None) == "s1:u1"
    assert rag_router._scoped_thread_id("s1", "u1", "  ") == "s1:u1"


def test_scoped_thread_id_keeps_ids_it_issued_and_nests_everything_else() -> None:
    scope = rag_router._scoped_thread_id
    assert scope("s1", "u1", "s1:u1") == "s1:u1"
    assert scope("s1", "u1", "s1:u1:abc") == "s1:u1:abc"
    assert scope("s1", "u1", "abc") == "s1:u1:abc"
    # Another user's thread id can only ever name a thread inside the caller's own scope.
    assert scope("s2", "u2", "s1:u1") == "s2:u2:s1:u1"
    assert scope("s2", "u2", "s1:u1:abc").startswith("s2:u2:")


class _FakeManager:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def is_configured(self) -> bool:
        return True

    async def chat_async(self, **kwargs):
        self.calls.append(kwargs)
        return {"answer": "ok", "sources": [], "citations": [], "query_time_ms": 1}

    async def resume_hitl(self, **kwargs):
        self.calls.append(kwargs)
        return {"answer": "ok", "sources": [], "citations": [], "query_time_ms": 1}


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch) -> _FakeManager:
    fake = _FakeManager()
    monkeypatch.setattr(rag_router, "_verify_session_owner", lambda sid, uid: {"user_id": uid})
    monkeypatch.setattr(rag_router, "_get_manager", lambda sid, uid: fake)
    monkeypatch.setattr(rag_router.settings, "FEATURE_HITL_ENABLED", True, raising=False)
    return fake


async def test_chat_cannot_address_another_users_thread(manager: _FakeManager) -> None:
    req = RAGChatRequest(session_id="s2", message="hi", thread_id="s1:u1")
    await rag_router.rag_chat(req, current_user_id="u2")
    assert manager.calls[-1]["thread_id"] == "s2:u2:s1:u1"


async def test_resume_cannot_address_another_users_thread(manager: _FakeManager) -> None:
    req = HITLResumeRequest(session_id="s2", thread_id="s1:u1")
    await rag_router.rag_chat_resume(req, current_user_id="u2")
    assert manager.calls[-1]["thread_id"] == "s2:u2:s1:u1"


def test_chat_text_is_bounded() -> None:
    with pytest.raises(ValidationError):
        RAGChatRequest(session_id="s", message="x" * (MAX_CHAT_CHARS + 1))
    with pytest.raises(ValidationError):
        RAGChatRequest(session_id="s", message="hi", history=[{"role": "user", "content": "x"}] * 51)
