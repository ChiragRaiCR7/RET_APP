"""Regression tests for auto-embed policy and stop/suppression semantics."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from api.routers import rag_router
from api.schemas.ai import GroupSelectionRequest
from api.services.ai import session_manager as sm


class _FakeRAGService:
    def clear_history(self):
        return None

    def get_history(self, limit: int = 50):
        return []


class _FakeAutoEmbedder:
    def __init__(self):
        self.stop_called = False
        self.start_called = False
        self.reload_called = False
        self.is_auto_embed_enabled = True

    def reload_admin_config(self):
        self.reload_called = True
        return {}

    def detect_eligible_groups(self, _xml_inventory):
        return ["AAL"]

    def start_auto_embed(self, **_kwargs):
        self.start_called = True

    @property
    def progress(self):
        return SimpleNamespace(status="idle")

    def stop(self):
        self.stop_called = True


class _FakeWorker:
    def __init__(self, cancelled_count: int = 0):
        self.cancelled_count = cancelled_count

    async def cancel_session_tasks(self, _session_id: str) -> int:
        return self.cancelled_count


class _FakeManagerForRouter:
    def __init__(self):
        self.is_auto_embed_suppressed = True
        self.clear_called = False
        self.embed_calls = []

    def clear_auto_embed_suppression(self):
        self.clear_called = True
        self.is_auto_embed_suppressed = False

    def is_configured(self):
        return True

    def embed_groups(self, groups):
        self.embed_calls.append(list(groups))
        return SimpleNamespace(
            indexed_chunks=12,
            indexed_files=3,
            indexed_docs=3,
            groups_processed=list(groups),
            errors=[],
        )


@pytest.fixture()
def session_ai_manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Create SessionAIManager with a mocked RAG factory and fake auto-embedder."""
    monkeypatch.setattr(sm, "get_rag_service", lambda *_args, **_kwargs: _FakeRAGService())

    manager = sm.SessionAIManager(
        session_id="sid-1",
        user_id="user-1",
        session_dir=tmp_path,
    )
    manager.__dict__["_auto_embedder"] = _FakeAutoEmbedder()
    return manager


def test_start_auto_embed_respects_session_suppression(session_ai_manager):
    session_ai_manager.set_auto_embed_suppressed(True, reason="user stop", source="test")

    result = session_ai_manager.start_auto_embed([{"group": "AAL"}])

    assert result["status"] == "suppressed"
    assert result["eligible_groups"] == []
    assert session_ai_manager._auto_embedder.start_called is False
    assert session_ai_manager._auto_embedder.reload_called is False


@pytest.mark.asyncio
async def test_stop_all_embedding_sets_suppression_and_cancels_worker(
    session_ai_manager,
    monkeypatch: pytest.MonkeyPatch,
):
    async def _fake_get_worker():
        return _FakeWorker(cancelled_count=3)

    monkeypatch.setattr("api.workers.embedding_worker.get_embedding_worker", _fake_get_worker)

    result = await session_ai_manager.stop_all_embedding(
        suppress_auto_start=True,
        reason="Stopped by user",
        source="user-1",
    )

    assert result["auto_embed_stopped"] is True
    assert result["worker_tasks_cancelled"] == 3
    assert result["auto_embed_suppressed"] is True
    assert session_ai_manager.is_auto_embed_suppressed is True
    assert session_ai_manager._auto_embedder.stop_called is True


def test_trigger_auto_embed_after_conversion_skips_when_suppressed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_manager = SimpleNamespace(
        is_auto_embed_suppressed=True,
        session_dir=tmp_path,
    )

    monkeypatch.setattr(sm, "get_session_ai_manager", lambda *_args, **_kwargs: fake_manager)

    result = sm.trigger_auto_embed_after_conversion(
        session_id="sid-1",
        user_id="user-1",
        conversion_result={"stats": {"success": 1, "failed": 0}},
    )

    assert result["status"] == "suppressed"
    assert result["attempted"] is True
    assert result["triggered"] is False
    assert result["eligible_groups"] == []


@pytest.mark.asyncio
async def test_embed_selected_groups_clears_suppression_on_manual_index(
    monkeypatch: pytest.MonkeyPatch,
):
    manager = _FakeManagerForRouter()

    monkeypatch.setattr(rag_router, "_verify_session_owner", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(rag_router, "_get_manager", lambda *_args, **_kwargs: manager)
    monkeypatch.setattr("api.services.admin_service.get_ai_indexing_config_data", lambda: {})

    req = GroupSelectionRequest(
        session_id="sid-1",
        selected_groups=None,
        groups=["AAL"],
        background=False,
    )

    result = await rag_router.embed_selected_groups(req=req, current_user_id="1")

    assert manager.clear_called is True
    assert manager.embed_calls == [["AAL"]]
    assert result["status"] == "success"
    assert result["auto_embed_suppression_cleared"] is True


@pytest.mark.asyncio
async def test_stop_endpoint_returns_suppression_state(monkeypatch: pytest.MonkeyPatch):
    class _StopManager:
        async def stop_all_embedding(self, **_kwargs):
            return {
                "auto_embed_stopped": True,
                "worker_tasks_cancelled": 2,
                "auto_embed_suppressed": True,
            }

    monkeypatch.setattr(rag_router, "_verify_session_owner", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(rag_router, "_get_manager", lambda *_args, **_kwargs: _StopManager())

    result = await rag_router.stop_auto_embed(session_id="sid-1", current_user_id="1")

    assert result["stopped"] is True
    assert result["worker_tasks_cancelled"] == 2
    assert result["auto_embed_suppressed"] is True
