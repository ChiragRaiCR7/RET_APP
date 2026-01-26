# admin.py (RET v4 — Professional Enterprise Admin Console)
# ----------------------------------------------------------------------------- 
# PURPOSE
#   Enterprise-grade admin console with professional UI/UX
#   Features:
#     - Token-first user onboarding with CRUD operations
#     - Password reset request approvals
#     - Comprehensive audit and operational logging
#     - Session registry monitoring with cleanup automation
#     - AI-powered admin agent with tool calling
#
# DESIGN: Professional enterprise interface with RETv4 brand identity
# ----------------------------------------------------------------------------- 

from __future__ import annotations

import os
import re
import math
import time
import json
import shutil
import hashlib
import random
import threading
from pathlib import Path
from typing import Any, Optional, Dict, List, Tuple, cast
from contextlib import contextmanager

from sqlalchemy import select

import streamlit as st
import pandas as pd

# Optional third-party helpers with safe fallbacks
_AUTOREFRESH_AVAILABLE = False
st_autorefresh = None
try:
    from streamlit_autorefresh import st_autorefresh  # type: ignore
    _AUTOREFRESH_AVAILABLE = True
except Exception:
    def st_autorefresh(interval: int = 60_000, key: str = "") -> None:  # no-op fallback
        return None

_COOKIES_AVAILABLE = False
CookieController: Optional[Any] = None
try:
    from streamlit_cookies_controller import CookieController  # type: ignore
    _COOKIES_AVAILABLE = True
except Exception:
    class CookieController:  # type: ignore # noqa: F811
        """Minimal fallback cookie controller."""
        def __init__(self) -> None:
            self._prefix = "_ret_cookie_"
        
        def _key(self, name: str) -> str:
            return f"{self._prefix}{name}"
        
        def get(self, name: str) -> Optional[str]:
            return st.session_state.get(self._key(name))
        
        def set(self, name: str, value: str, max_age: int = 0) -> None:
            st.session_state[self._key(name)] = value

import auth as AUTH
from db import get_session, write_ops_log, write_error_event
from models import AppSession


# =========================================================
# Azure OpenAI (Admin Agent)
# =========================================================
_AOAI_AVAILABLE = False
AzureOpenAI: Optional[Any] = None
try:
    from openai import AzureOpenAI  # type: ignore
    _AOAI_AVAILABLE = True
except Exception:
    AzureOpenAI = None
    _AOAI_AVAILABLE = False


# =========================================================
# Page Configuration
# =========================================================
st.set_page_config(
    page_title="RET v4 — Admin Console",
    layout="wide",
    page_icon="🛡️",
    initial_sidebar_state="collapsed",
)

DEBUG = os.environ.get("RET_DEBUG", "0") == "1"
COOKIE_SESSION_KEY = "ret_session"
COOKIE_SID_KEY = "sid"
IDLE_CLEANUP_SECONDS_DEFAULT = int(os.environ.get("RET_IDLE_CLEANUP_SECONDS", str(60 * 60)))


# =========================================================
# Thread-safe locks (standardized with main.py)
# =========================================================
_SESSION_CLEANUP_LOCK = threading.Lock()
_COOKIE_LOCK = threading.Lock()
_DB_POOL_LOCK = threading.Lock()


# =========================================================
# Correlation IDs (Standardized)
# =========================================================
def get_corr_id(prefix: str = "admin") -> str:
    """Generate a unique correlation ID for tracing."""
    ts = str(int(time.time() * 1000))[-6:]
    rand = str(random.randint(100000, 999999))
    return f"{prefix}_{ts}_{rand}"


def new_action_cid(action: str) -> str:
    """Create a correlation ID for a new admin action."""
    safe_action = re.sub(r"[^a-z0-9_]", "_", action.lower())[:20]
    return get_corr_id(safe_action)


def child_cid(parent: str, suffix: str) -> str:
    """Derive a child correlation ID from a parent ID."""
    safe_suffix = re.sub(r"[^a-z0-9_]", "_", suffix.lower())[:10]
    return f"{parent}_{safe_suffix}"


# =========================================================
# Security: Filesystem Path Allowlisting
# =========================================================
RET_RUNTIME_ROOT = Path(os.environ.get("RET_RUNTIME_ROOT", str(Path.cwd() / "ret_runtime"))).resolve()
RET_SESS_ROOT = (RET_RUNTIME_ROOT / "sessions").resolve()
RET_LOG_ROOT = (RET_RUNTIME_ROOT / "logs").resolve()


def _is_under(child: Path, parent: Path) -> bool:
    """Verify if child path is under parent directory (security check)."""
    try:
        child = child.resolve()
        parent = parent.resolve()
        return str(child).startswith(str(parent) + os.sep)
    except Exception:
        return False


def _safe_delete_dir_allowlisted(p: str) -> bool:
    """Delete directory only if under allowed sessions root."""
    try:
        if not p:
            return True
        target = Path(p).resolve()
        if not _is_under(target, RET_SESS_ROOT):
            return False
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        return True
    except Exception:
        return False


def _safe_read_log_allowlisted(p: str) -> bytes:
    """Read log file only if under allowed logs root."""
    target = Path(p).resolve()
    if not _is_under(target, RET_LOG_ROOT):
        raise PermissionError("Log path is outside allowed directory")
    if not target.exists():
        raise FileNotFoundError("Log file not found")
    return target.read_bytes()


# =========================================================
# Safe display sanitizer (aligned with main.py)
# =========================================================
def safe_display(s: Optional[str], max_len: int = 300) -> str:
    """Sanitize text for safe display (prevent injection/overflow)."""
    if not s:
        return ""
    text = str(s).replace("\r", "\\r").replace("\n", "\\n")
    return text[:max_len]


