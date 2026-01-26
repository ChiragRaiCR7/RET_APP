# login.py (RET v4) — Modern SaaS UI (final) with high contrast + theme-safe colors
# -----------------------------------------------------------------------------
# PURPOSE
#   Landing page for RETv4:
#     - Login (username/password)
#     - Persistent login (cookie token -> auth.get_login_session)
#     - Password reset requests + token-based password reset
#
# SECURITY NOTES
#   - Never log passwords or session tokens.
#   - Persistent login token is stored client-side; server validates token hash in DB.
# -----------------------------------------------------------------------------

from __future__ import annotations

import os
import secrets
from pathlib import Path

import streamlit as st
from streamlit_cookies_controller import CookieController

import auth as AUTH


# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="RETv4",
    layout="wide",
    page_icon="🔐",
    initial_sidebar_state="collapsed",
)

DEBUG = os.environ.get("RET_DEBUG", "0") == "1"
ENV = os.getenv("RET_ENV", "prod").lower()

COOKIE_SESSION_KEY = "ret_session"   # persistent login token (plaintext cookie)
COOKIE_SID_KEY = "sid"               # per-browser session id cookie

APP_DIR = Path(__file__).resolve().parent

# ✅ Portable hero image path (repo-relative)
# NOTE: Folder name kept as in your code: "Assests" (typo). Change if your repo uses "Assets".
HERO_IMAGE_LIGHT = APP_DIR / "Assests" / "Light_mode.png"
HERO_IMAGE_DARK = APP_DIR / "Assests" / "Dark_mode.png"  # optional; add for best results


# =========================================================
# MODERN SAAS INLINE CSS (UI only) — Final high-contrast version
# Requirements implemented:
# - Avoid fragile selectors (minimal BaseWeb/testid usage)
# - Strong focus-visible ring
# - Muted readable in dark mode
# - Reduced-motion support
# - Higher card solidity for contrast
# - Widget labels inherit theme tokens
# - Color-coded strength label classes
# =========================================================

