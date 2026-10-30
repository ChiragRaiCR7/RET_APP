"""/comparison/drilldown reads CSV files named in the query string: only inside the caller's sessions."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.core.dependencies import get_current_user_id
from api.routers import comparison_router
from api.services import storage_service

CSV = "id,name\n1,alpha\n2,beta\n"


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(comparison_router.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user_id] = lambda: "7"
    return TestClient(app)


def _session_csv(owner: str, name: str = "a.csv") -> Path:
    sid = storage_service.create_session_dir(owner)
    path = storage_service.get_session_dir(sid) / "output" / name
    path.write_text(CSV)
    return path


def _drilldown(client: TestClient, a: Path | str, b: Path | str):
    return client.post("/api/v1/comparison/drilldown", params={"csv_path_a": str(a), "csv_path_b": str(b)})


def test_files_in_own_session_are_compared(client) -> None:
    a, b = _session_csv("7", "a.csv"), _session_csv("7", "b.csv")
    assert _drilldown(client, a, b).status_code == 200


@pytest.mark.parametrize("target", ["outside", "other_user", "traversal", "no_owner"])
def test_paths_outside_own_sessions_are_refused(client, tmp_path, target) -> None:
    own = _session_csv("7")
    if target == "outside":
        secret = tmp_path / "secret.env"
        secret.write_text("JWT_SECRET_KEY=topsecret\n")
    elif target == "other_user":
        secret = _session_csv("8")
    elif target == "traversal":
        secret = own.parent / ".." / ".." / ".." / ".." / "pyproject.toml"
    else:
        secret = _session_csv("")
    resp = _drilldown(client, own, secret)
    assert resp.status_code == 403, resp.text
    assert "topsecret" not in resp.text and "hatchling" not in resp.text


def test_session_dir_rejects_sibling_prefix_escape() -> None:
    sibling = storage_service.SESSIONS_ROOT.parent / "sessions_evil"
    sibling.mkdir(exist_ok=True)
    try:
        with pytest.raises(ValueError):
            storage_service.get_session_dir("../sessions_evil")
    finally:
        sibling.rmdir()


def test_upload_comparison_csvs_are_drillable_by_their_owner_only(client) -> None:
    from api.services.comparison_service import compare_files

    result = compare_files(
        b"id,name\n1,alpha\n2,beta\n", "people.csv",
        b"id,name\n1,alpha\n2,BETA\n", "people.csv",
        owner="7",
    ).to_dict()
    pairs = [f for f in result.get("changes", []) if f.get("csv_path_a") and f.get("csv_path_b")]
    assert pairs, result
    a, b = pairs[0]["csv_path_a"], pairs[0]["csv_path_b"]
    assert _drilldown(client, a, b).status_code == 200

    client.app.dependency_overrides[get_current_user_id] = lambda: "8"
    assert _drilldown(client, a, b).status_code == 403


def test_temp_dirs_without_owner_marker_are_refused(client, tmp_path) -> None:
    import tempfile

    own = _session_csv("7")
    unmarked = Path(tempfile.mkdtemp(prefix="comparison_")) / "x.csv"
    unmarked.write_text(CSV)
    assert _drilldown(client, own, unmarked).status_code == 403
