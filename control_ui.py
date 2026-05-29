#!/usr/bin/env python3
"""
================================================================================
DEPRECATED — control_ui.py  (Stand: 2026-05-29)
================================================================================
Diese Datei ist nicht mehr das aktive UI-System.

Nachfolger : desktop/  (PySide6-Native-App)
Einstieg   : python desktop/app.py  oder  start_desktop.cmd

Grund: Architekturentscheidung Desktop-first.
  - PySide6  = primäre Benutzeroberfläche
  - FastAPI  = Infrastrukturmodul (Remote/API/externe Worker)
  - Gradio   = nicht mehr aktiv installiert (optional-dependency "legacy-ui")
  - Browser  = kein primäres Ziel mehr

Diese Datei bleibt als Referenz erhalten. Nicht für Produktion verwenden.
Wenn Gradio trotzdem benötigt wird: uv sync --extra legacy-ui
================================================================================

ECHO Orchestrator — Lokale Chat-Control-UI (Gradio) [LEGACY]
Dünne Schicht über FastAPI — keine Orchestrierungslogik.
"""

from __future__ import annotations

import argparse
import os
from typing import Any

import gradio as gr
import httpx

DEFAULT_API = os.environ.get("ECHO_API_URL", "http://127.0.0.1:8020")
DEFAULT_REVIEWER = os.environ.get("ECHO_REVIEWER", "Michael")

# UI-Statuslabels (vereinfacht für Anzeige)
STATUS_LABELS = {
    "pending": "planning",
    "awaiting_approval": "waiting_for_approval",
    "approved": "running",
    "in_progress": "running",
    "pending_diff": "waiting_for_approval",
    "completed": "completed",
    "failed": "failed",
    "rejected": "failed",
    "pending_approval": "waiting_for_approval",
    "approved_plan": "running",
    "rejected_plan": "failed",
}


class EchoApiClient:
    """Synchroner httpx-Client für FastAPI."""

    def __init__(self, base_url: str, timeout: float = 300.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def _handle(self, r: httpx.Response) -> Any:
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text[:500])
            except Exception:
                detail = r.text[:500]
            raise RuntimeError(f"HTTP {r.status_code}: {detail}")
        if r.status_code == 204:
            return None
        return r.json()

    def health(self) -> dict:
        return self._handle(self._client.get("/health"))

    def list_projects(self) -> dict[str, str]:
        return self._handle(self._client.get("/api/v1/projects"))

    def get_active_project(self) -> dict:
        return self._handle(self._client.get("/api/v1/projects/active"))

    def set_project(self, name: str) -> dict:
        return self._handle(
            self._client.post(
                "/api/v1/projects/active",
                json={"name": name},
            )
        )

    def create_plan(self, intent: str, reviewer: str) -> dict:
        return self._handle(
            self._client.post(
                "/api/v1/plan",
                json={"intent": intent, "reviewer": reviewer, "context": {}},
            )
        )

    def approve_plan(self, plan_id: str, approved: bool, reviewer: str) -> list:
        data = self._handle(
            self._client.post(
                f"/api/v1/plan/{plan_id}/approve",
                json={
                    "approved": approved,
                    "reviewer": reviewer,
                    "comment": "via control_ui",
                },
            )
        )
        return data if isinstance(data, list) else []

    def approve_task(self, task_id: str, approved: bool, reviewer: str) -> dict:
        return self._handle(
            self._client.post(
                f"/api/v1/tasks/{task_id}/approve",
                json={
                    "approved": approved,
                    "reviewer": reviewer,
                    "comment": "Gate 1 via control_ui",
                },
            )
        )

    def approve_diff(self, task_id: str, approved: bool, reviewer: str) -> dict:
        return self._handle(
            self._client.post(
                f"/api/v1/tasks/{task_id}/approve-diff",
                json={
                    "approved": approved,
                    "reviewer": reviewer,
                    "comment": "Gate 2 via control_ui",
                },
            )
        )

    def get_task(self, task_id: str) -> dict:
        return self._handle(self._client.get(f"/api/v1/tasks/{task_id}"))

    def get_diff(self, task_id: str) -> dict:
        return self._handle(self._client.get(f"/api/v1/tasks/{task_id}/diff"))

    def list_tasks(self, limit: int = 30) -> list:
        return self._handle(self._client.get(f"/api/v1/tasks?limit={limit}"))


