"""
ECHO Orchestrator — Chat UI
"""
from __future__ import annotations
import threading
import tkinter as tk
from tkinter import ttk
import httpx
from planner import Planner

BG_DARK = "#1e1e1e"
BG_INPUT = "#2a2a2a"
BG_BUTTON = "#3a3a3a"
BG_BTN_YES = "#1e4d2b"
BG_BTN_NO = "#4d1e1e"
FG_TEXT = "#d4d4d4"
FG_DIMMED = "#808080"
FG_ACCENT = "#569cd6"
FG_SUCCESS = "#4ec994"
FG_WARNING = "#ce9178"
FG_ERROR = "#f44747"
FG_PLAN = "#dcdcaa"

ORCHESTRATOR_URL = "http://127.0.0.1:8020"
REVIEWER_NAME = "Mica"


class EchoChatUI:

    _SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.planner = Planner()
        self._current_plan: dict | None = None
        self._current_task_id: str | None = None
        self._state: str = "idle"
        self._spinner_idx: int = 0
        self._spinner_job = None
        self._build_ui()
        self._post_system("ECHO Orchestrator gestartet.")
        self._check_server()

    def _build_ui(self) -> None:
        self.root.title("ECHO Orchestrator")
        self.root.geometry("820x640")
        self.root.minsize(600, 400)
        self.root.configure(bg=BG_DARK)
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Dark.Vertical.TScrollbar",
                        gripcount=0,
                        background=BG_BUTTON,
                        darkcolor=BG_DARK,
                        lightcolor=BG_DARK,
                        troughcolor=BG_DARK,
                        bordercolor=BG_DARK,
                        arrowcolor=FG_DIMMED)
        style.map("Dark.Vertical.TScrollbar",
                  background=[("active", FG_DIMMED), ("!active", BG_BUTTON)])
        title_bar = tk.Frame(self.root, bg=BG_DARK, pady=8)
        title_bar.pack(fill=tk.X, padx=16)
        tk.Label(title_bar, text="ECHO Orchestrator", bg=BG_DARK, fg=FG_ACCENT, font=("Consolas", 13, "bold")).pack(side=tk.LEFT)
        self._status_label = tk.Label(title_bar, text="● Verbinde...", bg=BG_DARK, fg=FG_DIMMED, font=("Consolas", 9))
        self._status_label.pack(side=tk.RIGHT)
        chat_frame = tk.Frame(self.root, bg=BG_DARK)
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))
        self._chat = tk.Text(chat_frame, bg=BG_DARK, fg=FG_TEXT, font=("Consolas", 10), wrap=tk.WORD, state=tk.DISABLED, relief=tk.FLAT, borderwidth=0, insertbackground=FG_TEXT, selectbackground=BG_BUTTON, selectforeground=FG_TEXT, inactiveselectbackground=BG_DARK)
        _scrollbar = ttk.Scrollbar(chat_frame, orient=tk.VERTICAL, command=self._chat.yview, style="Dark.Vertical.TScrollbar")
        self._chat.configure(yscrollcommand=_scrollbar.set)
        _scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._chat.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._chat.tag_config("system", foreground=FG_DIMMED)
        self._chat.tag_config("user", foreground=FG_ACCENT)
        self._chat.tag_config("plan", foreground=FG_PLAN)
        self._chat.tag_config("success", foreground=FG_SUCCESS)
        self._chat.tag_config("error", foreground=FG_ERROR)
        self._chat.tag_config("warning", foreground=FG_WARNING)
        self._chat.tag_config("diff", foreground=FG_DIMMED, font=("Consolas", 9))
        self._gate_frame = tk.Frame(self.root, bg=BG_DARK)
        self._gate_frame.pack(fill=tk.X, padx=16, pady=(0, 6))
        self._btn_yes = tk.Button(self._gate_frame, text="✓  Ja, umsetzen", bg=BG_BTN_YES, fg=FG_SUCCESS, font=("Consolas", 10, "bold"), relief=tk.FLAT, padx=16, pady=6, cursor="hand2", command=self._on_yes)
        self._btn_no = tk.Button(self._gate_frame, text="✗  Nein, abbrechen", bg=BG_BTN_NO, fg=FG_ERROR, font=("Consolas", 10, "bold"), relief=tk.FLAT, padx=16, pady=6, cursor="hand2", command=self._on_no)
        input_frame = tk.Frame(self.root, bg=BG_INPUT, pady=6)
        input_frame.pack(fill=tk.X, padx=16, pady=(0, 12))
        self._input = tk.Entry(input_frame, bg=BG_INPUT, fg=FG_TEXT, font=("Consolas", 11), relief=tk.FLAT, insertbackground=FG_TEXT, bd=0)
        self._input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        self._input.bind("<Return>", self._on_send)
        self._input.focus()
        self._send_btn = tk.Button(input_frame, text="→", bg=BG_BUTTON, fg=FG_ACCENT, font=("Consolas", 12, "bold"), relief=tk.FLAT, padx=12, pady=2, cursor="hand2", command=self._on_send)
        self._send_btn.pack(side=tk.RIGHT, padx=(6, 6))
        self._hide_gates()

    def _post(self, text: str, tag: str = "") -> None:
        self._chat.configure(state=tk.NORMAL)
        if tag:
            self._chat.insert(tk.END, text + "\n", tag)
        else:
            self._chat.insert(tk.END, text + "\n")
        self._chat.configure(state=tk.DISABLED)
        self._chat.see(tk.END)

    def _post_system(self, text: str) -> None:
        self._post(f"[System] {text}", "system")

    def _post_user(self, text: str) -> None:
        self._post(f"\nDu: {text}", "user")

    def _post_plan(self, text: str) -> None:
        self._post(f"\n{text}", "plan")

    def _post_success(self, text: str) -> None:
        self._post(f"✓ {text}", "success")

    def _post_error(self, text: str) -> None:
        self._post(f"✗ {text}", "error")

    def _post_warning(self, text: str) -> None:
        self._post(f"⚠ {text}", "warning")

    def _show_gates(self, label_yes: str = "✓  Ja, umsetzen", label_no: str = "✗  Nein, abbrechen") -> None:
        self._btn_yes.config(text=label_yes)
        self._btn_no.config(text=label_no)
        self._btn_yes.pack(side=tk.LEFT, padx=(0, 8))
        self._btn_no.pack(side=tk.LEFT)
        self._input.configure(state=tk.DISABLED)

    def _hide_gates(self) -> None:
        self._btn_yes.pack_forget()
        self._btn_no.pack_forget()
        self._input.configure(state=tk.NORMAL)
        self._input.focus()

    def _on_send(self, event=None) -> None:
        text = self._input.get().strip()
        if not text:
            return
        self._input.delete(0, tk.END)
        if self._state != "idle":
            self._post_warning("Bitte zuerst die aktuelle Gate-Entscheidung treffen." if "gate" in self._state else "Worker läuft noch. Bitte warten.")
            return
        self._post_user(text)
        self._post_system("Planner analysiert ...")
        self._set_busy(True)
        self._spinner_start("Planner")
        threading.Thread(target=self._run_planner, args=(text,), daemon=True).start()

    def _on_yes(self) -> None:
        self._hide_gates()
        if self._state == "awaiting_gate0":
            self._post_success("Freigegeben. Worker wird gestartet ...")
            self._state = "running"
            self._set_busy(True)
            threading.Thread(target=self._run_worker, daemon=True).start()
        elif self._state == "awaiting_gate1":
            self._post_success("Gate 1 freigegeben.")
            self._state = "running"
            self._spinner_start("Worker läuft")
            threading.Thread(target=self._approve_task, args=(self._current_task_id, True), daemon=True).start()
        elif self._state == "awaiting_gate2":
            self._post_success("Diff freigegeben. Wird committed ...")
            self._state = "idle"
            threading.Thread(target=self._approve_diff, args=(self._current_task_id, True), daemon=True).start()

    def _on_no(self) -> None:
        self._hide_gates()
        if self._state == "awaiting_gate0":
            self._post_warning("Abgebrochen. Kein Task erstellt.")
            self._state = "idle"
            self._current_plan = None
        elif self._state in ("awaiting_gate1", "awaiting_gate2"):
            self._post_warning("Abgelehnt. Task wird verworfen ...")
            self._state = "idle"
            threading.Thread(target=self._approve_task, args=(self._current_task_id, False), daemon=True).start()
        self._set_busy(False)

    def _run_planner(self, user_request: str) -> None:
        try:
            plan = self.planner.create_plan(user_request)
            self._current_plan = plan
            formatted = self.planner.format_plan_for_chat(plan)
            self.root.after(0, self._spinner_stop)
            self.root.after(0, self._post_plan, formatted)
            self.root.after(0, self._set_state, "awaiting_gate0")
            self.root.after(0, self._show_gates, "✓  Ja, umsetzen", "✗  Nein, abbrechen")
        except Exception as exc:
            self.root.after(0, self._post_error, f"Planner-Fehler: {exc}")
        finally:
            self.root.after(0, self._set_busy, False)

    def _run_worker(self) -> None:
        if not self._current_plan:
            self.root.after(0, self._post_error, "Kein Plan vorhanden.")
            return
        plan = self._current_plan
        try:
            payload = {
                "title": plan.get("zusammenfassung", "Task")[:200],
                "description": (plan.get("zusammenfassung", "") + "\n\nSchritte:\n" + "\n".join(plan.get("schritte", []))),
                "worker_type": plan.get("worker", "backend_worker"),
                "priority": "normal",
                "context": {},
                "files": plan.get("dateien", []),
            }
            with httpx.Client(base_url=ORCHESTRATOR_URL, timeout=30.0) as client:
                r = client.post("/api/v1/tasks", json=payload)
                r.raise_for_status()
                data = r.json()
            self._current_task_id = data["task_id"]
            self.root.after(0, self._post_system, f"Task erstellt: {data['task_id'][:12]}... | Status: {data['status']}")
            self.root.after(0, self._set_state, "awaiting_gate1")
            self.root.after(0, self._show_gates, "✓  Gate 1: Worker starten", "✗  Gate 1: Abbrechen")
        except Exception as exc:
            self.root.after(0, self._post_error, f"Worker-Start fehlgeschlagen: {exc}")
            self.root.after(0, self._reset_task)

    def _approve_task(self, task_id: str, approved: bool) -> None:
        try:
            with httpx.Client(base_url=ORCHESTRATOR_URL, timeout=180.0) as client:
                r = client.post(f"/api/v1/tasks/{task_id}/approve", json={"approved": approved, "reviewer": REVIEWER_NAME, "comment": "Gate-1 via Chat-UI"})
                r.raise_for_status()
                data = r.json()
            status = data.get("status", "")
            msg = data.get("message", "")
            self.root.after(0, self._post_system, f"Status: {status} — {msg}")
            if status in ("running", "pending"):
                threading.Thread(target=self._poll_task_status, args=(task_id,), daemon=True).start()
            elif status == "pending_diff":
                threading.Thread(target=self._fetch_and_show_diff, args=(task_id,), daemon=True).start()
            elif status in ("completed", "failed", "rejected"):
                tag = "success" if status == "completed" else "error"
                self.root.after(0, self._post, f"Task {status}.", tag)
                self.root.after(0, self._reset_task)
        except Exception as exc:
            self.root.after(0, self._post_error, f"Gate-1-Fehler: {exc}")

    def _poll_task_status(self, task_id: str) -> None:
        import time
        last_status = ""
        while True:
            time.sleep(3)
            try:
                with httpx.Client(base_url=ORCHESTRATOR_URL, timeout=10.0) as client:
                    r = client.get(f"/api/v1/tasks/{task_id}")
                    r.raise_for_status()
                    data = r.json()
                status = data.get("status", "")
                if status != last_status:
                    last_status = status
                    self.root.after(0, self._post_system, f"Worker: {status}")
                if status == "pending_diff":
                    threading.Thread(target=self._fetch_and_show_diff, args=(task_id,), daemon=True).start()
                    return
                if status in ("completed", "failed", "rejected"):
                    tag = "success" if status == "completed" else "error"
                    self.root.after(0, self._post, f"Task {status}.", tag)
                    self.root.after(0, self._reset_task)
                    return
            except Exception as exc:
                self.root.after(0, self._post_error, f"Polling-Fehler: {exc}")
                return

    def _fetch_and_show_diff(self, task_id: str) -> None:
        try:
            with httpx.Client(base_url=ORCHESTRATOR_URL, timeout=30.0) as client:
                r = client.get(f"/api/v1/tasks/{task_id}/diff")
                r.raise_for_status()
                data = r.json()
            diff = data.get("diff", "")
            diff_lines = data.get("diff_lines", 0)
            branch = data.get("branch", "n/a")
            self.root.after(0, self._post_system, f"Branch: {branch} | Diff: {diff_lines} Zeilen")
            if diff:
                preview = "\n".join(diff.splitlines()[:40])
                if diff_lines > 40:
                    preview += f"\n... ({diff_lines - 40} weitere Zeilen)"
                self.root.after(0, self._post, preview, "diff")
            self.root.after(0, self._set_state, "awaiting_gate2")
            self.root.after(0, self._show_gates, "✓  Gate 2: Diff committen", "✗  Gate 2: Verwerfen")
        except Exception as exc:
            self.root.after(0, self._post_error, f"Diff-Abruf fehlgeschlagen: {exc}")

    def _approve_diff(self, task_id: str, approved: bool) -> None:
        try:
            with httpx.Client(base_url=ORCHESTRATOR_URL, timeout=30.0) as client:
                r = client.post(f"/api/v1/tasks/{task_id}/approve-diff", json={"approved": approved, "reviewer": REVIEWER_NAME, "comment": "Gate-2 via Chat-UI"})
                r.raise_for_status()
                data = r.json()
            status = data.get("status", "")
            msg = data.get("message", "")
            tag = "success" if status == "completed" else "warning"
            self.root.after(0, self._post, f"{status}: {msg}", tag)
        except Exception as exc:
            self.root.after(0, self._post_error, f"Gate-2-Fehler: {exc}")
        finally:
            self.root.after(0, self._reset_task)

    def _spinner_start(self, label: str = "Arbeitet") -> None:
        self._spinner_stop()
        self._spinner_idx = 0
        self._spinner_label = label
        self._spinner_tick()

    def _spinner_tick(self) -> None:
        frame = self._SPINNER[self._spinner_idx % len(self._SPINNER)]
        self._status_label.configure(
            text=f"{frame} {self._spinner_label} ...", fg=FG_WARNING
        )
        self._spinner_idx += 1
        self._spinner_job = self.root.after(100, self._spinner_tick)

    def _spinner_stop(self) -> None:
        if self._spinner_job is not None:
            self.root.after_cancel(self._spinner_job)
            self._spinner_job = None

    def _reset_task(self) -> None:
        self._current_task_id = None
        self._current_plan = None
        self._state = "idle"
        self._spinner_stop()
        self._set_busy(False)

    def _check_server(self) -> None:
        threading.Thread(target=self._do_check_server, daemon=True).start()

    def _do_check_server(self) -> None:
        try:
            with httpx.Client(base_url=ORCHESTRATOR_URL, timeout=5.0) as client:
                r = client.get("/health")
                r.raise_for_status()
                data = r.json()
            version = data.get("version", "?")
            self.root.after(0, self._set_server_status, f"● Verbunden  v{version}", FG_SUCCESS)
            self.root.after(0, self._post_system, f"Orchestrator v{version} bereit.")
        except Exception:
            self.root.after(0, self._set_server_status, "● Nicht erreichbar", FG_ERROR)
            self.root.after(0, self._post_error, "Orchestrator nicht erreichbar. Läuft main.py?")

    def _set_busy(self, busy: bool) -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        self._send_btn.configure(state=state)
        if not busy:
            self._input.configure(state=tk.NORMAL)
            self._input.focus()

    def _set_state(self, state: str) -> None:
        self._state = state

    def _set_server_status(self, text: str, color: str) -> None:
        self._status_label.configure(text=text, fg=color)


def _set_icon(root: tk.Tk) -> None:
    # 16x16 Icon aus XBM — kein externes File nötig
    icon_data = """
#define icon_width 16
#define icon_height 16
static unsigned char icon_bits[] = {
   0x00, 0x00, 0xfe, 0x7f, 0x02, 0x40, 0xfa, 0x5f, 0x0a, 0x50, 0xea, 0x57,
   0x2a, 0x54, 0xaa, 0x55, 0x2a, 0x54, 0xea, 0x57, 0x0a, 0x50, 0xfa, 0x5f,
   0x02, 0x40, 0xfe, 0x7f, 0x00, 0x00, 0x00, 0x00 };
"""
    try:
        icon = tk.BitmapImage(data=icon_data, foreground="#569cd6", background="#1e1e1e")
        root.iconbitmap(bitmap=icon)
        root._icon = icon  # GC-Schutz
    except Exception:
        pass  # Icon ist optional — kein harter Fehler


def main() -> None:
    root = tk.Tk()
    _set_icon(root)
    app = EchoChatUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
