"""kiro_bridge.py — Production bridge between OpenClaw and Kiro CLI.

Supports concurrent projects: each project name gets its own kiro-cli
process with isolated context. Same project name reuses the existing
process and session (shared context).
"""

import logging, os, sys, threading
from concurrent.futures import ThreadPoolExecutor, Future

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acp_client import ACPClient, PromptResult, PermissionRequest

KIRO_CLI_PATH = os.environ.get("KIRO_CLI_PATH", os.path.expanduser("~/.local/bin/kiro-cli"))
WORKING_DIR   = os.environ.get("KIRO_WORKING_DIR", os.path.expanduser("~/kiro-projects"))
log = logging.getLogger(__name__)

_DEFAULT_PROJECT = "__default__"


class _ProjectHandle:
    """One kiro-cli process + session for a single project."""

    def __init__(self, project_name: str, cwd: str):
        self.project_name = project_name
        self.cwd = cwd
        self.acp: ACPClient | None = None
        self.session_id: str | None = None
        self._lock = threading.Lock()

    def ensure_running(self) -> ACPClient:
        with self._lock:
            if self.acp is not None and self.acp.is_running():
                return self.acp
            self.acp = ACPClient(cli_path=KIRO_CLI_PATH)
            self.acp.start(cwd=self.cwd)
            self.acp.on_permission_request(lambda req: "allow_once")
            log.info("[%s] Kiro ACP started (PID: %s)",
                     self.project_name, self.acp._proc.pid)
            return self.acp

    def ensure_session(self) -> str:
        with self._lock:
            if self.session_id:
                return self.session_id
        acp = self.ensure_running()
        sid, _ = acp.session_new(self.cwd)
        with self._lock:
            self.session_id = sid
        log.info("[%s] Session created: %s", self.project_name, sid[:20])
        return sid

    def reset_session(self) -> str:
        """Start a fresh session (e.g. when context is nearly full)."""
        acp = self.ensure_running()
        sid, _ = acp.session_new(self.cwd)
        with self._lock:
            self.session_id = sid
        log.info("[%s] Session reset: %s", self.project_name, sid[:20])
        return sid

    def prompt(self, text: str, timeout: float = 300) -> PromptResult:
        acp = self.ensure_running()
        sid = self.ensure_session()

        # Auto context management — rotate session at 80%
        meta = acp._session_metadata.get(sid, {})
        if meta.get("contextUsagePercentage", 0) > 80:
            log.warning("[%s] Context at %.1f%%, rotating session",
                        self.project_name, meta["contextUsagePercentage"])
            sid = self.reset_session()

        return acp.session_prompt(sid, text, timeout=timeout)

    def stop(self):
        with self._lock:
            if self.acp:
                self.acp.stop()
                self.acp = None
                self.session_id = None
                log.info("[%s] Stopped", self.project_name)


class KiroBridge:
    """
    Multi-project bridge with concurrent kiro-cli process support.

    - Same project name → reuses process & session (shared context)
    - Different project name → new kiro-cli process (isolated context)
    - prompt() without project → uses default single-project mode
    """

    def __init__(self):
        self._projects: dict[str, _ProjectHandle] = {}
        self._projects_lock = threading.Lock()

    # ── Project Management ────────────────────────────────

    def _get_handle(self, project: str | None = None,
                    cwd: str | None = None) -> _ProjectHandle:
        name = project or _DEFAULT_PROJECT
        work_dir = cwd or WORKING_DIR
        with self._projects_lock:
            if name in self._projects:
                return self._projects[name]
            handle = _ProjectHandle(name, work_dir)
            self._projects[name] = handle
            log.info("New project registered: %s (cwd=%s)", name, work_dir)
            return handle

    def list_projects(self) -> list[dict]:
        """List all active projects and their status."""
        with self._projects_lock:
            result = []
            for name, h in self._projects.items():
                display = name if name != _DEFAULT_PROJECT else "(default)"
                result.append({
                    "project": display,
                    "running": h.acp is not None and h.acp.is_running(),
                    "session_id": h.session_id,
                })
            return result

    def is_same_project(self, project_name: str) -> bool:
        """Check if a project with this name already exists."""
        with self._projects_lock:
            return project_name in self._projects

    # ── Core API ──────────────────────────────────────────

    def prompt(self, text: str, project: str | None = None,
               cwd: str | None = None, timeout: float = 300) -> dict:
        """
        Send a prompt to Kiro.

        Args:
            text: The prompt / task description.
            project: Project name. Same name reuses context; new name
                     starts a fresh kiro-cli process.
            cwd: Working directory override for this project.
            timeout: Max seconds to wait for response.
        """
        handle = self._get_handle(project, cwd)
        result = handle.prompt(text, timeout=timeout)

        return {
            "success": True,
            "project": project or "(default)",
            "text": result.text,
            "tool_calls": [
                {"kind": tc.kind, "title": tc.title, "status": tc.status}
                for tc in result.tool_calls
            ],
            "usage": {
                "kiro_credits": result.kiro_credits,
                "kiro_context_pct": result.kiro_context_pct,
                "kiro_tool_calls": len(result.tool_calls),
            },
        }

    def prompt_parallel(self, tasks: list[dict],
                        max_workers: int = 3) -> dict[str, dict]:
        """
        Run multiple project prompts concurrently.

        Args:
            tasks: List of dicts, each with keys:
                   - project (str): project name
                   - text (str): prompt text
                   - cwd (str, optional): working directory
            max_workers: Max concurrent kiro-cli processes.

        Returns:
            Dict mapping project name → prompt result.
        """
        results: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures: dict[Future, str] = {}
            for task in tasks:
                name = task["project"]
                f = pool.submit(
                    self.prompt,
                    text=task["text"],
                    project=name,
                    cwd=task.get("cwd"),
                )
                futures[f] = name

            for future in futures:
                name = futures[future]
                try:
                    results[name] = future.result()
                except Exception as e:
                    log.error("[%s] Parallel prompt failed: %s", name, e)
                    results[name] = {"success": False, "error": str(e)}
        return results

    # ── Lifecycle ─────────────────────────────────────────

    def stop_project(self, project: str):
        """Stop a single project's kiro-cli process."""
        with self._projects_lock:
            handle = self._projects.pop(project, None)
        if handle:
            handle.stop()

    def stop(self):
        """Stop all kiro-cli processes."""
        with self._projects_lock:
            handles = list(self._projects.values())
            self._projects.clear()
        for h in handles:
            h.stop()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stop()