# =========================================================
# PROFESSIONAL ENTERPRISE CSS THEME
# =========================================================
RET_ADMIN_PROFESSIONAL_CSS = r"""
/* ========================================================================
   RETv4 Admin Console — Professional Enterprise Design System
   ======================================================================== */

/* -------------------- Design Tokens -------------------- */
:root {
  color-scheme: light;

  /* Brand Identity (RETv4) */
  --brand-primary: #FFC000;
  --brand-secondary: #E6AC00;
  --brand-light: #FFD147;
  --brand-glow: rgba(255, 192, 0, 0.2);
  --brand-subtle: rgba(255, 192, 0, 0.08);

  /* Surface Layers */
  --bg-primary: #f5f7fa;
  --bg-secondary: #e8ecf1;
  --surface-base: #ffffff;
  --surface-elevated: #ffffff;
  --surface-hover: #f8f9fc;
  --surface-active: #f0f3f7;
  --surface-overlay: rgba(0, 0, 0, 0.02);

  /* Text Hierarchy */
  --text-heading: #1a202c;
  --text-body: #2d3748;
  --text-secondary: #4a5568;
  --text-tertiary: #718096;
  --text-placeholder: #a0aec0;
  --text-disabled: #cbd5e0;
  --text-inverse: #ffffff;

  /* Semantic Colors */
  --success: #10b981;
  --success-bg: #d1fae5;
  --success-border: #6ee7b7;
  --warning: #f59e0b;
  --warning-bg: #fef3c7;
  --warning-border: #fcd34d;
  --error: #ef4444;
  --error-bg: #fee2e2;
  --error-border: #fca5a5;
  --info: #3b82f6;
  --info-bg: #dbeafe;
  --info-border: #93c5fd;

  /* Borders & Dividers */
  --border-light: rgba(0, 0, 0, 0.06);
  --border-medium: rgba(0, 0, 0, 0.10);
  --border-strong: rgba(0, 0, 0, 0.15);
  --border-accent: var(--brand-primary);

  /* Shadows (Elevation System) */
  --shadow-xs: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  --shadow-sm: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px -1px rgba(0, 0, 0, 0.1);
  --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1);
  --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1);
  --shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
  --shadow-2xl: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
  --shadow-brand: 0 10px 30px -5px var(--brand-glow);

  /* Border Radius */
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 14px;
  --radius-xl: 18px;
  --radius-2xl: 24px;
  --radius-full: 9999px;

  /* Spacing Scale */
  --space-xs: 8px;
  --space-sm: 12px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --space-2xl: 48px;
  --space-3xl: 64px;

  /* Typography */
  --font-display: "Verdana Pro Black", "Verdana", -apple-system, system-ui, sans-serif;
  --font-body: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --font-mono: "SF Mono", "Monaco", "Inconsolata", "Fira Code", "Courier New", monospace;

  /* Transitions */
  --transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-base: 200ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-slow: 300ms cubic-bezier(0.4, 0, 0.2, 1);

  /* Focus Ring */
  --focus-ring: 0 0 0 3px var(--brand-glow);
  --focus-ring-error: 0 0 0 3px rgba(239, 68, 68, 0.2);
}

/* Dark Mode Tokens */
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;

    --bg-primary: #0d1117;
    --bg-secondary: #161b22;
    --surface-base: #161b22;
    --surface-elevated: #1c2128;
    --surface-hover: #21262d;
    --surface-active: #2d333b;
    --surface-overlay: rgba(255, 255, 255, 0.04);

    --text-heading: #f0f6fc;
    --text-body: #e6edf3;
    --text-secondary: #adbac7;
    --text-tertiary: #768390;
    --text-placeholder: #636e7b;
    --text-disabled: #545d68;

    --border-light: rgba(255, 255, 255, 0.08);
    --border-medium: rgba(255, 255, 255, 0.12);
    --border-strong: rgba(255, 255, 255, 0.18);

    --shadow-xs: 0 1px 2px 0 rgba(0, 0, 0, 0.5);
    --shadow-sm: 0 1px 3px 0 rgba(0, 0, 0, 0.6), 0 1px 2px -1px rgba(0, 0, 0, 0.6);
    --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.7), 0 2px 4px -2px rgba(0, 0, 0, 0.7);
    --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.8), 0 4px 6px -4px rgba(0, 0, 0, 0.8);
    --shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.9), 0 8px 10px -6px rgba(0, 0, 0, 0.9);
    
    --success-bg: rgba(16, 185, 129, 0.15);
    --warning-bg: rgba(245, 158, 11, 0.15);
    --error-bg: rgba(239, 68, 68, 0.15);
    --info-bg: rgba(59, 130, 246, 0.15);
  }
}

/* -------------------- Base Styles -------------------- */
html, body {
  background: var(--bg-primary) !important;
  color: var(--text-body) !important;
  font-family: var(--font-body) !important;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  line-height: 1.6;
  font-size: 15px;
}

*, *::before, *::after {
  box-sizing: border-box;
}

/* Hide Streamlit Chrome */
header, footer { visibility: hidden; height: 0; }
div[data-testid="stToolbar"],
button[title="Deploy this app"],
[data-testid="stDeployButton"],
[data-testid="collapsedControl"],
[data-testid="stSidebar"],
[data-testid="stSidebarNav"] {
  display: none !important;
}

.block-container {
  max-width: 1520px !important;
  padding: var(--space-xl) var(--space-lg) var(--space-3xl) !important;
}

/* -------------------- Header Component -------------------- */
.admin-header {
  background: var(--surface-elevated);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xl);
  padding: var(--space-xl);
  margin-bottom: var(--space-2xl);
  box-shadow: var(--shadow-md);
  position: relative;
  overflow: hidden;
}

.admin-header::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: linear-gradient(90deg, var(--brand-primary) 0%, var(--brand-light) 100%);
}

.header-grid {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: var(--space-lg);
  align-items: center;
}

.brand-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.brand-title {
  font-family: var(--font-display) !important;
  font-size: 2.25rem;
  font-weight: 900;
  letter-spacing: -0.025em;
  margin: 0;
  color: var(--text-heading);
}

.brand-accent {
  background: linear-gradient(135deg, var(--brand-primary), var(--brand-light));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.brand-subtitle {
  color: var(--text-secondary);
  font-size: 0.95rem;
  font-weight: 600;
  margin: 0;
}

.user-info {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  background: var(--brand-subtle);
  border: 1px solid var(--brand-primary);
  border-radius: var(--radius-full);
  padding: var(--space-sm) var(--space-lg);
  font-weight: 700;
  color: var(--text-body);
}

.user-avatar {
  width: 32px;
  height: 32px;
  background: linear-gradient(135deg, var(--brand-primary), var(--brand-light));
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  color: #000;
  font-weight: 900;
}

/* -------------------- Card Components -------------------- */
.enterprise-card {
  background: var(--surface-elevated);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: var(--space-lg);
  margin-bottom: var(--space-lg);
  box-shadow: var(--shadow-sm);
  transition: all var(--transition-base);
}

.enterprise-card:hover {
  box-shadow: var(--shadow-md);
  border-color: var(--border-medium);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: var(--space-md);
  margin-bottom: var(--space-lg);
  border-bottom: 2px solid var(--border-light);
}

.card-icon {
  font-size: 1.5rem;
  margin-right: var(--space-sm);
}

.card-title-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.card-title {
  font-size: 1.25rem;
  font-weight: 800;
  color: var(--text-heading);
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.card-description {
  color: var(--text-tertiary);
  font-size: 0.875rem;
  margin: 0;
}

/* -------------------- Buttons -------------------- */
div[data-testid="stButton"] > button,
.stButton > button {
  border-radius: var(--radius-md) !important;
  font-weight: 700 !important;
  font-size: 0.9375rem !important;
  padding: 11px 22px !important;
  border: 1px solid transparent !important;
  box-shadow: var(--shadow-sm);
  transition: all var(--transition-base);
  font-family: var(--font-body) !important;
  cursor: pointer;
}

/* Primary Button */
div[data-testid="stButton"] > button[kind="primary"],
.stButton > button[kind="primary"] {
  background: linear-gradient(135deg, var(--brand-primary) 0%, var(--brand-secondary) 100%) !important;
  color: #000000 !important;
  border-color: var(--brand-primary) !important;
}

div[data-testid="stButton"] > button[kind="primary"]:hover:not(:disabled) {
  box-shadow: var(--shadow-md), var(--shadow-brand);
  transform: translateY(-2px);
}

div[data-testid="stButton"] > button[kind="primary"]:active:not(:disabled) {
  transform: translateY(0);
  box-shadow: var(--shadow-sm);
}

/* Secondary Button */
div[data-testid="stButton"] > button[kind="secondary"],
.stButton > button[kind="secondary"] {
  background: var(--surface-base) !important;
  color: var(--text-body) !important;
  border: 1px solid var(--border-medium) !important;
}

div[data-testid="stButton"] > button[kind="secondary"]:hover:not(:disabled) {
  background: var(--surface-hover) !important;
  border-color: var(--border-strong) !important;
  box-shadow: var(--shadow-md);
}

/* Disabled State */
div[data-testid="stButton"] > button:disabled {
  opacity: 0.5 !important;
  cursor: not-allowed !important;
  transform: none !important;
  box-shadow: none !important;
}

/* -------------------- Form Inputs -------------------- */
div[data-baseweb="input"] input,
div[data-baseweb="textarea"] textarea,
div[data-baseweb="select"] select,
.stNumberInput input,
.stTextInput input,
.stTextArea textarea {
  background: var(--surface-base) !important;
  color: var(--text-body) !important;
  border: 1px solid var(--border-medium) !important;
  border-radius: var(--radius-md) !important;
  padding: 11px 15px !important;
  font-size: 0.9375rem !important;
  font-family: var(--font-body) !important;
  transition: all var(--transition-fast);
  box-shadow: var(--shadow-xs);
}

div[data-baseweb="input"] input:hover,
div[data-baseweb="textarea"] textarea:hover,
.stNumberInput input:hover,
.stTextInput input:hover {
  border-color: var(--border-strong) !important;
  box-shadow: var(--shadow-sm);
}

div[data-baseweb="input"] input:focus,
div[data-baseweb="textarea"] textarea:focus,
.stNumberInput input:focus,
.stTextInput input:focus {
  border-color: var(--brand-primary) !important;
  box-shadow: var(--focus-ring), var(--shadow-sm);
  outline: none !important;
}

div[data-baseweb="input"] input::placeholder,
div[data-baseweb="textarea"] textarea::placeholder {
  color: var(--text-placeholder) !important;
}

/* Input Labels */
[data-testid="stWidgetLabel"] label,
[data-testid="stWidgetLabel"] > div {
  color: var(--text-secondary) !important;
  font-weight: 700 !important;
  font-size: 0.875rem !important;
  margin-bottom: var(--space-xs);
  letter-spacing: 0.01em;
}

/* -------------------- Tabs -------------------- */
div[data-baseweb="tab-list"] {
  gap: var(--space-xs) !important;
  background: var(--surface-elevated) !important;
  border: 1px solid var(--border-light) !important;
  border-radius: var(--radius-full) !important;
  padding: 8px !important;
  box-shadow: var(--shadow-sm);
  margin-bottom: var(--space-xl);
}

button[data-baseweb="tab"] {
  border-radius: var(--radius-full) !important;
  font-weight: 700 !important;
  font-size: 0.875rem !important;
  color: var(--text-secondary) !important;
  padding: 10px 20px !important;
  transition: all var(--transition-base);
  border: 1px solid transparent !important;
}

button[data-baseweb="tab"]:hover {
  background: var(--surface-hover) !important;
  color: var(--text-body) !important;
}

button[data-baseweb="tab"][aria-selected="true"] {
  background: linear-gradient(135deg, var(--brand-primary), var(--brand-light)) !important;
  color: #000000 !important;
  box-shadow: var(--shadow-sm);
  font-weight: 900 !important;
}

/* -------------------- Tables -------------------- */
[data-testid="stDataFrame"] {
  border: 1px solid var(--border-light) !important;
  border-radius: var(--radius-lg) !important;
  overflow: hidden;
  box-shadow: var(--shadow-sm) !important;
  background: var(--surface-base) !important;
}

[data-testid="stDataFrame"] table {
  width: 100% !important;
  border-collapse: separate !important;
  border-spacing: 0 !important;
  font-size: 0.875rem;
}

[data-testid="stDataFrame"] thead th {
  background: var(--surface-elevated) !important;
  color: var(--text-heading) !important;
  font-weight: 800 !important;
  padding: 14px 16px !important;
  text-align: left !important;
  border-bottom: 2px solid var(--border-medium) !important;
  position: sticky;
  top: 0;
  z-index: 10;
  font-size: 0.8125rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

[data-testid="stDataFrame"] tbody td {
  padding: 12px 16px !important;
  border-bottom: 1px solid var(--border-light) !important;
  vertical-align: middle !important;
  transition: background var(--transition-fast);
  color: var(--text-body) !important;
}

[data-testid="stDataFrame"] tbody tr:hover td {
  background: var(--surface-hover) !important;
}

[data-testid="stDataFrame"] tbody tr:last-child td {
  border-bottom: none !important;
}

/* Custom Scrollbar */
[data-testid="stDataFrame"] ::-webkit-scrollbar {
  height: 12px;
  width: 12px;
}

[data-testid="stDataFrame"] ::-webkit-scrollbar-track {
  background: var(--surface-base);
  border-radius: var(--radius-sm);
}

[data-testid="stDataFrame"] ::-webkit-scrollbar-thumb {
  background: var(--border-strong);
  border-radius: var(--radius-sm);
  border: 3px solid var(--surface-base);
}

[data-testid="stDataFrame"] ::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
}

/* -------------------- Chat Interface -------------------- */
[data-testid="stChatMessage"] {
  background: var(--surface-elevated) !important;
  border: 1px solid var(--border-light) !important;
  border-radius: var(--radius-lg) !important;
  padding: var(--space-md) !important;
  margin-bottom: var(--space-md) !important;
  box-shadow: var(--shadow-xs);
  transition: all var(--transition-fast);
}

[data-testid="stChatMessage"]:hover {
  box-shadow: var(--shadow-sm);
}

/* -------------------- Code Blocks -------------------- */
.stCodeBlock, pre, code {
  background: var(--surface-active) !important;
  border: 1px solid var(--border-light) !important;
  border-radius: var(--radius-md) !important;
  padding: var(--space-md) !important;
  font-family: var(--font-mono) !important;
  font-size: 0.8125rem !important;
  line-height: 1.5;
  overflow-x: auto;
  box-shadow: var(--shadow-xs);
}

/* -------------------- Status Badges -------------------- */
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 14px;
  border-radius: var(--radius-full);
  font-size: 0.8125rem;
  font-weight: 700;
  border: 1px solid;
  letter-spacing: 0.02em;
}

.badge-success {
  background: var(--success-bg);
  border-color: var(--success-border);
  color: var(--success);
}

.badge-warning {
  background: var(--warning-bg);
  border-color: var(--warning-border);
  color: var(--warning);
}

.badge-error {
  background: var(--error-bg);
  border-color: var(--error-border);
  color: var(--error);
}

.badge-info {
  background: var(--info-bg);
  border-color: var(--info-border);
  color: var(--info);
}

/* -------------------- Alerts -------------------- */
.stAlert {
  border-radius: var(--radius-md) !important;
  border-width: 1px !important;
  border-style: solid !important;
  padding: var(--space-md) !important;
  box-shadow: var(--shadow-xs);
}

/* -------------------- Forms -------------------- */
.stForm {
  background: var(--surface-elevated);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: var(--space-xl);
  box-shadow: var(--shadow-sm);
  margin-bottom: var(--space-lg);
}

/* -------------------- Dividers -------------------- */
.stDivider, hr {
  border: none !important;
  height: 1px !important;
  background: linear-gradient(90deg, transparent, var(--border-medium) 50%, transparent) !important;
  margin: var(--space-xl) 0 !important;
}

/* -------------------- Metrics -------------------- */
.metric-container {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}

.metric-card {
  background: var(--surface-elevated);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: var(--space-lg);
  text-align: center;
  box-shadow: var(--shadow-xs);
  transition: all var(--transition-base);
}

.metric-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.metric-value {
  font-size: 2.5rem;
  font-weight: 900;
  color: var(--brand-primary);
  margin: 0;
  line-height: 1;
}

.metric-label {
  font-size: 0.875rem;
  color: var(--text-secondary);
  font-weight: 700;
  margin-top: var(--space-sm);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* -------------------- Info Cards -------------------- */
.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}

.info-item {
  background: var(--surface-elevated);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.info-label {
  font-size: 0.8125rem;
  color: var(--text-tertiary);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.info-value {
  font-size: 1.125rem;
  color: var(--text-heading);
  font-weight: 700;
}

/* -------------------- Footer -------------------- */
.admin-footer {
  text-align: center;
  padding: var(--space-2xl) 0;
  margin-top: var(--space-3xl);
  color: var(--text-tertiary);
  font-size: 0.875rem;
  border-top: 1px solid var(--border-light);
}

/* -------------------- Loading States -------------------- */
.stSpinner > div {
  border-color: var(--brand-primary) transparent transparent transparent !important;
}

/* -------------------- Accessibility -------------------- */
*:focus-visible {
  outline: 2px solid var(--brand-primary) !important;
  outline-offset: 2px !important;
  border-radius: var(--radius-sm);
}

/* -------------------- Animations -------------------- */
@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.animate-in {
  animation: slideIn 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

/* -------------------- Responsive -------------------- */
@media (max-width: 768px) {
  .header-grid {
    grid-template-columns: 1fr;
  }
  
  .metric-container,
  .info-grid {
    grid-template-columns: 1fr;
  }
}

/* -------------------- Print Styles -------------------- */
@media print {
  .admin-header,
  .admin-footer,
  button,
  [data-testid="stButton"] {
    display: none !important;
  }
}

/* -------------------- Reduced Motion -------------------- */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
"""


