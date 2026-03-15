from __future__ import annotations

from pathlib import Path

def test_dashboard_has_live_controls_link() -> None:
    tpl = Path("ui/templates/dashboard_v2.html").read_text(encoding="utf-8")
    assert 'href="/control/live"' in tpl
    assert "live-controls-link" in tpl
    assert "live-controls-error" in tpl
    assert "dashboard-admin-token-input" in tpl
    assert "dashboard-admin-token-save" in tpl


def test_base_template_exposes_admin_token_error_accessor() -> None:
    tpl = Path("ui/templates/_base.html").read_text(encoding="utf-8")
    assert "ps_admin_token" in tpl
    assert "getLastError" in tpl
    assert "window.psAdminTokenHeaders" in tpl
    assert "window.psAdminTokenSave" in tpl
    assert "window.psAdminTokenLoad" in tpl
    assert "window.__psAdminHelperLoaded = true" in tpl


def test_control_live_without_admin_token_returns_friendly_html() -> None:
    body = Path("ui/templates/control_live_locked.html").read_text(encoding="utf-8")
    assert "ADMIN_TOKEN is not configured" in body
    assert "Set ADMIN_TOKEN and restart the app." in body
    assert "execution_mode" in body
    assert "live_executor" in body
    assert "ready_for_live" in body
    assert "Live executor requirements (read-only)" in body
    assert "live_missing" in body
    assert "live_not_ready_reason" in body
    assert "live-admin-token-input" in body
    assert "live-admin-token-status" in body
    assert "localStorage" in body