RET_LOGIN_INLINE_CSS = r"""
/* =========================================================
   RETv4 Auth UI — Modern SaaS (High Contrast, Light/Dark)
   ========================================================= */

/* 1) TOKENS (LIGHT DEFAULT) */
:root{
  color-scheme: light;

  --brand:#FFC000;          
  --brand-700:#4338ca;
  --accent:#FFC000;         

  --bg:#f6f7ff;

  /* Solid-ish surfaces for contrast */
  --surface:#ffffff;
  --surface-2:#f4f6ff;
  --surface-3:rgba(79,70,229,.06);

  --text:#0f172a;
  --text-strong:#0b1220;
  --muted:#475569;          /* readable muted */

  --border: rgba(15,23,42,.12);
  --border-strong: rgba(15,23,42,.18);

  --shadow-sm: 0 12px 28px rgba(2, 6, 23, .08);
  --shadow-md: 0 22px 56px rgba(2, 6, 23, .12);

  --radius: 16px;
  --radius-lg: 22px;

  /* ✅ ONLY Verdana Pro Black */
  --font: "Verdana Pro Black";

  /* Stronger focus ring */
  --focus: rgba(79, 70, 229, .38);

  --input-bg: rgba(2, 6, 23, .05);
  --input-text: var(--text);
  --placeholder: rgba(71,85,105,.78);

  /* ✅ ALL buttons in FFC000 */
  --btn-bg: #FFC000;
  --btn-text: #000000;
  --btn-border: #FFC000;

  --btn-primary-bg: #FFC000;
  --btn-primary-text: #000000;
  --btn-primary-border: #FFC000;

  --pad-shell: 22px;
  --pad-card: 18px;
}

/* 2) TOKENS (DARK) */
@media (prefers-color-scheme: dark){
  :root{
    color-scheme: dark;

    --bg:#000000;

    --surface:#0b1220;
    --surface-2:#0f172a;
    --surface-3:rgba(99,102,241,.10);

    --text:#eaf0ff;
    --text-strong:#ffffff;

    /* boosted muted for readability in dark mode */
    --muted:#c3cce0;

    --border: rgba(255,255,255,.12);
    --border-strong: rgba(255,255,255,.18);

    --shadow-sm: 0 16px 36px rgba(0,0,0,.45);
    --shadow-md: 0 28px 64px rgba(0,0,0,.55);

    --focus: rgba(99,102,241,.46);

    --input-bg: #ffffff;
    --input-text: #000000;
    --placeholder: #000000;

    /* ✅ ALL buttons in FFC000 */
    --btn-bg: #FFC000;
    --btn-text: #000000;
    --btn-border: #FFC000;

    --btn-primary-bg:#FFC000;
    --btn-primary-border:#FFC000;
    --btn-primary-text:#000000;
  }
}

/* 3) BASE SURFACE */
html, body{
  font-family: var(--font) !important;
  background: var(--bg) !important;
  color: var(--text) !important;
}

/* ✅ Force Verdana Pro Black everywhere */
*,
.stApp,
.stApp *{
  font-family: var(--font) !important;
}

.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"]{
  background: var(--bg) !important;
  color: var(--text) !important;
}

/* Hide Streamlit chrome */
header, footer { visibility: hidden; height: 0; }
div[data-testid="stToolbar"] { visibility: hidden !important; }
button[title="Deploy this app"], [data-testid="stDeployButton"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
[data-testid="stSidebar"], [data-testid="stSidebarNav"] { display: none !important; }

/* IMPORTANT: User requested remove padding for block-container */
.block-container{
  max-width: 1180px;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
}

/* Text consistency */
[data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"] *{
  color: var(--text) !important;
}

/* Widget labels inherit theme tokens */
[data-testid="stWidgetLabel"] *{
  color: var(--text) !important;
  font-weight: 750 !important;
}

/* Caption text */
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] *{
  color: var(--muted) !important;
}

a, a:visited{ color: var(--accent) !important; }

/* 4) SAAS BACKDROP BLOBS */
.ret-backdrop{
  position: relative;
  overflow: hidden;
}

.ret-backdrop:before,
.ret-backdrop:after{
  content:"";
  position:absolute;
  width: 720px;
  height: 720px;
  border-radius: 999px;
  filter: blur(72px);
  opacity: .32;
  z-index: 0;
}
.ret-backdrop:before{
  top:-360px; left:-360px;
  background: radial-gradient(circle at 30% 30%, rgba(79,70,229,.95), transparent 60%);
}
.ret-backdrop:after{
  top:-360px; right:-380px;
  background: radial-gradient(circle at 30% 30%, rgba(6,182,212,.85), transparent 58%);
}

/* 5) SHELL (GLASS but high contrast) */
.auth-shell{
  position: relative;
  z-index: 1;
  margin: 0 auto;
  background: linear-gradient(180deg, rgba(255,255,255,.92), rgba(255,255,255,.82));
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  backdrop-filter: blur(10px);
}

@media (prefers-color-scheme: dark){
  .auth-shell{
    background: linear-gradient(180deg, rgba(15,23,42,.92), rgba(15,23,42,.82));
  }
}

/* 6) BRAND HEADER */
.brand-row{
  display:flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 14px;
  margin-bottom: 14px;
}
.brand-title{
  font-weight: 950;
  font-size: 2.15rem;
  line-height: 1.05;
  margin: 0;
  letter-spacing: -0.02em;
  color: var(--text-strong) !important;
}
.brand-title .accent{
  background: linear-gradient(90deg, var(--accent), var(--brand));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent !important;
}
.brand-subtitle{
  margin: .35rem 0 0 0;
  font-weight: 650;
  color: var(--muted) !important;
}
.brand-badge{
  display:inline-flex;
  align-items:center;
  gap: 8px;
  font-size: .85rem;
  font-weight: 900;
  border-radius: 999px;
  background: var(--surface);
  color: var(--text) !important;
}
@media (prefers-color-scheme: dark){
  .brand-badge{
    background: rgba(255,255,255,.06);
  }
}

/* 7) HERO + CARD (more solid / higher contrast) */
.auth-hero{
  background:
    radial-gradient(650px 280px at 12% 10%, rgba(79,70,229,.16), transparent 60%),
    radial-gradient(700px 280px at 92% 0%, rgba(6,182,212,.12), transparent 60%),
    linear-gradient(180deg, rgba(245,158,11,.06), var(--surface));
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  height: 100%;
}

.auth-card{
  background: var(--surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
}
/* Hero image */
div[data-testid="stImage"] img{
  width: 100% !important;
  height: auto !important;
  border-radius: 18px;
  box-shadow: var(--shadow-sm);
  object-fit: cover;
}

/* Card header */
.card-header{
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap: 10px;
  margin-bottom: 10px;
}
.card-title{
  font-weight: 950;
  font-size: 1.18rem;
  margin: 0;
  letter-spacing: -0.01em;
  color: var(--text-strong) !important;
}
.card-hint{
  margin-top: 2px;
  font-size: .92rem;
  color: var(--muted) !important;
}

/* 8) INPUTS / BUTTONS / FOCUS */
div[data-baseweb="input"] input,
div[data-baseweb="textarea"] textarea{
  background: var(--input-bg) !important;
  color: var(--input-text) !important;
  border-radius: 14px !important;
}
div[data-baseweb="input"] input::placeholder,
div[data-baseweb="textarea"] textarea::placeholder{
  color: var(--placeholder) !important;
}

/* Strong focus ring */
div[data-baseweb="input"] input:focus,
div[data-baseweb="textarea"] textarea:focus,
button:focus-visible,
a:focus-visible{
  outline: 3px solid var(--focus) !important;
  outline-offset: 2px !important;
  border-radius: 12px;
}

/* Buttons */
div[data-testid="stButton"] > button,
.stButton > button{
  border-radius: 14px !important;
  font-weight: 950 !important;
  background: var(--btn-bg) !important;
  color: var(--btn-text) !important;
  transition: transform .10s ease, box-shadow .18s ease, border-color .18s ease;
}

div[data-testid="stButton"] > button:hover{
  transform: translateY(-1px);
  box-shadow: 0 12px 26px rgba(2,6,23,.12);
  border-color: rgba(99,102,241,.35);
}

/* ✅ Primary buttons also solid #FFC000 (no gradient) */

div[data-testid="stButton"] > button[kind="primary"],
.stButton > button[kind="primary"]{
  background: var(--btn-primary-bg) !important;
  border-color: var(--btn-primary-border) !important;
  color: var(--btn-primary-text) !important;
}


div[data-testid="stButton"] > button:disabled{
  opacity: .55 !important;
  cursor: not-allowed !important;
  transform: none !important;
  box-shadow: none !important;
}

/* Tabs (pill segmented) */
div[data-baseweb="tab-list"]{
  gap: 8px !important;
  border-radius: 999px !important;
  background: rgba(255,255,255,.55) !important;
}
@media (prefers-color-scheme: dark){
  div[data-baseweb="tab-list"]{
    background: rgba(255,255,255,.06) !important;
  }
}
button[data-baseweb="tab"]{
  border-radius: 999px !important;
  font-weight: 950 !important;
  color: var(--text) !important;
}
button[data-baseweb="tab"][aria-selected="true"]{
  background: var(--surface-3) !important;
}

/* Strength meter */
.ret-meter{
  width: 100%;
  height: 10px;
  border-radius: 999px;
  background: rgba(2,6,23,.10);
  overflow:hidden;
}
@media (prefers-color-scheme: dark){
  .ret-meter{ background: rgba(255,255,255,.10); }
}
.ret-meter > div{
  height: 100%;
  width: 0%;
  border-radius: 999px;
  background: linear-gradient(90deg, #ef4444, #f59e0b, #22c55e);
  transition: width .22s ease;
}

/* Color-coded strength label */
.pw-weak{ color:#ef4444 !important; font-weight: 900; }
.pw-fair{ color:#f59e0b !important; font-weight: 900; }
.pw-good{ color:#3b82f6 !important; font-weight: 900; }
.pw-strong{ color:#22c55e !important; font-weight: 900; }

/* Footer */
.ret-footer{
  margin-top: 16px;
  padding-top: 12px;
  text-align: center;
  color: var(--muted) !important;
  font-size: 0.92rem;
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce){
  *{ transition: none !important; animation: none !important; }
}

/* Responsive */
@media (max-width: 900px){
  .auth  .auth-shell{
    padding: 16px;
  }
}
"""



