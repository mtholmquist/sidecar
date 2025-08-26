# sidecar/ui/ui.py
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from textual.app import App, ComposeResult
from textual.widgets import Static
from textual.containers import Vertical


def _last_json_line(path: str) -> Optional[Dict[str, Any]]:
    """Return the last valid JSON object from a jsonl file, or None."""
    try:
        if not os.path.exists(path) or os.path.isdir(path):
            return None
        with open(path, "rb") as f:
            try:
                f.seek(-4096, os.SEEK_END)
            except OSError:
                f.seek(0)
            chunk = f.read().decode("utf-8", errors="ignore").splitlines()
        for line in reversed(chunk):
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                return json.loads(line)
            except Exception:
                continue
    except Exception:
        pass
    return None


class SidecarUI(App):
    """
    Minimal, non-interactive UI:
      • Title + status bar
      • Single scrolling 'details' pane with full suggestions
    """

    CSS = """
    Screen { layout: vertical; }
    #title   { height: 1; content-align: center middle; }
    #status  { height: 1; padding: 0 1; }
    #details { height: 1fr; padding: 0 1; overflow: auto; }
    """

    BINDINGS = []  # No key/mouse interaction required

    def __init__(self, audit_path: str):
        super().__init__()
        self.audit_path = os.path.expanduser(audit_path)
        self._last_mtime: float = 0.0
        self.title_bar: Static | None = None
        self.status: Static | None = None
        self.details: Static | None = None

    def compose(self) -> ComposeResult:
        self.title_bar = Static("sidecar suggestions", id="title")
        self.status = Static(f"following: {self.audit_path}", id="status")
        self.details = Static(id="details")
        yield Vertical(self.title_bar, self.status, self.details)

    def on_mount(self) -> None:
        # Poll the audit file periodically and refresh if it changed
        self.set_interval(0.5, self._tick)

    # ---------- rendering ----------
    def _render_details(self, evt: Dict[str, Any]) -> None:
        assert self.details is not None

        plan = evt.get("plan", {}) or {}
        actions = plan.get("next_actions", []) or []
        notes = plan.get("notes", []) or []
        last_cmd = str(evt.get("cmd", "") or "")

        lines: list[str] = []
        lines.append(f"[b]last:[/b] {last_cmd if last_cmd else '—'}")
        if notes:
            lines.append(f"[b]notes:[/b] " + " ".join(notes))

        lines.append("")
        lines.append("[b]suggestions[/b]")

        if actions:
            for i, a in enumerate(actions, 1):
                cmd = str(a.get("cmd", "")).strip().replace("\n", " ")
                reason = str(a.get("reason", "")).strip().replace("\n", " ")
                noise = str(a.get("noise", "")).strip()
                safety = str(a.get("safety", "")).strip()
                lines.append(f"[b]{i}[/b] {cmd}")
                lines.append(f"    [dim]why:[/dim] {reason}  [dim]noise:[/dim] {noise}  [dim]safety:[/dim] {safety}")
        else:
            lines.append("[dim]No suggestions yet.[/dim]")

        self.details.update("\n".join(lines))

    # ---------- file polling ----------
    def _tick(self) -> None:
        try:
            mtime = os.path.getmtime(self.audit_path) if os.path.exists(self.audit_path) else 0.0
        except Exception:
            mtime = 0.0

        if mtime <= self._last_mtime:
            return
        self._last_mtime = mtime

        evt = _last_json_line(self.audit_path)
        if evt:
            if self.status:
                last_cmd = str(evt.get("cmd", "") or "")
                self.status.update(f"following: {self.audit_path}    |    last: {last_cmd if last_cmd else '—'}")
            self._render_details(evt)


def run_ui(audit: str) -> None:
    if not audit:
        raise SystemExit("[!] ui requires --audit <path>")
    app = SidecarUI(audit_path=audit)
    app.run()