def _ui_status(raw: str) -> str:
    return STATUS_LABELS.get(raw, raw)


def _format_plan(plan: dict) -> str:
    lines = [
        f"**{plan.get('plan_title', '?')}**",
        f"Plan-ID: `{plan.get('plan_id', '?')[:8]}...`",
        "",
        plan.get("summary", ""),
        "",
        f"Geschätzte Tokens: ~{plan.get('estimated_total_tokens', 0)}",
        "",
        "### Tasks",
    ]
    for i, t in enumerate(plan.get("tasks", []), 1):
        lines.append(
            f"{i}. **{t.get('title', '?')}** — `{t.get('worker_type', '?')}` "
            f"({t.get('priority', '?')})"
        )
        if t.get("rationale"):
            lines.append(f"   _{t['rationale']}_")
    return "\n".join(lines)


def _format_history(tasks: list) -> str:
    if not tasks:
        return "_Keine Tasks in der History._"
    rows = ["| Status | Titel | Task-ID |", "|---|---|---|"]
    for t in sorted(tasks, key=lambda x: x.get("created_at", ""), reverse=True):
        rows.append(
            f"| {_ui_status(t.get('status', '?'))} | "
            f"{t.get('title', '?')[:40]} | `{t.get('task_id', '?')[:8]}` |"
        )
    return "\n".join(rows)


def _format_task_summary(
    task: dict,
    api_message: str = "",
    diff_data: dict | None = None,
) -> str:
    """Ergebnis wie run_pipeline.py print_summary — für Chat/Result-Panel."""
    lines = [
        f"**Task:** {task.get('title', '?')}",
        f"- Status: `{task.get('status', '?')}`",
        f"- Task-ID: `{task.get('task_id', '?')}`",
        f"- Worker: `{task.get('worker_type', '?')}`",
    ]
    if api_message:
        lines.append(f"- Meldung: {api_message}")
    if diff_data and diff_data.get("branch"):
        lines.append(f"- Branch: `{diff_data['branch']}`")
        lines.append(f"- Diff-Zeilen: {diff_data.get('diff_lines', 0)}")
    result = task.get("result")
    if result:
        artifacts = result.get("artifacts") or []
        if artifacts:
            lines.append(f"- Geänderte Dateien: {', '.join(artifacts)}")
        output = str(result.get("output", "")).strip()
        if output:
            preview_lines = output.splitlines()[:12]
            preview = "\n".join(preview_lines)
            if len(output.splitlines()) > 12:
                preview += "\n… (gekürzt)"
            lines.extend(["", "**Worker-Output:**", f"```\n{preview}\n```"])
        if result.get("error"):
            lines.append(f"- Fehler: {result['error']}")
    return "\n".join(lines)


def _format_diff_panel(diff_data: dict) -> str:
    diff = diff_data.get("diff", "") or ""
    if not diff:
        return "_Kein Diff — Worker hat keine Dateien verändert._"
    branch = diff_data.get("branch") or "?"
    lines_count = diff_data.get("diff_lines", len(diff.splitlines()))
    header = f"Branch: {branch}  |  {lines_count} Zeilen\n{'─' * 60}\n"
    return header + diff


