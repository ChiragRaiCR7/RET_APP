"""Browser end-to-end checks: real backend (SQLite) + Vite dev server + Chromium.

Opt-in because it needs Node and a browser:
    pip install -e ".[dev,e2e]" && playwright install chromium   (once)
    RET_E2E=1 pytest tests/e2e -q
    (optional) RET_E2E_CHROMIUM=/path/to/chrome to use an already-installed browser

Covers login and session restore, the admin guard, upload -> scan -> convert, the AI
answer renderer (chat API stubbed: there is no model here) and comparison drilldown.
"""

from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
import time
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

if os.environ.get("RET_E2E") != "1":
    pytest.skip("set RET_E2E=1 to run browser tests", allow_module_level=True)

sync_api = pytest.importorskip("playwright.sync_api")

BACKEND = Path(__file__).resolve().parents[2]
FRONTEND = BACKEND.parent / "frontend"
API_PORT, WEB_PORT = 8000, 5173  # vite.config.js proxies /api to :8000
APP = f"http://localhost:{WEB_PORT}"


def _wait_for_port(port: int, timeout: float = 90) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.25)
    raise RuntimeError(f"nothing listening on :{port}")


def _ledger_zip(path: Path, rows: list[tuple[int, str]]) -> Path:
    xml = "<?xml version='1.0'?><ROWSET>" + "".join(
        f"<ROW><LEDGER_ID>{i}</LEDGER_ID><NAME>{n}</NAME></ROW>" for i, n in rows
    ) + "</ROWSET>"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("GL_LEDGERS.xml", xml)
    return path