def _load_css():
    try:
        st.markdown(f"<style>{RET_LOGIN_INLINE_CSS}</style>", unsafe_allow_html=True)
    except Exception:
        pass


_load_css()


# =========================================================
# INIT DB (one-time)
# =========================================================
@st.cache_resource(show_spinner=False)
def _init_db_once():
    AUTH.init_db()


_init_db_once()


# =========================================================
# Optional: Create demo users only in dev (if available)
# =========================================================
if ENV == "dev" and hasattr(AUTH, "create_demo_users"):
    try:
        AUTH.create_demo_users()
    except Exception:
        st.toast("Demo users not created.", icon="⚠️")


# =========================================================
# Navigation candidates (robust multipage switching)
# =========================================================
ADMIN_PAGE_CANDIDATES = [
    "pages/admin.py",
    "pages/Admin.py",
    "Admin.py",
    "admin.py",
]

MAIN_PAGE_CANDIDATES = [
    "pages/main.py",
    "pages/Main.py",
    "pages/App.py",
    "pages/app.py",
    "main.py",
    "App.py",
]


def _safe_switch_page(candidates: list[str]) -> bool:
    """Try switching to any candidate page; return True if succeeded."""
    for t in candidates:
        try:
            st.switch_page(t)
            return True
        except Exception:
            continue
    return False


