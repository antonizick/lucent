#!/usr/bin/env python3
"""
Git pre-commit hook for Gibson Security Auditor
Triggered before commits, blocks critical/high vulns, warns on medium/low
"""

import subprocess
import json
import sys
import time
from pathlib import Path

def run_security_audit(project_path: str) -> dict:
    """Run Gibson audit and return results"""
    try:
        result = subprocess.run(
            ["python3", "/home/nick/dev/lucent/scripts/run-security-audit.py", project_path, "--block-on-high"],
            capture_output=True,
            text=True,
            timeout=60
        )

        # Extract JSON from output (last line)
        output_lines = result.stdout.strip().split('\n')
        for line in reversed(output_lines):
            if line.startswith('{'):
                return json.loads(line)

        return {"status": "error", "message": "Could not parse audit results"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Audit timeout (>60s)"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def ask_user_override(question: str, timeout_seconds: int = 5) -> bool:
    """Ask user yes/no, with timeout for auto-proceed"""
    print(f"\n{question}")
    print(f"[You have {timeout_seconds} seconds to respond]")
    print("Press 'y' to override, or wait for auto-proceed...")

    # For non-interactive environments, default to False
    try:
        import select
        if sys.stdin in select.select([sys.stdin], [], [], timeout_seconds)[0]:
            response = sys.stdin.readline().strip().lower()
            return response in ('y', 'yes', 'override')
        return False
    except Exception:
        # Non-interactive or error
        return False


def send_voice_alert(message: str):
    """Send alert via voice box"""
    try:
        import subprocess
        subprocess.run([
            "curl", "-X", "POST",
            "http://localhost:8001/speak",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({"text": message})
        ], timeout=5, capture_output=True)
    except Exception:
        pass  # Voice box not available, continue anyway


def main():
    """Main pre-commit hook logic"""
    # Get the project root (where .git is)
    project_path = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"],
        text=True
    ).strip()

    print("[Gibson Pre-Commit Hook] Running security audit...")

    # Run audit
    results = run_security_audit(project_path)

    if results.get("status") == "error":
        print(f"⚠️  Audit error: {results.get('message')}")
        print("Proceeding with commit (audit unavailable)")
        return 0  # Don't block if audit fails

    # Get summary
    summary = results.get("summary", {})
    critical = summary.get("critical", 0)
    high = summary.get("high", 0)
    medium = summary.get("medium", 0)
    low = summary.get("low", 0)

    voice_msg = results.get("voice_summary", "Security audit complete")
    report_path = results.get("report_path", "unknown")

    print(f"\n{voice_msg}\n")
    send_voice_alert(voice_msg)

    # Determine action
    if critical > 0 or high > 0:
        print(f"\n🚨 SECURITY ALERT: Commit blocked ({critical} critical, {high} high vulnerabilities)")
        print(f"Full report: {report_path}\n")

        # Ask for override
        if ask_user_override("Override security block and commit anyway? (y/n):"):
            print("⚠️  Committing despite security findings. Be careful!")
            return 0
        else:
            print("\nCommit blocked. Address security findings before committing.")
            print("To bypass: Add --no-verify flag (not recommended)")
            return 1  # Block commit

    elif medium > 0 or low > 0:
        print(f"\n⚠️  Warning: {medium} medium, {low} low severity findings")
        print(f"Full report: {report_path}")
        print("Auto-proceeding in 60 seconds (or press Ctrl+C to abort)...\n")

        # Auto-proceed with warning (user can Ctrl+C)
        try:
            time.sleep(60)
        except KeyboardInterrupt:
            print("\nCommit cancelled by user")
            return 1

    else:
        print("\n✅ No security issues found. Commit approved.")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"Hook error: {e}")
        sys.exit(0)  # Don't block on hook errors
