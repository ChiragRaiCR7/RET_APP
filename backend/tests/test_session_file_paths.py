"""File names from requests must never reach files outside the session's output folder."""

from pathlib import Path

import pytest

from api.services import conversion_service, storage_service

USER = "7"
ESCAPES = [
    "../../../../outside.CSV",  # parent traversal
    "..%2F..%2F..%2F..%2Foutside.CSV",  # decoded by the service's unquote()
    "%2Ftmp%2Foutside.CSV",  # absolute after unquote: pathlib would drop the base
]


@pytest.fixture
def session() -> tuple[str, Path]:
    sid = storage_service.create_session_dir(USER)
    out = storage_service.get_session_dir(sid) / "output"
    (out / "GOOD.CSV").write_text("a,b\n1,2\n")
    return sid, out


@pytest.fixture
def outside(tmp_path_factory) -> Path:
    victim = storage_service.SESSIONS_ROOT.parent / "outside.CSV"
    victim.write_text("secret,data\n")
    Path("/tmp/outside.CSV").write_text("secret,data\n")
    yield victim
    victim.unlink(missing_ok=True)
    Path("/tmp/outside.CSV").unlink(missing_ok=True)


def test_contained_path_accepts_children_only(tmp_path) -> None:
    assert storage_service.contained_path(tmp_path, "a/b.csv") == (tmp_path / "a/b.csv").resolve()
    for bad in ("../x", "/etc/passwd", ".", ""):
        with pytest.raises(ValueError):
            storage_service.contained_path(tmp_path, bad)


@pytest.mark.parametrize("name", ESCAPES)
def test_preview_refuses_escaping_names(session, outside, name) -> None:
    sid, _ = session
    with pytest.raises((ValueError, FileNotFoundError)):
        conversion_service.get_file_preview(sid, USER, name)
    assert conversion_service.get_file_preview(sid, USER, "GOOD.CSV")["headers"] == ["a", "b"]


@pytest.mark.parametrize("name", ESCAPES)
def test_delete_cannot_remove_files_outside_the_session(session, outside, name) -> None:
    sid, _ = session
    with pytest.raises((ValueError, FileNotFoundError)):
        conversion_service.delete_file(sid, USER, name)
    assert outside.exists() and Path("/tmp/outside.CSV").exists()


def test_add_file_cannot_write_outside_the_session(session) -> None:
    sid, out = session
    name = "../../../../EVIL.CSV"
    target = (out / name).resolve()  # where the old code actually wrote
    try:
        with pytest.raises(ValueError):
            conversion_service.add_new_file(sid, USER, name, None, ["a"])
        assert not target.exists()
    finally:
        target.unlink(missing_ok=True)