def build_ui(api_url: str, reviewer: str, ui_port: int) -> gr.Blocks:
    client = EchoApiClient(api_url)

    def session_init() -> dict:
        return {
            "plan_id": None,
            "plan": None,
            "task_ids": [],
            "active_task_idx": 0,
            "active_task_id": None,
            "phase": "idle",
            "plan_display": "",
            "result_display": "",
            "last_result_task": None,
        }

    def check_server() -> str:
        try:
            h = client.health()
            return f"API OK — v{h.get('version', '?')} ({api_url})"
        except Exception as exc:
            return f"API nicht erreichbar: {exc}"

    def load_project_choices() -> list[tuple[str, str]]:
        try:
            data = client.list_projects()
            return [(key, key) for key in data.keys()]
        except Exception:
            return []

    def on_project_change(project_name: str, sess: dict) -> tuple[str, dict]:
        if not project_name:
            return "Kein Projekt gewählt.", sess
        try:
            r = client.set_project(project_name)
            path = r.get("path", "")
            return f"Zielprojekt: **{r.get('name', project_name)}** → `{path}`", sess
        except Exception as exc:
            return f"Fehler: {exc}", sess

    def refresh_history() -> str:
        try:
            tasks = client.list_tasks()
            return _format_history(tasks)
        except Exception as exc:
            return f"History-Fehler: {exc}"

    def poll_status(sess: dict) -> tuple[str, str, str, str, dict]:
        """Status, Plan, Diff, Ergebnis aus Session + API."""
        result_md = sess.get("result_display", "")
        if not sess.get("active_task_id"):
            phase = sess.get("phase", "idle")
            if phase == "plan_pending" and sess.get("plan"):
                return (
                    "waiting_for_approval (Plan — Gate 0)",
                    _format_plan(sess["plan"]),
                    "",
                    result_md,
                    sess,
                )
            return "idle", sess.get("plan_display", ""), "", result_md, sess

        task_id = sess["active_task_id"]
        try:
            task = client.get_task(task_id)
            raw_status = task.get("status", "?")
            ui = _ui_status(raw_status)
            diff_text = ""
            diff_data: dict | None = None

            if raw_status == "awaiting_approval":
                sess["phase"] = "task_gate1"
            elif raw_status == "pending_diff":
                sess["phase"] = "task_gate2"
                diff_data = client.get_diff(task_id)
                diff_text = _format_diff_panel(diff_data)
            elif raw_status in ("in_progress", "approved"):
                diff_text = "_Worker läuft … (Gate 1 freigegeben)_"
            elif raw_status in ("completed", "failed", "rejected"):
                if not result_md or sess.get("last_result_task") != task_id:
                    diff_data = None
                    try:
                        diff_data = client.get_diff(task_id)
                    except Exception:
                        pass
                    result_md = _format_task_summary(task, diff_data=diff_data)
                    sess["result_display"] = result_md
                    sess["last_result_task"] = task_id

            plan_disp = sess.get("plan_display", "")
            phase = sess.get("phase", "idle")
            gate_hint = ""
            if phase == "task_gate1" and raw_status == "awaiting_approval":
                gate_hint = " — Gate 1: Worker freigeben?"
            elif phase == "task_gate2" and raw_status == "pending_diff":
                gate_hint = " — Gate 2: Diff committen?"
            return f"{ui} (`{raw_status}`){gate_hint}", plan_disp, diff_text, result_md, sess
        except Exception as exc:
            return f"Fehler: {exc}", "", "", result_md, sess

    def send_chat(
        message: str,
        history: list,
        sess: dict,
        project_name: str,
    ) -> tuple[list, str, str, str, str, dict]:
        if not message or not message.strip():
            status, plan_md, diff_md, result_md, _ = poll_status(sess)
            return history, status, plan_md, diff_md, result_md, sess

        if not project_name:
            history = history + [[message.strip(), "Bitte zuerst ein Zielprojekt wählen."]]
            status, plan_md, diff_md, result_md, _ = poll_status(sess)
            return history, status, plan_md, diff_md, result_md, sess

        history = history + [[message.strip(), None]]
        sess["phase"] = "planning"
        sess["plan_display"] = "_Planner läuft (Ollama) …_"
        sess["result_display"] = ""

        try:
            plan = client.create_plan(message.strip(), reviewer)
            sess["plan_id"] = plan["plan_id"]
            sess["plan"] = plan
            sess["plan_display"] = _format_plan(plan)
            sess["phase"] = "plan_pending"
            reply = (
                f"Plan **{plan.get('plan_title')}** mit {len(plan.get('tasks', []))} "
                f"Task(s). Gate 0: Plan freigeben oder ablehnen."
            )
        except Exception as exc:
            sess["phase"] = "idle"
            sess["plan_display"] = ""
            reply = f"Planner-Fehler: {exc}"

        history[-1][1] = reply
        status, plan_md, diff_md, result_md, _ = poll_status(sess)
        return history, status, plan_md, diff_md, result_md, sess

    def plan_approve(approved: bool, sess: dict, history: list) -> tuple[list, str, str, str, str, dict]:
        plan_id = sess.get("plan_id")
        if not plan_id:
            status, plan_md, diff_md, result_md, _ = poll_status(sess)
            return history, status, plan_md, diff_md, result_md, sess
        try:
            submitted = client.approve_plan(plan_id, approved, reviewer)
            if not approved:
                sess["phase"] = "done"
                history = history + [[None, "Plan abgelehnt. Keine Tasks eingereicht."]]
                status, plan_md, diff_md, result_md, _ = poll_status(sess)
                return history, "failed (Plan rejected)", plan_md, diff_md, result_md, sess

            task_ids = [r["task_id"] for r in submitted]
            sess["task_ids"] = task_ids
            sess["active_task_idx"] = 0
            sess["active_task_id"] = task_ids[0] if task_ids else None
            sess["phase"] = "task_gate1"
            sess["result_display"] = ""
            ids_preview = ", ".join(f"`{t[:8]}`" for t in task_ids)
            history = history + [
                [
                    None,
                    f"Plan freigegeben. {len(task_ids)} Task(s) eingereicht: {ids_preview}. "
                    f"Gate 1: Worker freigeben.",
                ]
            ]
        except Exception as exc:
            history = history + [[None, f"Plan-Freigabe fehlgeschlagen: {exc}"]]
        status, plan_md, diff_md, result_md, _ = poll_status(sess)
        return history, status, plan_md, diff_md, result_md, sess

    def gate1(approved: bool, sess: dict, history: list) -> tuple[list, str, str, str, str, dict]:
        task_id = sess.get("active_task_id")
        if not task_id:
            status, plan_md, diff_md, result_md, _ = poll_status(sess)
            return history, status, plan_md, diff_md, result_md, sess
        try:
            if not approved:
                resp = client.approve_task(task_id, False, reviewer)
                history = history + [
                    [None, f"Gate 1 abgelehnt für `{task_id[:8]}`. {resp.get('message', '')}"]
                ]
                sess = _advance_task(sess)
                status, plan_md, diff_md, result_md, _ = poll_status(sess)
                return history, status, plan_md, diff_md, result_md, sess

            history = history + [[None, f"Gate 1 OK — Worker startet für `{task_id[:8]}` …"]]
            resp = client.approve_task(task_id, True, reviewer)
            task = client.get_task(task_id)
            resp_status = resp.get("status", task.get("status", ""))
            message = resp.get("message", "")

            if resp_status == "pending_diff":
                sess["phase"] = "task_gate2"
                history = history + [
                    [None, f"Worker fertig. {message} Gate 2: Diff prüfen und committen."]
                ]
            elif resp_status in ("completed", "failed", "rejected"):
                summary = _format_task_summary(task, message)
                sess["result_display"] = summary
                sess["last_result_task"] = task_id
                history = history + [[None, summary]]
                if resp_status == "completed" and "Keine Code-Änderungen" in message:
                    history = history + [[None, "Kein Diff-Gate nötig — Task direkt abgeschlossen."]]
                sess = _advance_task(sess)
            else:
                history = history + [[None, f"Unerwarteter Status nach Gate 1: {resp_status}. {message}"]]
        except Exception as exc:
            history = history + [[None, f"Gate 1 Fehler: {exc}"]]
        status, plan_md, diff_md, result_md, _ = poll_status(sess)
        return history, status, plan_md, diff_md, result_md, sess

    def gate2(approved: bool, sess: dict, history: list) -> tuple[list, str, str, str, str, dict]:
        task_id = sess.get("active_task_id")
        if not task_id:
            status, plan_md, diff_md, result_md, _ = poll_status(sess)
            return history, status, plan_md, diff_md, result_md, sess
        try:
            diff_data = client.get_diff(task_id)
            if not diff_data.get("diff") and approved:
                history = history + [[None, "Kein Diff vorhanden — Gate 2 übersprungen."]]
                sess = _advance_task(sess)
                status, plan_md, diff_md, result_md, _ = poll_status(sess)
                return history, status, plan_md, diff_md, result_md, sess

            resp = client.approve_diff(task_id, approved, reviewer)
            message = resp.get("message", "")
            task = client.get_task(task_id)
            if approved:
                summary = _format_task_summary(task, message, diff_data)
                sess["result_display"] = summary
                sess["last_result_task"] = task_id
                history = history + [[None, f"Gate 2: Commit OK.\n\n{summary}"]]
            else:
                history = history + [[None, f"Gate 2: Diff verworfen. {message}"]]
            sess = _advance_task(sess)
        except Exception as exc:
            history = history + [[None, f"Gate 2 Fehler: {exc}"]]
        status, plan_md, diff_md, result_md, _ = poll_status(sess)
        return history, status, plan_md, diff_md, result_md, sess

    def _advance_task(sess: dict) -> dict:
        idx = sess.get("active_task_idx", 0) + 1
        ids = sess.get("task_ids", [])
        if idx < len(ids):
            sess["active_task_idx"] = idx
            sess["active_task_id"] = ids[idx]
            sess["phase"] = "task_gate1"
            sess["result_display"] = ""
        else:
            sess["active_task_id"] = None
            sess["phase"] = "done"
        return sess

    def init_project_dropdown() -> tuple[gr.Dropdown, str]:
        choices = load_project_choices()
        try:
            active = client.get_active_project()
            name = active.get("name")
            path = active.get("path", "")
            if name and any(k == name for k, _ in choices):
                return gr.Dropdown(choices=choices, value=name), f"Zielprojekt: **{name}** → `{path}`"
        except Exception:
            pass
        return gr.Dropdown(choices=choices), "Kein Projekt gewählt — bitte Dropdown setzen."

    with gr.Blocks(title="ECHO Control") as demo:
        gr.Markdown("# ECHO Orchestrator — Control UI")
        api_status = gr.Markdown(check_server())
        sess_state = gr.State(session_init())

        with gr.Row():
            project_dd = gr.Dropdown(
                label="Zielprojekt",
                choices=load_project_choices(),
                interactive=True,
            )
            btn_reload_projects = gr.Button("Projekte neu laden", scale=0)
            project_status = gr.Markdown("")

        project_dd.change(
            on_project_change,
            inputs=[project_dd, sess_state],
            outputs=[project_status, sess_state],
        )

        def reload_projects() -> gr.Dropdown:
            return gr.Dropdown(choices=load_project_choices())

        btn_reload_projects.click(reload_projects, outputs=[project_dd])

        status_box = gr.Textbox(label="Live-Status", interactive=False)
        chatbot = gr.Chatbot(label="Chat", height=320)
        msg = gr.Textbox(label="Anforderung (natürliche Sprache)", lines=3)
        btn_send = gr.Button("Senden / Plan erstellen", variant="primary")

        with gr.Row():
            btn_plan_ok = gr.Button("Plan freigeben (Gate 0)")
            btn_plan_no = gr.Button("Plan ablehnen")

        plan_md = gr.Markdown(label="Plan")
        diff_box = gr.Textbox(label="Git Diff (Gate 2)", lines=18, max_lines=40)
        result_md = gr.Markdown(label="Ergebnis", value="_Noch kein Task abgeschlossen._")

        with gr.Row():
            btn_g1_ok = gr.Button("Gate 1: Worker starten")
            btn_g1_no = gr.Button("Gate 1: Ablehnen")
        with gr.Row():
            btn_g2_ok = gr.Button("Gate 2: Commit + Push")
            btn_g2_no = gr.Button("Gate 2: Verwerfen")

        history_md = gr.Markdown(value=refresh_history(), label="Task-History")
        btn_refresh = gr.Button("Status + History aktualisieren")

        btn_send.click(
            send_chat,
            inputs=[msg, chatbot, sess_state, project_dd],
            outputs=[chatbot, status_box, plan_md, diff_box, result_md, sess_state],
        ).then(lambda: "", outputs=[msg])

        btn_plan_ok.click(
            lambda s, h: plan_approve(True, s, h),
            inputs=[sess_state, chatbot],
            outputs=[chatbot, status_box, plan_md, diff_box, result_md, sess_state],
        ).then(refresh_history, outputs=[history_md])
        btn_plan_no.click(
            lambda s, h: plan_approve(False, s, h),
            inputs=[sess_state, chatbot],
            outputs=[chatbot, status_box, plan_md, diff_box, result_md, sess_state],
        )
        btn_g1_ok.click(
            lambda s, h: gate1(True, s, h),
            inputs=[sess_state, chatbot],
            outputs=[chatbot, status_box, plan_md, diff_box, result_md, sess_state],
        ).then(refresh_history, outputs=[history_md])
        btn_g1_no.click(
            lambda s, h: gate1(False, s, h),
            inputs=[sess_state, chatbot],
            outputs=[chatbot, status_box, plan_md, diff_box, result_md, sess_state],
        ).then(refresh_history, outputs=[history_md])
        btn_g2_ok.click(
            lambda s, h: gate2(True, s, h),
            inputs=[sess_state, chatbot],
            outputs=[chatbot, status_box, plan_md, diff_box, result_md, sess_state],
        ).then(refresh_history, outputs=[history_md])
        btn_g2_no.click(
            lambda s, h: gate2(False, s, h),
            inputs=[sess_state, chatbot],
            outputs=[chatbot, status_box, plan_md, diff_box, result_md, sess_state],
        ).then(refresh_history, outputs=[history_md])

        btn_refresh.click(
            lambda s: (*poll_status(s)[0:4], refresh_history(), s),
            inputs=[sess_state],
            outputs=[status_box, plan_md, diff_box, result_md, history_md, sess_state],
        )

        poll_timer = gr.Timer(3)
        poll_timer.tick(
            lambda s: poll_status(s)[0:4] + (s,),
            inputs=[sess_state],
            outputs=[status_box, plan_md, diff_box, result_md, sess_state],
        )
        poll_timer.tick(refresh_history, outputs=[history_md])

        demo.load(init_project_dropdown, outputs=[project_dd, project_status])
        demo.load(
            lambda s: poll_status(s)[0:4],
            inputs=[sess_state],
            outputs=[status_box, plan_md, diff_box, result_md],
        )
        demo.load(refresh_history, outputs=[history_md])

    return demo, client, ui_port


def main() -> None:
    parser = argparse.ArgumentParser(description="ECHO Control UI (Gradio)")
    parser.add_argument("--api", default=DEFAULT_API, help="FastAPI base URL")
    parser.add_argument("--reviewer", default=DEFAULT_REVIEWER)
    parser.add_argument("--port", type=int, default=int(os.environ.get("ECHO_UI_PORT", "7860")))
    args = parser.parse_args()

    demo, client, _port = build_ui(args.api, args.reviewer, args.port)
    try:
        demo.launch(
            server_name="127.0.0.1",
            server_port=args.port,
            show_error=True,
        )
    finally:
        client.close()


if __name__ == "__main__":
    main()