@pytest.fixture(scope="module")
def servers(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    runtime = tmp_path_factory.mktemp("runtime")
    env = {
        **os.environ,
        "ENV": "development",
        "DATABASE_URL": f"sqlite+aiosqlite:///{runtime}/ret.db",
        "RET_RUNTIME_ROOT": str(runtime),
        "JWT_SECRET_KEY": secrets.token_urlsafe(40),
    }
    py = sys.executable
    subprocess.run([py, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True)
    subprocess.run([py, "-m", "scripts.init_db", "--seed-demo"], cwd=BACKEND, env=env, check=True)
    procs = [
        subprocess.Popen([py, "-m", "uvicorn", "api.main:app", "--port", str(API_PORT)], cwd=BACKEND, env=env),
        subprocess.Popen(["npx", "vite", "--host", "localhost", "--port", str(WEB_PORT)], cwd=FRONTEND, env=env),
    ]
    try:
        _wait_for_port(API_PORT)
        _wait_for_port(WEB_PORT)
        yield runtime
    finally:
        for proc in procs:
            proc.terminate()
            proc.wait(timeout=20)


@pytest.fixture
def page(servers):
    with sync_api.sync_playwright() as p:
        # RET_E2E_CHROMIUM points at a preinstalled browser when `playwright install` can't run.
        executable = os.environ.get("RET_E2E_CHROMIUM") or None
        browser = p.chromium.launch(executable_path=executable)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        yield page
        browser.close()
        assert errors == [], errors


def _login(page, username: str = "demo", password: str = "demo123") -> None:
    page.goto(APP)
    page.get_by_label("Username").first.fill(username)
    page.get_by_label("Password").first.fill(password)
    page.get_by_role("button", name="Sign in").or_(page.get_by_role("button", name="Log in")).first.click()
    page.wait_for_url("**/app", timeout=30000)


def test_login_keeps_token_in_memory_and_survives_reload(page) -> None:
    _login(page)
    stored = page.evaluate("JSON.stringify({...localStorage, ...sessionStorage})")
    assert "access" not in stored and "eyJ" not in stored
    page.reload()
    page.wait_for_timeout(3000)
    assert page.url.endswith("/app")
    page.goto(f"{APP}/admin")
    page.wait_for_timeout(3000)
    assert page.url.endswith("/app"), "non-admin must not reach /admin"


def test_convert_then_render_ai_answer_safely(page, tmp_path) -> None:
    answer = "\n\n".join([
        "**Ledger summary** [csv:1]",
        '```chart\n{"type":"bar","data":{"labels":["L1","L2"],"datasets":[{"data":[3,5]}]}}\n```',
        '```table\n{"columns":["id","name"],"data":[[1,"a"],[2,"b"]]}\n```',
        '```kpi\n{"Ledgers": 2, "Rows": 8}\n```',
        "```mermaid\ngraph TD; A[Ledger]-->B[Entity]\n```",
        '<img src=x onerror="window.pwned=1">',
    ])
    page.route("**/api/v1/v2/ai/chat", lambda r: r.fulfill(json={"answer": answer, "sources": []}))
    _login(page)
    page.locator('input[type="file"]').first.set_input_files(str(_ledger_zip(tmp_path / "s.zip", [(1, "a")])))
    page.get_by_role("button", name="Scan", exact=True).click()
    page.get_by_text("Groups found").first.wait_for(timeout=60000)
    page.get_by_role("button", name="Convert all").click()
    page.wait_for_function("() => !document.body.innerText.includes('Converting…')", timeout=120000)
    page.get_by_role("tab").nth(3).click()
    box = page.get_by_placeholder("Ask about your indexed documents…")
    box.fill("Summarize")
    box.press("Enter")
    page.locator(".chart-slot canvas").first.wait_for(timeout=20000)
    page.wait_for_timeout(1000)
    assert page.locator(".table-slot tbody tr").count() == 2
    assert page.locator(".stats-slot .stat-card").count() == 2
    assert page.locator(".mermaid-diagram svg").count() == 1
    assert page.evaluate("window.pwned === 1") is False


def test_comparison_drilldown_opens_in_new_tab(page, tmp_path) -> None:
    a = _ledger_zip(tmp_path / "a.zip", [(1, "alpha"), (2, "beta"), (3, "gamma")])
    b = _ledger_zip(tmp_path / "b.zip", [(1, "alpha"), (2, "BETA"), (4, "delta")])
    _login(page)
    page.get_by_role("tab").nth(2).click()
    inputs = page.locator('.comparison-panel input[type="file"]')
    inputs.first.wait_for(state="attached", timeout=20000)
    inputs.nth(0).set_input_files(str(a))
    inputs.nth(1).set_input_files(str(b))
    page.get_by_role("button", name="Compare Now").click()
    button = page.get_by_role("button", name="Compare Data ↗").first
    button.wait_for(timeout=120000)
    with page.context.expect_page(timeout=15000) as opened:
        button.click()
    drill = opened.value
    drill.locator("table").first.wait_for(timeout=30000)
    assert "BETA" in drill.inner_text("body")
    assert "Popup blocked" not in page.inner_text("body")


def test_edit_dialog_is_modal_labelled_and_closes_on_escape(page, tmp_path) -> None:
    _login(page)
    page.locator('input[type="file"]').first.set_input_files(str(_ledger_zip(tmp_path / "e.zip", [(1, "a")])))
    page.get_by_role("button", name="Scan", exact=True).click()
    page.get_by_text("Groups found").first.wait_for(timeout=60000)
    page.get_by_role("button", name="Convert all").click()
    page.wait_for_function("() => !document.body.innerText.includes('Converting…')", timeout=120000)
    page.get_by_label("Enable Edit Mode").check()
    page.get_by_role("button", name="Add New File").click()
    dialog = page.get_by_role("dialog", name="Add New File")
    dialog.wait_for(timeout=10000)
    # showModal() moves focus inside the dialog and labels are bound to their inputs.
    assert page.evaluate("document.activeElement.closest('dialog') !== null")
    # The parent's scoped .modal-content styles must reach the <dialog> root (surface, sizing).
    bg = dialog.evaluate("d => getComputedStyle(d).backgroundColor")
    assert bg not in ("rgba(0, 0, 0, 0)", "transparent"), bg
    dialog.get_by_label("File Name").fill("x.csv")
    page.keyboard.press("Escape")
    dialog.wait_for(state="hidden", timeout=5000)
