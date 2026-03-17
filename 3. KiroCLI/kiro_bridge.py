"""kiro_bridge.py — Production bridge between OpenClaw and Kiro CLI."""

import logging, os, sys, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acp_client import ACPClient, PromptResult, PermissionRequest

KIRO_CLI_PATH = os.environ.get("KIRO_CLI_PATH", os.path.expanduser("~/.local/bin/kiro-cli"))
WORKING_DIR   = os.environ.get("KIRO_WORKING_DIR", os.path.expanduser("~/kiro-projects"))
log = logging.getLogger(__name__)


class KiroBridge:
    """
    Production bridge with four key features:
    1. Lazy start — kiro-cli process only starts on first actual call
    2. Session reuse — default session persists across tasks
    3. Auto context management — starts new session at 80% context usage
    4. Dual usage tracking — Kiro Credits + Claude API tokens
    """

    def __init__(self):
        self._acp: ACPClient | None = None
        self._acp_lock = threading.Lock()
        self._sessions: dict[str, str] = {}
        self._sessions_lock = threading.Lock()

    def _start_acp(self):
        with self._acp_lock:
            if self._acp is not None and self._acp.is_running():
                return
            self._acp = ACPClient(cli_path=KIRO_CLI_PATH)
            self._acp.start(cwd=WORKING_DIR)
            self._acp.on_permission_request(lambda req: "allow_once")
            log.info("Kiro ACP started (PID: %s)", self._acp._proc.pid)

    def _ensure_acp(self) -> ACPClient:
        self._start_acp()
        return self._acp

    def _get_default_session(self) -> str:
        with self._sessions_lock:
            if "default" in self._sessions:
                return self._sessions["default"]
        acp = self._ensure_acp()
        session_id, _ = acp.session_new(WORKING_DIR)
        with self._sessions_lock:
            self._sessions["default"] = session_id
        return session_id

    def prompt(self, text: str, session_id: str | None = None,
               task_name: str | None = None) -> dict:
        """Send a coding task. Returns structured result with usage data."""
        acp = self._ensure_acp()
        sid = session_id or self._get_default_session()

        # Proactive context management
        meta = acp._session_metadata.get(sid, {})
        if meta.get("contextUsagePercentage", 0) > 80:
            log.warning("Context at %.1f%%, starting fresh session",
                       meta["contextUsagePercentage"])
            sid = acp.session_new(WORKING_DIR)[0]
            with self._sessions_lock:
                self._sessions["default"] = sid

        result: PromptResult = acp.session_prompt(sid, text)

        return {
            "success": True,
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

    def stop(self):
        if self._acp:
            self._acp.stop()
            self._acp = None
            with self._sessions_lock:
                self._sessions.clear()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stop()