def _load_css():
    """Inject professional enterprise CSS theme."""
    try:
        st.markdown(f"<style>{RET_ADMIN_PROFESSIONAL_CSS}</style>", unsafe_allow_html=True)
    except Exception:
        pass


_load_css()


# =========================================================
# Database Initialization (defensive)
# =========================================================
@st.cache_resource(show_spinner=False)
def _init_db_once() -> None:
    # AUTH.init_db may be missing or not callable in some test harnesses; guard it.
    fn = getattr(AUTH, "init_db", None)
    if callable(fn):
        try:
            fn()
        except Exception:
            # don't raise during page import; allow page to render and surface error later
            pass


_init_db_once()


# =========================================================
# Utility Functions
# =========================================================
def sha_short(s: str, n: int = 16) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


def _safe_str(val) -> str:
    if val is None:
        return ""
    try:
        if pd.isna(val):
            return ""
    except Exception:
        pass
    if isinstance(val, float) and math.isnan(val):
        return ""
    return str(val)


def _series_to_dict(obj):
    if isinstance(obj, pd.Series):
        return obj.to_dict()
    return obj


def _get_username(u) -> str:
    if isinstance(u, (list, tuple)) and len(u) >= 2:
        return str(u[1])
    if isinstance(u, dict):
        return str(u.get("username") or u.get("name") or "User")
    return "User"


def _get_role(u) -> str:
    if isinstance(u, (list, tuple)) and len(u) >= 3:
        return str(u[2]).lower()
    if isinstance(u, dict):
        return str(u.get("role", "user")).lower()
    return "user"


def _fmt_ts(ts: Optional[int]) -> str:
    if not ts:
        return "—"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(ts)))
    except Exception:
        return "—"


def _format_epoch_columns(df: pd.DataFrame, cols, fmt: str = "%Y-%m-%d %H:%M:%S") -> pd.DataFrame:
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            dt = pd.to_datetime(df[col], unit="s", errors="coerce")
            df[col] = dt.dt.strftime(fmt).fillna("")
    return df


def _safe_filename(name: str) -> str:
    leaf = Path(name).name
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".", " ") else "_" for ch in leaf).strip() or "log.txt"


# =========================================================
# Cookie Management (thread-safe)
# =========================================================
def get_cookie_controller() -> CookieController:
    """Get or create cached cookie controller instance (thread-safe)."""
    if "_cookie_controller" not in st.session_state:
        try:
            st.session_state["_cookie_controller"] = CookieController()
        except Exception:
            st.session_state["_cookie_controller"] = None
    return st.session_state.get("_cookie_controller") or CookieController()


def do_logout_and_redirect(reason: str = "LOGOUT") -> None:
    """Handle logout with proper cleanup and redirection (defensive)."""
    controller = get_cookie_controller()

    tok = None
    sid = None
    try:
        tok = controller.get(COOKIE_SESSION_KEY)
    except Exception:
        tok = None
    try:
        sid = controller.get(COOKIE_SID_KEY)
    except Exception:
        sid = None

    current_user = None
    if "auth_user" in st.session_state and st.session_state.auth_user is not None:
        current_user = _get_username(st.session_state.auth_user)

    try:
        # Guard against AUTH.logout_cleanup missing or not callable
        fn = getattr(AUTH, "logout_cleanup", None)
        if callable(fn):
            fn(
                cookie_token=tok,
                session_id=sid,
                username=current_user,
                temp_dir=st.session_state.get("temp_dir") or None,
                reason=reason,
                chroma_collection_name=None,
                chroma_parent_dir=None,
            )
    except Exception:
        pass

    for key in (COOKIE_SESSION_KEY, COOKIE_SID_KEY):
        try:
            controller.set(key, "", max_age=0)
        except Exception:
            pass

    try:
        st.session_state.clear()
    except Exception:
        for k in list(st.session_state.keys()):
            try:
                del st.session_state[k]
            except Exception:
                pass

    # Try multiple possible main page paths for different app arrangements
    for t in ("login.py", "Home.py", "pages/login.py", "pages/Home.py", "main.py", "pages/main.py"):
        try:
            st.switch_page(t)
            break
        except Exception:
            continue

    # In case switch_page didn't raise but we want to ensure UI updates
    try:
        st.rerun()
    except Exception:
        pass


if DEBUG:
    st.caption(f"🔍 Debug: auth.py loaded from: {getattr(AUTH, '__file__', 'unknown')}")


# =========================================================
# Authentication Gate
# =========================================================
if "auth_user" not in st.session_state or st.session_state.auth_user is None:
    do_logout_and_redirect(reason="NO_AUTH")
    st.stop()

current_username = _get_username(st.session_state.auth_user)
current_role = _get_role(st.session_state.auth_user).lower()

if current_role != "admin":
    st.error("⛔ Access Denied: Administrator privileges required.")
    do_logout_and_redirect(reason="FORBIDDEN")
    st.stop()


# =========================================================
# Auto-refresh (1 minute) — defensive calling
# =========================================================
# st_autorefresh might be a no-op fallback; calling it is safe.
st_autorefresh(interval=60 * 1000, key="admin_refresh")


# =========================================================
# Token Pruning (defensive)
# =========================================================
try:
    fn = getattr(AUTH, "prune_expired_tokens", None)
    if callable(fn):
        try:
            fn()
        except Exception:
            pass
except Exception:
    pass


# =========================================================
# Cached Data Functions (with explicit List return types)
# =========================================================
@st.cache_data(ttl=60, show_spinner=False)
def cached_users(_admin_user: str) -> List[Dict[str, Any]]:
    """Get cached user list."""
    raw = AUTH.list_users() if hasattr(AUTH, "list_users") else []
    # Ensure list return type for type-checkers
    return list(raw)


@st.cache_data(ttl=30, show_spinner=False)
def cached_ops_logs(_admin_user: str, area: Optional[str], limit: int) -> List[Dict[str, Any]]:
    """Get cached operational logs."""
    logs = AUTH.list_ops_logs(limit=int(limit), area=area)
    return list(logs[: int(limit)])