def _safe_switch_post_login(user_tuple):
    """
    user_tuple expected: (id, username, role) OR dict-like.
    If admin -> go admin page (if exists), else main.
    """
    role = ""
    try:
        if isinstance(user_tuple, (list, tuple)) and len(user_tuple) >= 3:
            role = str(user_tuple[2] or "").lower()
        elif isinstance(user_tuple, dict):
            role = str(user_tuple.get("role") or "").lower()
    except Exception:
        role = ""

    if role in ("admin", "superadmin"):
        if _safe_switch_page(ADMIN_PAGE_CANDIDATES):
            return
        _safe_switch_page(MAIN_PAGE_CANDIDATES)
    else:
        _safe_switch_page(MAIN_PAGE_CANDIDATES)


# =========================================================
# Cookie helpers
# =========================================================
def get_cookie_controller() -> CookieController:
    """Reuse a single CookieController instance per session."""
    if "_cookie_controller" not in st.session_state:
        st.session_state["_cookie_controller"] = CookieController()
    return st.session_state["_cookie_controller"]


def _ensure_sid_cookie(controller: CookieController) -> str:
    """Ensure sid cookie exists (per browser session identifier)."""
    sid = None
    try:
        sid = st.context.cookies.get(COOKIE_SID_KEY)
    except Exception:
        sid = None

    if not sid:
        try:
            sid = controller.get(COOKIE_SID_KEY)
        except Exception:
            sid = None

    if not sid:
        sid = secrets.token_hex(16)[:16]
        try:
            controller.set(COOKIE_SID_KEY, sid)
        except Exception:
            pass

    return str(sid)


def _clear_auth_cookies(controller: CookieController):
    """Clear auth cookies (token + sid) best-effort."""
    for k in (COOKIE_SESSION_KEY, COOKIE_SID_KEY):
        try:
            controller.set(k, "", max_age=0)
        except Exception:
            pass
        try:
            controller.set(k, None, max_age=0)
        except Exception:
            pass


# =========================================================
# Session state defaults
# =========================================================
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None

if "prefill_reset_username" not in st.session_state:
    st.session_state.prefill_reset_username = ""


# =========================================================
# Controller init + sid cookie ensure
# =========================================================
controller = get_cookie_controller()
_ = _ensure_sid_cookie(controller)

if DEBUG:
    st.caption(f"auth.py loaded from: {getattr(AUTH, '__file__', 'unknown')}")
# =========================================================
# Operational logging helpers (safe: do NOT log secrets/tokens/passwords)
# =========================================================
def _ops(
    level: str,
    action: str,
    username: str | None = None,
    message: str | None = None,
    details: dict | None = None,
):
    """Call AUTH.ops safely if available (auth.py has sanitized ops wrapper)."""
    try:
        if hasattr(AUTH, "ops"):
            AUTH.ops(level=level, action=action, username=username, message=message, details=details or {}, area="LOGIN")
    except Exception:
        pass


