"""Quick ACP integration test."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acp_client import ACPClient

KIRO_CLI = os.environ.get("KIRO_CLI_PATH", os.path.expanduser("~/.local/bin/kiro-cli"))
WORK_DIR = os.environ.get("KIRO_WORKING_DIR", os.path.expanduser("~/kiro-projects"))

print("=== ACP Integration Test ===")
print(f"Kiro CLI: {KIRO_CLI}")
print(f"Working Dir: {WORK_DIR}")

acp = ACPClient(cli_path=KIRO_CLI)

try:
    # Step 1: Initialize
    print("\n[1/3] Initializing ACP connection...")
    init_result = acp.start(cwd=WORK_DIR)
    print(f"  ✔ Agent: {init_result.get('agentInfo', {}).get('name', 'unknown')}")
    print(f"  ✔ Version: {init_result.get('agentInfo', {}).get('version', 'unknown')}")

    # Step 2: Create session
    print("\n[2/3] Creating new session...")
    session_id, modes = acp.session_new(WORK_DIR)
    print(f"  ✔ Session ID: {session_id[:20]}...")

    # Step 3: Send a simple prompt
    print("\n[3/3] Sending test prompt...")
    result = acp.session_prompt(session_id, "Say hello in one sentence.", timeout=60)
    print(f"  ✔ Response: {result.text[:100]}...")
    print(f"  ✔ Tool calls: {len(result.tool_calls)}")
    print(f"  ✔ Context usage: {result.kiro_context_pct:.1f}%")

    print("\n=== All tests passed ===")

except Exception as e:
    print(f"\n✘ Test failed: {e}")
    sys.exit(1)

finally:
    acp.stop()
    print("ACP connection closed.")
