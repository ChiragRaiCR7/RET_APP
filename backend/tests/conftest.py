import gzip
import io
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ADMIN_PW = "Admin-Pass-2026!"


def zip_bytes(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def rowset(rows: list[dict[str, str]], record: str = "ROW", root: str = "ROWSET") -> bytes:
    body = "".join(
        f"<{record}>" + "".join(f"<{k}>{v}</{k}>" for k, v in r.items()) + f"</{record}>"
        for r in rows
    )
    return f'<?xml version="1.0"?><{root}>{body}</{root}>'.encode()


FUN_ROWS = [
    {"Name": "US Ops", "PrimaryLedgerName": "US Ledger", "LegalEntityName": "Acme US"},
    {"Name": "UK Ops", "PrimaryLedgerName": "UK Ledger", "LegalEntityName": "Acme UK"},
    {"Name": "", "PrimaryLedgerName": "X", "LegalEntityName": "Y"},
]
INV_ROWS = [
    {"NAME": "Dallas DC", "BusinessUnitName": "US Ops"},
    {"NAME": "Leeds DC", "BusinessUnitName": "UK Ops"},
    {"NAME": "Orphan DC", "BusinessUnitName": "Nowhere"},
]
TERMS = [
    {"TermId": "1", "Name": "NET30", "DueDays": "30", "CreatedBy": "alice"},
    {"TermId": "2", "Name": "NET60", "DueDays": "60", "CreatedBy": "alice"},
    {"TermId": "3", "Name": "COD", "DueDays": "0", "CreatedBy": "bob"},
]


def oracle_export(terms: list[dict[str, str]] = TERMS) -> bytes:
    """Root container → business ZIPs (one with a batch ZIP) + a loose CSV."""
    fun = zip_bytes({"1_BATCH.zip": zip_bytes({"FUN_BUSINESS_UNIT.xml": rowset(FUN_ROWS)})})
    inv = zip_bytes(
        {
            "InventoryOrganizationMaster.xml": rowset(INV_ROWS[:2]),
            "InventoryOrganizationChild.xml": rowset(INV_ROWS[1:]),
        }
    )
    ar = zip_bytes({"AR_PAYMENT_TERMS.xml.gz": gzip.compress(rowset(terms))})
    return zip_bytes(
        {
            "FUN_BUSINESS_UNIT.zip": fun,
            "INV_ORGANIZATIONS.zip": inv,
            "AR_PAYMENT_TERM.zip": ar,
            "GL_DATA/ledgers.csv": b"Ledger,Currency\nUS Ledger,USD\nUK Ledger,GBP\n",
            "__MACOSX/._junk": b"x",
        }
    )


@pytest.fixture
def app_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", ADMIN_PW)
    monkeypatch.setenv("FRONTEND_DIST", str(tmp_path / "no-dist"))
    for var in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_CHAT_MODEL"):
        monkeypatch.delenv(var, raising=False)
    from app import config, db
    from app.services import assistant, jobs

    config.get_settings.cache_clear()
    assistant._client.cache_clear()
    db.reset_engine()
    monkeypatch.setattr(jobs, "RUN_INLINE", True)
    yield tmp_path
    db.reset_engine()
    config.get_settings.cache_clear()


@pytest.fixture
def client(app_env: Path) -> Iterator[TestClient]:
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


def login(c: TestClient, username: str, password: str) -> None:
    r = c.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text


@pytest.fixture
def admin(client: TestClient) -> TestClient:
    login(client, "admin", ADMIN_PW)
    return client


def make_user(admin_client: TestClient, username: str, password: str = "User-Pass-2026!") -> None:
    r = admin_client.post(
        "/api/admin/users", json={"username": username, "password": password, "role": "user"}
    )
    assert r.status_code == 201, r.text


def upload(c: TestClient, name: str, data: bytes) -> dict:  # type: ignore[type-arg]
    r = c.post(
        "/api/workspaces",
        params={"filename": name},
        content=data,
        headers={"content-type": "application/octet-stream"},
    )
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]