# =========================================================
# UI-ONLY Password strength meter (no security enforcement)
# =========================================================
def password_strength(pw: str) -> tuple[int, str, list[str]]:
    """
    UI-only strength score (0..100) + label + tips.
    This does NOT replace AUTH.validate_password().
    """
    pw = pw or ""
    tips: list[str] = []
    length = len(pw)
    has_lower = any(c.islower() for c in pw)
    has_upper = any(c.isupper() for c in pw)
    has_digit = any(c.isdigit() for c in pw)
    has_special = any(not c.isalnum() for c in pw)

    length_score = min(length, 12) * 5  # 0..60
    variety_score = (10 if has_lower else 0) + (10 if has_upper else 0) + (10 if has_digit else 0) + (10 if has_special else 0)
    score = max(0, min(100, length_score + variety_score))

    if length < 8:
        tips.append("Use at least 8 characters.")
    if not has_upper:
        tips.append("Add an uppercase letter (A–Z).")
    if not has_lower:
        tips.append("Add a lowercase letter (a–z).")
    if not has_digit:
        tips.append("Add a number (0–9).")
    if not has_special:
        tips.append("At least one special character `!@#$%^&*(),.?':{}|<>`.")

    if score < 35:
        label = "Weak"
    elif score < 60:
        label = "Fair"
    elif score < 80:
        label = "Good"
    else:
        label = "Strong"

    return score, label, tips