@st.cache_data(ttl=60, show_spinner=False)
def cached_audit_logs(_admin_user: str, limit: int = 500) -> List[Dict[str, Any]]:
    """Get cached audit logs."""
    raw = AUTH.list_audit_logs(limit=int(limit)) if hasattr(AUTH, "list_audit_logs") else []
    return list(raw)


@st.cache_data(ttl=30, show_spinner=False)
def cached_reset_requests(_admin_user: str, status: str = "pending") -> List[Dict[str, Any]]:
    """Get cached password reset requests."""
    raw = AUTH.list_reset_requests(status=status) if hasattr(AUTH, "list_reset_requests") else []
    return list(raw)


@st.cache_data(ttl=30, show_spinner=False)
def cached_sessions_eligible(_admin_user: str, cutoff: int) -> List[AppSession]:
    """Return an explicit List[AppSession] (avoid Sequence to satisfy type checkers)."""
    with get_session() as db:
        rows = (
            db.execute(
                select(AppSession)
                .where(AppSession.status == "ACTIVE")
                .where(AppSession.last_seen < cutoff)
                .order_by(AppSession.last_seen.asc())
            )
            .scalars()
            .all()
        )
    return list(rows)


@st.cache_data(ttl=30, show_spinner=False)
def cached_sessions_recent(_admin_user: str, limit: int = 500) -> List[AppSession]:
    """Return an explicit List[AppSession] (avoid Sequence to satisfy type checkers)."""
    with get_session() as db:
        recent = (
            db.execute(
                select(AppSession)
                .order_by(AppSession.last_seen.desc())
                .limit(int(limit))
            )
            .scalars()
            .all()
        )
    return list(recent)


# Load user data
try:
    users = cached_users(current_username)
except Exception as e:
    st.error(f"⚠️ Failed to load users: {e}")
    users = []

usernames = [u["username"] for u in users] if users else []
admin_count = sum(1 for u in users if str(u.get("role", "")).lower() == "admin")