def _render_strength_meter(score: int):
    """Modern SaaS style strength meter bar (UI only)."""
    safe = max(0, min(100, int(score)))
    st.markdown(
        f"""
        <div class="ret-meter" aria-label="Password strength">
          <div style="width:{safe}%;"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _strength_class(label: str) -> str:
    return {
        "Weak": "pw-weak",
        "Fair": "pw-fair",
        "Good": "pw-good",
        "Strong": "pw-strong",
    }.get(label, "pw-fair")


# =========================================================
# Persistent cookie login (token -> auth.get_login_session)
# =========================================================
existing_token = None
try:
    existing_token = st.context.cookies.get(COOKIE_SESSION_KEY)
except Exception:
    existing_token = None

if not existing_token:
    try:
        existing_token = controller.get(COOKIE_SESSION_KEY)
    except Exception:
        existing_token = None

# Attempt session restore
if st.session_state.auth_user is None and existing_token:
    if hasattr(AUTH, "get_login_session"):
        try:
            user_tuple = AUTH.get_login_session(existing_token)
        except Exception:
            user_tuple = None

        if user_tuple:
            st.session_state.auth_user = user_tuple
            _ops("INFO", "cookie_login_success", username=str(user_tuple[1]), message="Persistent cookie login succeeded")
            _safe_switch_post_login(user_tuple)
            st.stop()
        else:
            _ops("WARN", "cookie_login_failed", message="Persistent cookie login failed; clearing cookies")
            _clear_auth_cookies(controller)
    else:
        st.warning("Persistent login unavailable because `get_login_session` is missing in auth.py.")

# Already logged in
if st.session_state.auth_user is not None:
    _safe_switch_post_login(st.session_state.auth_user)
    st.stop()


# =========================================================
# UI
# =========================================================
st.markdown('<div class="ret-backdrop">', unsafe_allow_html=True)
st.markdown('<div class="auth-shell">', unsafe_allow_html=True)

# Brand header
st.markdown(
    """
    <div class="brand-row">
      <div>
        <div class="brand-title">RET<span class="accent">v4</span></div>
        <div class="brand-subtitle">Secure enterprise access • XML conversion workspace</div>
      </div>
      <div class="brand-badge">🔒 Session secured</div>
    </div>
    """,
    unsafe_allow_html=True
)

left, right = st.columns([1.7, 1], gap="large")

# ---------------------------------------------------------
# Hero Panel
# ---------------------------------------------------------
with left:
    st.markdown('<div class="auth-hero">', unsafe_allow_html=True)

    hero_path = HERO_IMAGE_LIGHT if HERO_IMAGE_LIGHT.exists() else HERO_IMAGE_DARK
    if hero_path and hero_path.exists():
        st.image(str(hero_path), use_container_width=True)
    else:
        st.warning(f"Hero image not found. Expected: {HERO_IMAGE_LIGHT} (or optional {HERO_IMAGE_DARK})")

    st.markdown(
        """
        <h3 style="margin-top: 14px; letter-spacing: -0.01em;">ZIP → XML → CSV/XLSX</h3>
        <p style="margin-top: -6px;">
          Upload ZIPs containing XML files, convert at scale, preview results and download outputs —
          with session-based AI assistance.
        </p>
        <div style="display:flex; gap:10px; flex-wrap:wrap; margin-top: 10px;">
          <span class="brand-badge">⚡ Fast conversions</span>
          <span class="brand-badge">🧾 Audit-friendly logs</span>
          <span class="brand-badge">📦 Bulk ZIP support</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.info("🔒 Account creation is **restricted to administrators**.\nContact your admin.")
    st.markdown("</div>", unsafe_allow_html=True)  # close auth-hero
# ---------------------------------------------------------
# Auth Card (Tabs + Forms)
# ---------------------------------------------------------
with right:
    st.markdown('<div class="auth-card">', unsafe_allow_html=True)

    tabs = st.tabs(["Login", "Reset Password"])

# =========================
# Login Tab
# =========================
with tabs[0]:
    st.markdown(
        """
        <div class="card-header">
          <div>
            <div class="card-title">Sign in</div>
            <div class="card-hint">Use your enterprise credentials</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    with st.form("login_form", clear_on_submit=False, border=False):
        username_input = st.text_input("Username", placeholder="Enter your username", key="login_username")
        password = st.text_input("Password", type="password", placeholder="Enter your password", key="login_password")

        # ✅ Keep 'remember me' in a single row using columns (unpacked correctly)
        c1, c2 = st.columns([1, 1])
        with c1:
            remember = st.checkbox("Keep me signed in", value=True, key="remember_me")

        # You can use the right column for spacing or future items
        with c2:
            st.write("")  # spacer (optional)

        submitted = st.form_submit_button("Login", type="primary", use_container_width=True)

    if submitted:
        username = (username_input or "").strip().lower()
        _ops("INFO", "login_attempt", username=username, message="Login attempt started")

        try:
            with st.spinner("Signing you in…"):
                user = AUTH.verify_user(username, password)

            if user:
                st.session_state.auth_user = user

                # Persistent login cookie only if remember enabled
                if remember and hasattr(AUTH, "create_login_session"):
                    try:
                        cookie_token = AUTH.create_login_session(user[1])
                        ttl = int(os.getenv("TOKEN_EXPIRY_SECONDS", "86400"))
                        try:
                            controller.set(COOKIE_SESSION_KEY, cookie_token, max_age=ttl)
                        except Exception:
                            pass
                    except Exception:
                        _ops("WARN", "login_cookie_set_failed", username=user[1],
                             message="Failed to set persistent login cookie")

                _ops("INFO", "login_success_ui", username=user[1], message="UI login succeeded")
                st.success(f"Welcome, {user[1]}!")
                _safe_switch_post_login(user)
                st.stop()

            # Generic failure
            _ops("WARN", "login_failed_ui", username=username, message="UI login failed")
            st.error("Invalid credentials or account unavailable.")
            st.info("If you are onboarding or locked out, use **Reset Password** with your admin-provided token.")

        except Exception as e:
            _ops("ERROR", "login_error_ui", username=username, message=str(e)[:400])
            st.error("Login failed. Please try again or contact admin.")

    # =========================
    # Reset Password Tab
    # =========================
    with tabs[1]:
        st.markdown(
            """
            <div class="card-header">
              <div>
                <div class="card-title">Reset password</div>
                <div class="card-hint">Request a reset or use an admin token</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        default_uname = st.session_state.get("prefill_reset_username", "")
        reset_username_input = st.text_input(
            "Username",
            value=default_uname,
            placeholder="Your username",
            key="reset_username",
        )
        reset_username = (reset_username_input or "").strip().lower()

        # Reset request form
        with st.form("reset_request_form", clear_on_submit=False, border=False):
            st.caption("No token yet? Submit a request and your admin will send one.")
            req_submit = st.form_submit_button("Request Password Reset", use_container_width=True)

        if req_submit:
            _ops("INFO", "reset_request_attempt", username=reset_username, message="Reset request attempt")
            try:
                with st.spinner("Submitting request…"):
                    req_id = AUTH.create_reset_request(reset_username)
                _ops("INFO", "reset_request_created", username=reset_username, message="Reset request created", details={"request_id": req_id})
                st.info(f"📨 Request submitted (ID: {req_id}). Admin will review and send you a reset token.")
                st.toast("Reset request sent to admin.", icon="📨")
            except Exception as e:
                _ops("WARN", "reset_request_failed", username=reset_username, message=str(e)[:400])
                st.error("Failed to submit request. Please try again later or contact admin.")

        st.divider()
        st.markdown("**Have a token? Set a new password below:**")

        show_pw2 = st.checkbox("Show new password", value=False, key="show_pw_reset")

        new_pw = st.text_input(
            "New Password",
            type="default" if show_pw2 else "password",
            placeholder="Create a strong password",
            key="reset_new_pw",
        )

        # ✅ Only show strength meter when input has content
        if (new_pw or "").strip():
            score, label, tips = password_strength(new_pw)
            _render_strength_meter(score)

            cls = _strength_class(label)
            st.markdown(
                f'Password strength: <span class="{cls}">{label}</span>  •  {score}/100',
                unsafe_allow_html=True,
            )

            # Tips (subtle)
            if tips:
                st.caption("• " + "\n• ".join(tips))

        token_input = st.text_input(
            "Reset Token (provided by admin)",
            placeholder="Paste the admin-provided token here",
            key="reset_token",
        )
        # Token-based reset
        if st.button("Update Password", type="primary", key="btn_update_pw", use_container_width=True):
            clean_username = (reset_username or "").strip().lower()
            clean_token = (token_input or "").strip()

            if not clean_username:
                st.error("Please provide your username.")
            elif not clean_token:
                st.error("Please provide the reset token.")
            elif not hasattr(AUTH, "validate_password"):
                st.error("Password policy validator missing in auth.py (`validate_password`).")
            elif not AUTH.validate_password(new_pw or ""):
                st.error("Password does not meet security requirements.")
            else:
                _ops("INFO", "reset_password_attempt", username=clean_username, message="Reset password attempt")
                try:
                    with st.spinner("Updating password…"):
                        if hasattr(AUTH, "reset_password_verbose"):
                            ok, reason = AUTH.reset_password_verbose(clean_username, new_pw, clean_token)
                            if ok:
                                _ops("INFO", "reset_password_success", username=clean_username, message="Password reset succeeded")
                                st.success("Password updated successfully! Please login.")
                                st.session_state.prefill_reset_username = ""
                                st.toast("Password has been updated.", icon="✅")
                                st.rerun()
                            else:
                                msg_map = {
                                    "policy": "Password does not meet security requirements.",
                                    "no_token_row": "No active token found for this username.",
                                    "expired": "This token has expired. Ask your admin to generate a new one.",
                                    "token_mismatch": "Token does not match. Remove spaces/newlines and try again.",
                                    "user_missing": "User not found.",
                                    "used": "This token was already used. Ask admin to generate a new one.",
                                    "token_missing": "Token is required.",
                                }
                                _ops("WARN", "reset_password_failed", username=clean_username, message=f"Reset failed: {reason}")
                                st.error(f"Reset failed: {msg_map.get(reason, reason)}")
                                st.info("Tip: Ensure the username matches the token’s owner and remove spaces/newlines from the token.")
                        else:
                            if not hasattr(AUTH, "reset_password"):
                                st.error("Password reset function missing in auth.py (`reset_password`).")
                                st.stop()

                            success = AUTH.reset_password(clean_username, new_pw, clean_token)
                            if success:
                                _ops("INFO", "reset_password_success", username=clean_username, message="Password reset succeeded (fallback)")
                                st.success("Password updated successfully! Please login.")
                                st.session_state.prefill_reset_username = ""
                                st.toast("Password has been updated.", icon="✅")
                                st.rerun()
                            else:
                                _ops("WARN", "reset_password_failed", username=clean_username, message="Reset failed (fallback)")
                                st.error("Reset failed: invalid token or expired.")
                                st.info("Tip: Ensure the username matches the token’s owner and remove spaces/newlines from the token.")
                except Exception as e:
                    _ops("ERROR", "reset_password_error", username=clean_username, message=str(e)[:400])
                    st.error("Failed to update password. Please try again or contact admin.")

    st.markdown("</div>", unsafe_allow_html=True)  # close auth-card

# Footer
st.markdown(
    '<div class="ret-footer">Copyright 2025 TATA Consultancy Services Limited | All Rights reserved • RETv4</div>',
    unsafe_allow_html=True
)

# ✅ Close wrappers properly (verified)
st.markdown("</div>", unsafe_allow_html=True)  # close auth-shell