# =========================================================
# Operations Logging
# =========================================================
def _agent_log(level: str, action: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
    """Log admin agent actions to operational logs with correlation ID."""
    try:
        write_ops_log(
            level=level,
            area="ADMIN_AGENT",
            action=action,
            username=current_username,
            session_id=None,
            corr_id=new_action_cid(action),
            message=(message or "")[:1000],
            details=details or {},
        )
    except Exception:
        pass


# =========================================================
# Session Cleanup Functions (thread-safe)
# =========================================================
def cleanup_idle_sessions_postgres(idle_seconds: int, force: bool = False) -> Dict[str, Any]:
    """Cleanup idle sessions with disk cleanup (thread-safe)."""
    with _SESSION_CLEANUP_LOCK:
        summary: Dict[str, Any] = {"eligible": 0, "deleted": 0, "failed": 0, "sessions": []}
        cutoff = int(time.time() - idle_seconds)

        with get_session() as db:
            rows = (
                db.execute(
                    select(AppSession)
                    .where(AppSession.status == "ACTIVE")
                    .where(AppSession.last_seen < cutoff)
                    .order_by(AppSession.last_seen.asc())
                )
                .scalars()
                .all()
            )

            summary["eligible"] = len(rows)

            for s in rows:
                temp_dir = str(s.temp_dir or "")
                ok = True
                if temp_dir:
                    ok = _safe_delete_dir_allowlisted(temp_dir)

                if ok:
                    setattr(s, "status", "FORCE_CLEANED_IDLE" if force else "CLEANED_IDLE")
                    setattr(s, "last_seen", int(time.time()))
                    summary["deleted"] += 1
                    summary["sessions"].append((s.session_id, s.username, getattr(s, "status", "")))
                else:
                    setattr(s, "status", "FAILED_DELETE")
                    setattr(s, "last_seen", int(time.time()))
                    summary["failed"] += 1
                    summary["sessions"].append((s.session_id, s.username, "FAILED_DELETE"))

                db.add(s)

            db.commit()

        return summary


# =========================================================
# Azure OpenAI Configuration (with improved error handling)
# =========================================================
def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Get environment variable safely."""
    v = os.environ.get(name)
    if v is None or str(v).strip() == "":
        return default
    return v


def get_aoai_config() -> Dict[str, Optional[str]]:
    """Get Azure OpenAI configuration from environment."""
    return {
        "endpoint": _env("AZURE_OPENAI_ENDPOINT", ""),
        "api_key": _env("AZURE_OPENAI_API_KEY", ""),
        "api_version": _env("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        "agent_deployment": _env("ADMIN_AGENT_CHAT_DEPLOYMENT", _env("AZURE_OPENAI_CHAT_DEPLOYMENT", "")),
    }


@st.cache_resource(show_spinner=False)
def get_aoai_client_cached(endpoint: Optional[str], api_key: Optional[str], api_version: Optional[str]):
    """Get cached Azure OpenAI client with defensive checks."""
    # Be explicit for static analyzers: AzureOpenAI may be None at import time.
    if not _AOAI_AVAILABLE or AzureOpenAI is None:
        raise RuntimeError("Azure OpenAI SDK not installed. Install: pip install openai")
    if not endpoint or not api_key:
        raise RuntimeError("Azure OpenAI endpoint/api_key not configured.")
    # At this point, AzureOpenAI is guaranteed non-None. Use an assert so type checkers know.
    assert AzureOpenAI is not None
    return AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)


def _with_retry(fn, retries: int = 4, base_delay: float = 0.6, max_delay: float = 6.0):
    """Execute function with exponential backoff retry logic."""
    last_exc: Optional[Exception] = None
    for i in range(retries):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            delay = min(max_delay, base_delay * (2 ** i)) * (0.7 + 0.6 * random.random())
            time.sleep(delay)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Retry failed but no exception was recorded")


def _with_retry(fn, retries: int = 4, base_delay: float = 0.6, max_delay: float = 6.0):
    last_exc: Optional[Exception] = None
    for i in range(retries):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            delay = min(max_delay, base_delay * (2 ** i)) * (0.7 + 0.6 * random.random())
            time.sleep(delay)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Retry failed but no exception was recorded")


# =========================================================
# AI Agent Tools
# =========================================================
def tool_create_user(username: str, role: str = "user", ttl_hours: int = 24, note: str = "") -> Dict[str, Any]:
    uname = (username or "").strip().lower()
    role = (role or "user").strip().lower()
    ttl_hours = int(ttl_hours or 24)
    if role not in ("user", "guest", "admin"):
        role = "user"

    AUTH.create_user(uname, role, password=None, admin_username=current_username)
    tok = AUTH.admin_generate_reset_token_for_user(
        uname,
        admin_username=current_username,
        ttl_seconds=int(ttl_hours) * 3600,
        note=note or "created by AI agent",
    )
    _agent_log("INFO", "ai_create_user", f"AI created user {uname}", {"role": role, "ttl_hours": ttl_hours})
    return {"ok": True, "username": uname, "role": role, "token": tok}


def tool_delete_user(username: str) -> Dict[str, Any]:
    uname = (username or "").strip().lower()
    ok = AUTH.delete_user(uname, admin_username=current_username)
    _agent_log("INFO", "ai_delete_user", f"AI deleted user {uname}", {"ok": ok})
    return {"ok": bool(ok), "username": uname}


def tool_set_role(username: str, role: str) -> Dict[str, Any]:
    uname = (username or "").strip().lower()
    role = (role or "").strip().lower()
    ok = AUTH.update_user_role(uname, role, admin_username=current_username)
    _agent_log("INFO", "ai_set_role", f"AI updated role for {uname}", {"role": role, "ok": ok})
    return {"ok": bool(ok), "username": uname, "role": role}


def tool_unlock_user(username: str) -> Dict[str, Any]:
    uname = (username or "").strip().lower()
    ok = AUTH.unlock_user(uname, admin_username=current_username)
    _agent_log("INFO", "ai_unlock_user", f"AI unlocked {uname}", {"ok": ok})
    return {"ok": bool(ok), "username": uname}


def tool_generate_reset_token(username: str, ttl_hours: int = 24, note: str = "") -> Dict[str, Any]:
    uname = (username or "").strip().lower()
    ttl_hours = int(ttl_hours or 24)
    tok = AUTH.admin_generate_reset_token_for_user(
        uname,
        admin_username=current_username,
        ttl_seconds=int(ttl_hours) * 3600,
        note=note or "generated by AI agent",
    )
    _agent_log("INFO", "ai_reset_token", f"AI generated token for {uname}", {"ttl_hours": ttl_hours})
    return {"ok": bool(tok), "username": uname, "token": tok}


def tool_cleanup_idle_sessions(idle_minutes: int = 60, force: bool = False) -> Dict[str, Any]:
    idle_minutes = int(idle_minutes or 60)
    summary = cleanup_idle_sessions_postgres(idle_seconds=idle_minutes * 60, force=bool(force))
    _agent_log("INFO", "ai_cleanup_sessions", "AI executed idle cleanup", summary)
    return summary


def tool_fetch_ops_logs(area: str = "(all)", limit: int = 300) -> Dict[str, Any]:
    area_val = None if (area or "(all)") == "(all)" else area
    logs = AUTH.list_ops_logs(limit=int(limit), area=area_val)
    logs = logs[: int(limit)]
    return {"ok": True, "area": area_val or "(all)", "count": len(logs), "logs": logs}


def tool_summarize_ops_logs(area: str = "(all)", limit: int = 200) -> Dict[str, Any]:
    return tool_fetch_ops_logs(area=area, limit=limit)


AI_TOOL_REGISTRY = {
    "create_user": tool_create_user,
    "delete_user": tool_delete_user,
    "set_role": tool_set_role,
    "unlock_user": tool_unlock_user,
    "generate_reset_token": tool_generate_reset_token,
    "cleanup_idle_sessions": tool_cleanup_idle_sessions,
    "fetch_ops_logs": tool_fetch_ops_logs,
    "summarize_ops_logs": tool_summarize_ops_logs,
}

DESTRUCTIVE_TOOLS = {"delete_user", "cleanup_idle_sessions", "set_role"}


def _aoai_tools_schema() -> List[Dict[str, Any]]:
    return [
        {"type": "function", "function": {
            "name": "create_user",
            "description": "Create a user (no password) and generate a one-time reset token.",
            "parameters": {"type": "object", "properties": {
                "username": {"type": "string"},
                "role": {"type": "string", "enum": ["user", "guest", "admin"]},
                "ttl_hours": {"type": "integer", "minimum": 1, "maximum": 168},
                "note": {"type": "string"},
            }, "required": ["username"]} 
        }},
        {"type": "function", "function": {
            "name": "delete_user",
            "description": "Delete a user account.",
            "parameters": {"type": "object", "properties": {
                "username": {"type": "string"},
            }, "required": ["username"]}
        }},
        {"type": "function", "function": {
            "name": "set_role",
            "description": "Set a user's role (admin/user/guest).",
            "parameters": {"type": "object", "properties": {
                "username": {"type": "string"},
                "role": {"type": "string", "enum": ["user", "guest", "admin"]},
            }, "required": ["username", "role"]}
        }},
        {"type": "function", "function": {
            "name": "unlock_user",
            "description": "Unlock a user account (clear lockout).",
            "parameters": {"type": "object", "properties": {
                "username": {"type": "string"},
            }, "required": ["username"]}
        }},
        {"type": "function", "function": {
            "name": "generate_reset_token",
            "description": "Generate a one-time reset token for a user.",
            "parameters": {"type": "object", "properties": {
                "username": {"type": "string"},
                "ttl_hours": {"type": "integer", "minimum": 1, "maximum": 168},
                "note": {"type": "string"},
            }, "required": ["username"]}
        }},
        {"type": "function", "function": {
            "name": "cleanup_idle_sessions",
            "description": "Cleanup idle ACTIVE sessions and delete temp dirs (allowlisted).",
            "parameters": {"type": "object", "properties": {
                "idle_minutes": {"type": "integer", "minimum": 5, "maximum": 1440},
                "force": {"type": "boolean"},
            }, "required": ["idle_minutes"]}
        }},
        {"type": "function", "function": {
            "name": "fetch_ops_logs",
            "description": "Fetch operational logs from Postgres.",
            "parameters": {"type": "object", "properties": {
                "area": {"type": "string"},
                "limit": {"type": "integer", "minimum": 50, "maximum": 2000},
            }}
        }},
        {"type": "function", "function": {
            "name": "summarize_ops_logs",
            "description": "Fetch ops logs intended to be summarized by the model.",
            "parameters": {"type": "object", "properties": {
                "area": {"type": "string"},
                "limit": {"type": "integer", "minimum": 50, "maximum": 2000},
            }}
        }},
    ]


def aoai_agent_chat(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Execute Azure OpenAI chat with tool calling (with retry logic)."""
    cfg = get_aoai_config()
    endpoint = cfg.get("endpoint") or ""
    api_key = cfg.get("api_key") or ""
    api_version = cfg.get("api_version") or ""
    client = get_aoai_client_cached(endpoint, api_key, api_version)
    model = cfg.get("agent_deployment") or ""
    if not model:
        raise RuntimeError("Admin Agent deployment not configured.")

    def call():
        return client.chat.completions.create(
            model=model,
            messages=cast(Any, messages),
            tools=cast(Any, _aoai_tools_schema()),
            tool_choice="auto",
            temperature=0.2,
            timeout=60,
        )

    resp = _with_retry(call, retries=4)
    try:
        return resp.model_dump()
    except Exception:
        return json.loads(json.dumps(resp, default=str))


def _extract_tool_call(resp_obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        choices = resp_obj.get("choices") or []
        if not choices:
            return None
        msg = (choices[0] or {}).get("message") or {}
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return None
        tc = tool_calls[0]
        fn = (tc.get("function") or {})
        name = fn.get("name")
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {"raw": args}
        return {"name": name, "arguments": args or {}}
    except Exception:
        return None


def _extract_text(resp_obj: Dict[str, Any]) -> str:
    try:
        choices = resp_obj.get("choices") or []
        msg = (choices[0] or {}).get("message") or {}
        return (msg.get("content") or "").strip()
    except Exception:
        return ""


# =========================================================
# Log Redaction for AI Safety
# =========================================================
SENSITIVE_KEYS = {
    "session_id", "temp_dir", "log_path", "corr_id",
    "details_json", "message", "token", "authorization", "api_key", "password"
}


def redact_logs_for_ai(logs: list[dict], max_rows: int = 200) -> str:
    """Remove sensitive fields before sending to AI model."""
    out = []
    for row in logs[:max_rows]:
        clean = {}
        for k, v in (row or {}).items():
            if k in SENSITIVE_KEYS:
                clean[k] = "[REDACTED]"
            else:
                s = str(v).replace("\r", "\\r").replace("\n", "\\n")
                clean[k] = s[:500]
        out.append(clean)
    return json.dumps(out, ensure_ascii=False)[:12000]


# =========================================================
# ENTERPRISE UI HEADER
# =========================================================
st.markdown(f"""
<div class="admin-header animate-in">
    <div class="header-grid">
        <div class="brand-section">
            <h1 class="brand-title">
                RET<span class="brand-accent">v4</span> Admin Console
            </h1>
            <p class="brand-subtitle">Enterprise Administration Dashboard</p>
        </div>
        <div class="user-info">
            <div class="user-avatar">{current_username[0].upper()}</div>
            <span>{current_username}</span>
        </div>
        <div style="display: flex; gap: 12px;">
""", unsafe_allow_html=True)

col_back, col_logout = st.columns(2)
with col_back:
    if st.button("⬅️ Back to App", use_container_width=True, key="admin_back_to_app"):
        try:
            st.switch_page("pages/main.py")
        except Exception:
            try:
                st.switch_page("main.py")
            except Exception:
                pass
        st.stop()

with col_logout:
    if st.button("🚪 Logout", use_container_width=True, key="admin_logout", type="secondary"):
        do_logout_and_redirect(reason="LOGOUT")
        st.stop()

st.markdown("</div></div></div>", unsafe_allow_html=True)


# =========================================================
# Quick Stats Dashboard
# =========================================================
st.markdown(f"""
<div class="metric-container animate-in">
    <div class="metric-card">
        <div class="metric-value">{len(users)}</div>
        <div class="metric-label">Total Users</div>
    </div>
    <div class="metric-card">
        <div class="metric-value">{admin_count}</div>
        <div class="metric-label">Administrators</div>
    </div>
    <div class="metric-card">
        <div class="metric-value">{len(users) - admin_count}</div>
        <div class="metric-label">Regular Users</div>
    </div>
</div>
""", unsafe_allow_html=True)


# =========================================================
# Enhanced Tab Navigation
# =========================================================
tabs = st.tabs([
    "🤖 AI Agent",
    "➕ Add User",
    "🛠️ Manage User",
    "👥 All Users",
    "🔑 Reset Requests",
    "📝 Audit Logs",
    "🧾 Ops Logs",
    "📁 Sessions",
])


# =========================================================
# TAB 0: Admin AI Agent
# =========================================================
with tabs[0]:
    st.markdown("""
    <div class="enterprise-card animate-in">
        <div class="card-header">
            <div class="card-title-group">
                <h2 class="card-title">🤖 AI-Powered Admin Agent</h2>
                <p class="card-description">Natural language interface for administrative tasks with built-in safety controls</p>
            </div>
        </div>
    """, unsafe_allow_html=True)

    cfg = get_aoai_config()
    if not (cfg.get("endpoint") and cfg.get("api_key") and cfg.get("agent_deployment")):
        st.warning("⚠️ Azure OpenAI not configured. Set environment variables for AI Agent functionality.")

    if "admin_ai_chat" not in st.session_state:
        st.session_state.admin_ai_chat = []
    if "admin_ai_pending_tool" not in st.session_state:
        st.session_state.admin_ai_pending_tool = None

    # Chat History
    st.markdown("### 💬 Conversation")
    for m in st.session_state.admin_ai_chat[-30:]:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    # Pending Tool Execution
    pending = st.session_state.admin_ai_pending_tool
    if pending:
        name = pending.get("name")
        args = pending.get("arguments", {})
        
        st.markdown("""
        <div class="enterprise-card" style="border-left: 4px solid var(--warning); background: var(--warning-bg);">
            <h4 style="margin: 0 0 12px 0; color: var(--warning);">⚡ Action Requires Confirmation</h4>
        """, unsafe_allow_html=True)
        
        st.code(json.dumps({"tool": name, "arguments": args}, indent=2), language="json")

        col1, col2, col3 = st.columns([1, 1, 4])
        with col1:
            if st.button("✅ Execute", type="primary", key=f"ai_exec_{sha_short(name + json.dumps(args), 10)}"):
                try:
                    if name not in AI_TOOL_REGISTRY:
                        raise ValueError(f"Tool not allowed: {name}")
                    fn = AI_TOOL_REGISTRY[name]
                    result = fn(**args)
                    st.session_state.admin_ai_chat.append(
                        {"role": "assistant", "content": f"✅ **Action Completed:** `{name}`\n\n```json\n{json.dumps(result, indent=2)}\n```"}
                    )
                    st.session_state.admin_ai_pending_tool = None
                    st.rerun()
                except Exception as e:
                    st.session_state.admin_ai_chat.append({"role": "assistant", "content": f"❌ **Execution Failed:** `{str(e)}`"})
                    st.session_state.admin_ai_pending_tool = None
                    st.rerun()

        with col2:
            if st.button("🛑 Cancel", key=f"ai_cancel_{sha_short(name, 10)}", type="secondary"):
                st.session_state.admin_ai_chat.append({"role": "assistant", "content": "🛑 Action cancelled by administrator."})
                st.session_state.admin_ai_pending_tool = None
                st.rerun()
        
        st.markdown("</div>", unsafe_allow_html=True)

    # Chat Input
    prompt = st.chat_input("💬 Ask the AI agent... e.g., 'Create user alex as admin with 48 hour token'")
    if prompt:
        st.session_state.admin_ai_chat.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        system = {
            "role": "system",
            "content": (
                "You are an enterprise admin AI agent for RETv4.\n"
                "You help administrators manage users, tokens, sessions, and logs.\n"
                "For any action request, propose a tool call.\n"
                "Be concise and professional.\n"
            ),
        }

        messages = [system] + [{"role": m["role"], "content": m["content"]} for m in st.session_state.admin_ai_chat[-12:]]
        try:
            resp = aoai_agent_chat(messages)
            tool_call = _extract_tool_call(resp)
            text = _extract_text(resp)

            if tool_call and tool_call.get("name") in AI_TOOL_REGISTRY:
                tname = tool_call["name"]
                targs = tool_call.get("arguments", {}) or {}
                st.session_state.admin_ai_pending_tool = {"name": tname, "arguments": targs}

                expl = text or f"I recommend executing `{tname}` with the parameters shown above."
                st.session_state.admin_ai_chat.append(
                    {"role": "assistant", "content": f"**Proposed Action:** `{tname}`\n\n{expl}\n\n*(Confirm or cancel above)*"}
                )
                st.rerun()
            else:
                if text:
                    st.session_state.admin_ai_chat.append({"role": "assistant", "content": text})
                    st.rerun()
        except Exception as e:
            st.error(f"🚨 AI Agent Error: {str(e)[:300]}")
            write_ops_log(
                level="ERROR",
                area="ADMIN_AI",
                action="ai_chat_error",
                username=current_username,
                message=str(e)[:500],
            )

    st.markdown("</div>", unsafe_allow_html=True)

    # Command Runner
    st.markdown("""
    <div class="enterprise-card animate-in" style="margin-top: 24px;">
        <div class="card-header">
            <div class="card-title-group">
                <h3 class="card-title">⚙️ Direct Command Runner</h3>
                <p class="card-description">Execute precise admin commands with deterministic behavior</p>
            </div>
        </div>
    """, unsafe_allow_html=True)

    cmd = st.text_area(
        "Command",
        height=100,
        placeholder="e.g., create user alex role admin ttl 48 note onboarding",
        key="admin_cmd_text",
        help="Supported commands: create user, set role, unlock, delete, reset token, approve/reject reset request, cleanup idle sessions"
    )
    confirm_destructive = st.checkbox("⚠️ I confirm this action (required for destructive operations)", value=False, key="confirm_destructive_cmd")

    def _agent_execute(command: str) -> Tuple[bool, str]:
        cmd_in = (command or "").strip()
        if not cmd_in:
            return False, "❌ Command cannot be empty."

        # [Command parsing logic remains the same as original]
        # create user
        m = re.match(
            r"^create\s+user\s+([a-z0-9._-]{3,64})(?:\s+role\s+(admin|user|guest))?(?:\s+ttl\s+(\d+))?(?:\s+note\s+(.+))?$",
            cmd_in,
            flags=re.IGNORECASE
        )
        if m:
            uname = m.group(1).lower()
            role = (m.group(2) or "user").lower()
            ttl_h = int(m.group(3) or 24)
            note = (m.group(4) or "").strip()
            try:
                AUTH.create_user(uname, role, password=None, admin_username=current_username)
                tok = AUTH.admin_generate_reset_token_for_user(
                    uname,
                    admin_username=current_username,
                    ttl_seconds=int(ttl_h) * 3600,
                    note=note or "command runner onboarding",
                )
                _agent_log("INFO", "create_user", f"User {uname} created via command", {"role": role, "ttl_hours": ttl_h})
                return True, f"✅ **Success:** User `{uname}` created (role={role})\n\n**Token:**\n```\n{tok}\n```"
            except Exception as e:
                _agent_log("ERROR", "create_user_failed", str(e), {"username": uname})
                return False, f"❌ **Failed:** {e}"

        # set role
        m = re.match(r"^set\s+role\s+([a-z0-9._-]{3,64})\s+(admin|user|guest)$", cmd_in, flags=re.IGNORECASE)
        if m:
            uname, role = m.group(1).lower(), m.group(2).lower()
            if "set_role" in DESTRUCTIVE_TOOLS and not confirm_destructive:
                return False, "⚠️ Destructive action requires confirmation checkbox."
            try:
                ok = AUTH.update_user_role(uname, role, admin_username=current_username)
                _agent_log("INFO", "set_role", f"Role updated for {uname}", {"new_role": role, "ok": ok})
                return True, f"✅ **Success:** Role updated for `{uname}` → `{role}`"
            except Exception as e:
                _agent_log("ERROR", "set_role_failed", str(e), {"username": uname})
                return False, f"❌ **Failed:** {e}"

        # unlock
        m = re.match(r"^unlock\s+([a-z0-9._-]{3,64})$", cmd_in, flags=re.IGNORECASE)
        if m:
            uname = m.group(1).lower()
            try:
                ok = AUTH.unlock_user(uname, admin_username=current_username)
                _agent_log("INFO", "unlock_user", f"Unlocked {uname}", {"ok": ok})
                return True, f"✅ **Success:** User `{uname}` unlocked" if ok else f"⚠️ User `{uname}` not found"
            except Exception as e:
                _agent_log("ERROR", "unlock_failed", str(e), {"username": uname})
                return False, f"❌ **Failed:** {e}"

        # delete user
        m = re.match(r"^delete\s+([a-z0-9._-]{3,64})$", cmd_in, flags=re.IGNORECASE)
        if m:
            uname = m.group(1).lower()
            if "delete_user" in DESTRUCTIVE_TOOLS and not confirm_destructive:
                return False, "⚠️ Destructive action requires confirmation checkbox."
            try:
                ok = AUTH.delete_user(uname, admin_username=current_username)
                _agent_log("INFO", "delete_user", f"Deleted {uname}", {"ok": ok})
                return True, f"✅ **Success:** User `{uname}` deleted" if ok else f"⚠️ User `{uname}` not found"
            except Exception as e:
                _agent_log("ERROR", "delete_failed", str(e), {"username": uname})
                return False, f"❌ **Failed:** {e}"

        # reset token
        m = re.match(
            r"^reset\s+token\s+([a-z0-9._-]{3,64})(?:\s+ttl\s+(\d+))?(?:\s+note\s+(.+))?$",
            cmd_in,
            flags=re.IGNORECASE
        )
        if m:
            uname = m.group(1).lower()
            ttl_h = int(m.group(2) or 24)
            note = (m.group(3) or "").strip()
            try:
                tok = AUTH.admin_generate_reset_token_for_user(
                    uname,
                    admin_username=current_username,
                    ttl_seconds=int(ttl_h) * 3600,
                    note=note or "command runner reset token",
                )
                if not tok:
                    return False, f"❌ User `{uname}` not found"
                _agent_log("INFO", "reset_token", f"Token generated for {uname}", {"ttl_hours": ttl_h})
                return True, f"✅ **Success:** Token generated for `{uname}`\n\n```\n{tok}\n```"
            except Exception as e:
                _agent_log("ERROR", "reset_token_failed", str(e), {"username": uname})
                return False, f"❌ **Failed:** {e}"

        # approve reset request
        m = re.match(r"^approve\s+reset\s+request\s+(\d+)(?:\s+ttl\s+(\d+))?$", cmd_in, flags=re.IGNORECASE)
        if m:
            req_id = int(m.group(1))
            ttl_h = int(m.group(2) or 24)
            try:
                tok = AUTH.admin_generate_token_for_request(req_id, current_username, ttl=int(ttl_h) * 3600)
                if not tok:
                    return False, f"❌ Request #{req_id} not pending or not found"
                AUTH.set_reset_request_status(req["id"], "approved", current_username, note="approved via command")
                _agent_log("INFO", "approve_reset_request", f"Approved request {req_id}", {"ttl_hours": ttl_h})
                return True, f"✅ **Success:** Request #{req_id} approved\n\n**Token:**\n```\n{tok}\n```"
            except Exception as e:
                _agent_log("ERROR", "approve_reset_request_failed", str(e), {"request_id": req_id})
                return False, f"❌ **Failed:** {e}"

        # reject reset request
        m = re.match(r"^reject\s+reset\s+request\s+(\d+)(?:\s+note\s+(.+))?$", cmd_in, flags=re.IGNORECASE)
        if m:
            req_id = int(m.group(1))
            note = (m.group(2) or "rejected via command").strip()
            try:
                ok = AUTH.set_reset_request_status(req_id, "rejected", current_username, note=note)
                _agent_log("INFO", "reject_reset_request", f"Rejected request {req_id}", {"note": note, "ok": ok})
                return True, f"✅ **Success:** Request #{req_id} rejected" if ok else f"⚠️ Request #{req_id} not found"
            except Exception as e:
                _agent_log("ERROR", "reject_reset_request_failed", str(e), {"request_id": req_id})
                return False, f"❌ **Failed:** {e}"

        # cleanup idle sessions
        m = re.match(r"^cleanup\s+idle\s+sessions(?:\s+minutes\s+(\d+))?(?:\s+force\s+(true|false))?$", cmd_in, flags=re.IGNORECASE)
        if m:
            if "cleanup_idle_sessions" in DESTRUCTIVE_TOOLS and not confirm_destructive:
                return False, "⚠️ Destructive action requires confirmation checkbox."
            minutes = int(m.group(1) or int(IDLE_CLEANUP_SECONDS_DEFAULT // 60))
            force = (m.group(2) or "false").lower() == "true"
            seconds = minutes * 60
            summary = cleanup_idle_sessions_postgres(idle_seconds=seconds, force=force)
            _agent_log("INFO", "cleanup_idle_sessions", "Cleanup executed via command", summary)
            return True, f"✅ **Cleanup Complete**\n\nEligible: {summary['eligible']}\nDeleted: {summary['deleted']}\nFailed: {summary['failed']}"
        
        return False, (
            "❌ **Unknown Command**\n\n"
            "**Supported commands:**\n"
            "- `create user <username> role <user|admin|guest> ttl <hours> note <text>`\n"
            "- `set role <username> <admin|user|guest>`\n"
            "- `unlock <username>`\n"
            "- `delete <username>`\n"
            "- `reset token <username> ttl <hours> note <text>`\n"
            "- `approve reset request <id> ttl <hours>`\n"
            "- `reject reset request <id> note <text>`\n"
            "- `cleanup idle sessions minutes <minutes> force <true|false>`\n"
        )

    if st.button("▶️ Execute Command", type="primary", use_container_width=True, key="admin_cmd_run"):
        ok, msg = _agent_execute(cmd)
        if ok:
            st.success("✅ Command executed successfully")
            st.markdown(msg)
            st.cache_data.clear()
            time.sleep(0.5)
            st.rerun()
        else:
            st.error("❌ Command failed")
            st.markdown(msg)

    st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# TAB 1: Add New User
# =========================================================
with tabs[1]:
    st.markdown("""
    <div class="enterprise-card animate-in">
        <div class="card-header">
            <div class="card-title-group">
                <h2 class="card-title">➕ Create New User Account</h2>
                <p class="card-description">Token-first onboarding with secure password setup</p>
            </div>
        </div>
    """, unsafe_allow_html=True)

    with st.form("add_user_form", clear_on_submit=True):
        new_username_raw = st.text_input("Username", placeholder="e.g., john.smith", help="3-64 characters, lowercase, alphanumeric with dots, dashes, underscores")
        new_username = (new_username_raw or "").strip().lower()
        if new_username_raw and new_username != new_username_raw:
            st.caption(f"✨ Normalized to: `{new_username}`")

        col1, col2 = st.columns(2)
        with col1:
            new_role = st.selectbox("Role", ["user", "guest", "admin"], index=0, help="user=standard access, guest=limited, admin=full control")
        with col2:
            ttl_hours = st.number_input("Token Validity (hours)", min_value=1, max_value=168, value=24, step=1, help="1-168 hours (7 days max)")

        note = st.text_input("Administrative Note", placeholder="e.g., Ticket #12345, Onboarding batch Q1", help="Optional context for audit trail")

        submitted = st.form_submit_button("🎯 Create User + Generate Token", type="primary", use_container_width=True)
        if submitted:
            uname = (new_username or "").strip().lower()
            if not uname:
                st.error("❌ Username is required")
            elif len(uname) < 3 or len(uname) > 64:
                st.error("❌ Username must be 3-64 characters")
            else:
                try:
                    AUTH.create_user(uname, new_role, password=None, admin_username=current_username)
                    tok = AUTH.admin_generate_reset_token_for_user(
                        uname,
                        admin_username=current_username,
                        ttl_seconds=int(ttl_hours) * 3600,
                        note=note or "new user onboarding",
                    )
                    st.success(f"✅ User `{uname}` created successfully!")
                    st.markdown(f"""
                    <div class="enterprise-card" style="border-left: 4px solid var(--success); background: var(--success-bg); margin-top: 16px;">
                        <h4 style="color: var(--success); margin: 0 0 8px 0;">🎫 One-Time Setup Token</h4>
                        <p style="margin: 0 0 12px 0; color: var(--text-secondary);">Share this token securely with the user. Valid for {ttl_hours} hours.</p>
                    </div>
                    """, unsafe_allow_html=True)
                    st.code(tok, language="text")
                    st.info("ℹ️ User must use this token to set their password before accessing the system.")
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed to create user: {str(e)}")

    st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# TAB 2: Manage User
# =========================================================
with tabs[2]:
    st.markdown("""
    <div class="enterprise-card animate-in">
        <div class="card-header">
            <div class="card-title-group">
                <h2 class="card-title">🛠️ Manage User Account</h2>
                <p class="card-description">Update roles, generate tokens, unlock accounts, and more</p>
            </div>
        </div>
    """, unsafe_allow_html=True)

    if not users:
        st.info("📭 No users found in the system.")
    else:
        target_user = st.selectbox("Select User", options=usernames, key="admin_target_user", help="Choose a user to manage")
        selected = next((u for u in users if u["username"] == target_user), None)

        if selected:
            sel_username = selected["username"]
            sel_role = str(selected.get("role", "user")).lower()
            must_reset = int(selected.get("must_reset", 1))
            failed_attempts = int(selected.get("failed_attempts", 0))
            locked_until = int(selected.get("locked_until", 0))
            created_at = int(selected.get("created_at", 0))
            changed_at = selected.get("password_changed_at", None)

            # User Info Display
            st.markdown(f"""
            <div class="info-grid">
                <div class="info-item">
                    <div class="info-label">Username</div>
                    <div class="info-value">{sel_username}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Role</div>
                    <div class="info-value">{sel_role.upper()}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Must Reset Password</div>
                    <div class="info-value">{'✅ Yes' if must_reset == 1 else '❌ No'}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Failed Login Attempts</div>
                    <div class="info-value">{failed_attempts}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Account Locked Until</div>
                    <div class="info-value">{_fmt_ts(locked_until)}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Created At</div>
                    <div class="info-value">{_fmt_ts(created_at)}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Password Last Changed</div>
                    <div class="info-value">{_fmt_ts(changed_at)}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.divider()

            # Role Update
            st.markdown("### 🔄 Update Role")
            new_role_for_user = st.selectbox(
                "New Role",
                ["user", "guest", "admin"],
                index=["user", "guest", "admin"].index(sel_role) if sel_role in ["user", "guest", "admin"] else 0,
                key="admin_new_role",
                help="Admin role grants full system access"
            )

            will_demote_admin = (sel_role == "admin" and new_role_for_user != "admin")
            is_self = (sel_username == current_username)
            demotes_last_admin = (will_demote_admin and admin_count <= 1)
            can_update_role = (not is_self) and (not demotes_last_admin)

            if is_self:
                st.warning("⚠️ You cannot modify your own role.")
            elif demotes_last_admin:
                st.warning("⚠️ Cannot demote the last administrator.")

            if st.button("💾 Update Role", disabled=not can_update_role, key="btn_update_role", type="primary"):
                try:
                    ok = AUTH.update_user_role(sel_username, new_role_for_user, admin_username=current_username)
                    if ok:
                        st.success(f"✅ Role updated: `{sel_username}` → `{new_role_for_user}`")
                        st.cache_data.clear()
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("❌ Role update failed")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")

            st.divider()

            # Token Generation
            st.markdown("### 🎫 Generate Reset Token")
            col1, col2 = st.columns(2)
            with col1:
                ttl_hours2 = st.number_input("Token TTL (hours)", min_value=1, max_value=168, value=24, step=1, key="mgr_token_ttl")
            with col2:
                token_note = st.text_input("Note", value="", placeholder="Optional context", key="mgr_token_note")

            if st.button("🔑 Generate Token", key="btn_gen_reset_token", type="primary"):
                try:
                    tok = AUTH.admin_generate_reset_token_for_user(
                        sel_username,
                        admin_username=current_username,
                        ttl_seconds=int(ttl_hours2) * 3600,
                        note=token_note or "admin issued token",
                    )
                    st.success(f"✅ Token generated for `{sel_username}`")
                    st.code(tok, language="text")
                except Exception as e:
                    st.error(f"❌ Token generation failed: {str(e)}")

            st.divider()

            # Unlock Account
            st.markdown("### 🔓 Unlock Account")
            st.caption("Clear failed login attempts and remove account lockout")
            if st.button("🔓 Unlock User", key="btn_unlock_user", type="primary"):
                try:
                    ok = AUTH.unlock_user(sel_username, admin_username=current_username)
                    if ok:
                        st.success(f"✅ Account `{sel_username}` unlocked")
                        st.cache_data.clear()
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("❌ Unlock operation failed")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")

            st.divider()

            # Delete User
            st.markdown("### 🗑️ Delete User")
            st.caption("⚠️ **WARNING:** This action cannot be undone. All user data will be permanently removed.")
            
            is_sel_admin = (sel_role == "admin")
            can_delete = (sel_username != current_username) and not (is_sel_admin and admin_count <= 1)
            
            if sel_username == current_username:
                st.warning("⚠️ You cannot delete your own account.")
            elif is_sel_admin and admin_count <= 1:
                st.warning("⚠️ Cannot delete the last administrator.")

            danger = st.checkbox("✅ I understand this action is permanent", value=False, key="confirm_delete")
            if st.button("🗑️ Delete User", type="secondary", disabled=(not danger or not can_delete), key="btn_delete_user"):
                try:
                    ok = AUTH.delete_user(sel_username, admin_username=current_username)
                    if ok:
                        st.success(f"✅ User `{sel_username}` deleted permanently")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ Deletion failed")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")

    st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# TAB 3: All Users
# =========================================================
with tabs[3]:
    st.markdown("""
    <div class="enterprise-card animate-in">
        <div class="card-header">
            <div class="card-title-group">
                <h2 class="card-title">👥 User Directory</h2>
                <p class="card-description">Complete overview of all user accounts</p>
            </div>
        </div>
    """, unsafe_allow_html=True)

    if users:
        q = st.text_input("🔍 Search Users", placeholder="Filter by username...", key="filter_users")
        filtered = [u for u in users if q.lower() in u["username"].lower()] if q else users
        
        if filtered:
            df = pd.DataFrame(filtered)
            df = _format_epoch_columns(df, cols=["created_at", "last_seen"])
            st.dataframe(df, use_container_width=True, height=320)
            st.markdown("### 📥 Download Session Log")
            st.caption("Retrieve log files for specific sessions (if available on server)")
            
            pick_sid = st.text_input("Session ID", placeholder="Enter session_id to download log", key="session_log_id")

            if st.button("🔍 Download Log File", key="dl_session_log"):
                recent = cached_sessions_recent(current_username, limit=500)
                rec = next((s for s in recent if s.session_id == pick_sid), None)
                if not rec:
                    st.error("❌ Session ID not found in recent sessions")
                else:
                    p = str(rec.log_path or "")
                    if not p:
                        st.warning("⚠️ No log path recorded for this session")
                    else:
                        try:
                            data = _safe_read_log_allowlisted(p)
                            st.download_button(
                                "📥 Download Log",
                                data=data,
                                file_name=_safe_filename(Path(p).name),
                                mime="text/plain",
                                key=f"dl_admin_log_{sha_short(p, 12)}",
                            )
                        except Exception as e:
                            st.error(f"❌ Failed to read log: {str(e)}")
        else:
            st.info(f"No users match '{q}'")
    else:
        st.info("📭 No users in the system yet.")

    st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# TAB 4: Password Reset Requests
# =========================================================
with tabs[4]:
    st.markdown("""
    <div class="enterprise-card animate-in">
        <div class="card-header">
            <div class="card-title-group">
                <h2 class="card-title">🔑 Password Reset Requests</h2>
                <p class="card-description">Review and approve pending password reset requests</p>
            </div>
        </div>
    """, unsafe_allow_html=True)

    try:
        pending = cached_reset_requests(current_username, status="pending")
    except Exception as e:
        st.error(f"⚠️ Failed to load reset requests: {e}")
        pending = []

    if not pending:
        st.success("✅ No pending reset requests at this time.")
    else:
        st.info(f"📋 {len(pending)} pending request(s) require review")
        
        for i, req in enumerate(pending):
            req = _series_to_dict(req)
            
            st.markdown(f"""
            <div class="enterprise-card" style="border-left: 4px solid var(--info); margin-bottom: 16px;">
                <h4 style="margin: 0 0 8px 0;">Request #{req['id']} — User: <code>{req['username']}</code></h4>
                <p style="margin: 0; color: var(--text-secondary); font-size: 0.875rem;">
                    Submitted: {_fmt_ts(req.get('created_at'))}
                </p>
            </div>
            """, unsafe_allow_html=True)

            col1, col2, col3 = st.columns([2, 3, 5])
            with col1:
                ttl_hours = st.number_input(
                    "Token TTL",
                    min_value=1,
                    max_value=168,
                    value=24,
                    step=1,
                    key=f"rr_ttl_{req['id']}",
                    help="Hours until token expires"
                )
            with col2:
                note = st.text_input(
                    "Admin Note",
                    value=_safe_str(req.get("note")),
                    key=f"rr_note_{req['id']}",
                    placeholder="Optional note"
                )

            col_a, col_b, col_c = st.columns([1, 1, 4])
            with col_a:
                if st.button(f"✅ Approve", key=f"rr_appr_{req['id']}", type="primary"):
                    try:
                        tok = AUTH.admin_generate_token_for_request(req["id"], current_username, ttl=int(ttl_hours * 3600))
                        if tok:
                            AUTH.set_reset_request_status(req["id"], "approved", current_username, note)
                            st.success(f"✅ Request #{req['id']} approved")
                            st.code(tok, language="text")
                            st.cache_data.clear()
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("❌ Request not found or already processed")
                    except Exception as e:
                        st.error(f"❌ Failed: {str(e)}")

            with col_b:
                if st.button(f"🛑 Reject", key=f"rr_rej_{req['id']}", type="secondary"):
                    try:
                        ok = AUTH.set_reset_request_status(req["id"], "rejected", current_username, note or "rejected")
                        if ok:
                            st.success(f"✅ Request #{req['id']} rejected")
                            st.cache_data.clear()
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error("❌ Request not found")
                    except Exception as e:
                        st.error(f"❌ Failed: {str(e)}")

            st.divider()

    st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# TAB 5: Audit Logs
# =========================================================
with tabs[5]:
    st.markdown("""
    <div class="enterprise-card animate-in">
        <div class="card-header">
            <div class="card-title-group">
                <h2 class="card-title">📝 Administrator Audit Trail</h2>
                <p class="card-description">Complete history of administrative actions</p>
            </div>
        </div>
    """, unsafe_allow_html=True)

    try:
        logs = cached_audit_logs(current_username, limit=500)
    except Exception as e:
        st.error(f"⚠️ Failed to load audit logs: {e}")
        logs = []

    if logs:
        df = pd.DataFrame(logs)
        df = _format_epoch_columns(df, cols=["created_at"])
        st.dataframe(df, use_container_width=True, height=420)

        st.download_button(
            "📥 Export Audit Logs (CSV)",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=f"ret_audit_logs_{int(time.time())}.csv",
            mime="text/csv",
        )
    else:
        st.info("📭 No audit logs recorded yet.")

    st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# TAB 6: Operational Logs
# =========================================================
with tabs[6]:
    st.markdown("""
    <div class="enterprise-card animate-in">
        <div class="card-header">
            <div class="card-title-group">
                <h2 class="card-title">🧾 Operational Logs</h2>
                <p class="card-description">System events, errors, and operations</p>
            </div>
        </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        area = st.selectbox("Filter by Area", ["(all)", "AUTH", "ADMIN_AGENT", "MAIN", "AI", "CLEANUP", "APP"], index=0)
    with col2:
        limit = st.slider("Maximum Rows", 50, 2000, 300, step=50)

    try:
        logs = cached_ops_logs(current_username, None if area == "(all)" else area, int(limit))
    except Exception as e:
        st.error(f"⚠️ Failed to load ops logs: {e}")
        logs = []

    if logs:
        df = pd.DataFrame(logs)
        df = _format_epoch_columns(df, cols=["created_at"])
        st.dataframe(df, use_container_width=True, height=420)

        st.download_button(
            "📥 Export Ops Logs (CSV)",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=f"ret_ops_logs_{int(time.time())}.csv",
            mime="text/csv",
        )
    else:
        st.info("📭 No operational logs found.")

    st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# TAB 7: Sessions & Cleanup
# =========================================================
with tabs[7]:
    st.markdown("""
    <div class="enterprise-card animate-in">
        <div class="card-header">
            <div class="card-title-group">
                <h2 class="card-title">📁 Session Management & Cleanup</h2>
                <p class="card-description">Monitor active sessions and manage idle cleanup</p>
            </div>
        </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        idle_minutes = st.number_input(
            "Idle Timeout (minutes)",
            min_value=5,
            max_value=24 * 60,
            value=int(IDLE_CLEANUP_SECONDS_DEFAULT // 60),
            step=5,
        )
    with col2:
        force = st.checkbox("Force cleanup (FORCE_CLEANED_IDLE status)", value=False)

    cutoff = int(time.time() - int(idle_minutes) * 60)
    eligible = cached_sessions_eligible(current_username, cutoff)

    if eligible:
        df = pd.DataFrame([{
            "session_id": s.session_id,
            "username": s.username,
            "created_at": s.created_at,
            "last_seen": s.last_seen,
            "status": s.status,
            "temp_dir": s.temp_dir,
        } for s in eligible])
        df = _format_epoch_columns(df, cols=["created_at", "last_seen"])
        
        st.warning(f"⚠️ {len(df)} idle sessions eligible for cleanup")
        st.dataframe(df, use_container_width=True, height=260)

        if st.button("🧹 Execute Cleanup Now", type="primary"):
            summary = cleanup_idle_sessions_postgres(int(idle_minutes) * 60, force=force)
            st.success(f"✅ Cleanup complete: {summary['deleted']} sessions cleaned, {summary['failed']} failed")
            st.cache_data.clear()
            time.sleep(1)
            st.rerun()
    else:
        st.success("✅ No idle sessions eligible for cleanup at this threshold.")

    st.divider()

    # Recent Sessions
    st.markdown("### 📊 Recent Session Activity")
    recent = cached_sessions_recent(current_username, limit=500)

    if recent:
        df = pd.DataFrame([{
            "session_id": s.session_id,
            "username": s.username,
            "created_at": s.created_at,
            "last_seen": s.last_seen,
            "status": s.status,
            "temp_dir": s.temp_dir,
            "log_path": s.log_path,
        } for s in recent])
        df = _format_epoch_columns(df, cols=["created_at", "last_seen"])
        st.dataframe(df, use_container_width=True, height=420)

        st.markdown("### 📥 Download a Session Log (if available on server)")
        pick_sid = st.text_input("Enter session_id", value="", key="dl_pick_sid")

        if st.button("🔎 Find & Download Log", key="dl_find_log"):
            rec = next((s for s in recent if s.session_id == pick_sid), None)
            if not rec:
                st.error("❌ session_id not found in recent sessions.")
            else:
                p = str(rec.log_path or "")
                if not p:
                    st.error("⚠️ Log path is empty for this session.")
                else:
                    try:
                        data = _safe_read_log_allowlisted(p)  # allowlisted read
                        st.download_button(
                            "📥 Download Log",
                            data=data,
                            file_name=_safe_filename(Path(p).name),
                            mime="text/plain",
                            key=f"dl_admin_log_{sha_short(p, 12)}",
                        )
                    except Exception as e:
                        st.error(f"❌ Failed to read log: {str(e)}")
    else:
        st.caption("📭 No recent sessions found yet.")

    st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# FOOTER
# =========================================================
st.markdown("""
<div class="admin-footer">
    <p style="margin: 0 0 8px 0;">
        <strong>RET<span style="color: var(--brand-primary);">v4</span> Administration Console</strong>
    </p>
    <p style="margin: 0; font-size: 0.8125rem;">
        © 2025 TATA Consultancy Services Limited • All Rights Reserved
    </p>
</div>
""", unsafe_allow_html=True)
