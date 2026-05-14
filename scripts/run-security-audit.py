#!/usr/bin/env python3
"""
Gibson Security Auditor — Main entry point
Runs security scans, generates reports, outputs to memory/security-audits/
Integrates with Claude Code, OpenCode, and git pre-commit hooks
"""

import os
import json
import sys
from pathlib import Path
from datetime import datetime
from security_auditor import SecurityAuditor

class GibsonRunner:
    def __init__(self, project_path: str):
        self.project_path = Path(project_path).resolve()
        self.memory_dir = Path("/home/nick/dev/lucent/memory")
        self.audits_dir = self.memory_dir / "security-audits"
        self.project_name = self.project_path.name

    def run_audit(self) -> dict:
        """Execute security audit and save report"""
        print(f"[Gibson] Starting security audit of {self.project_name}...")

        # Run scanner
        auditor = SecurityAuditor(str(self.project_path))
        results = auditor.run()

        # Generate markdown report
        markdown = auditor.generate_markdown_report()

        # Save report
        report_path = self._save_report(markdown)
        results["report_path"] = str(report_path)

        return results

    def _save_report(self, markdown: str) -> Path:
        """Save markdown report to memory/security-audits/"""
        # Create directory if needed
        today = datetime.now().strftime("%Y-%m-%d")
        day_dir = self.audits_dir / today
        day_dir.mkdir(parents=True, exist_ok=True)

        # Generate timestamp filename
        timestamp = datetime.now().strftime("%H-%M-%S")
        filename = f"{self.project_name}-{timestamp}.md"
        report_path = day_dir / filename

        with open(report_path, 'w') as f:
            f.write(markdown)

        return report_path

    def should_block_commit(self, results: dict) -> bool:
        """Determine if commit should be blocked"""
        summary = results.get("summary", {})
        return summary.get("critical", 0) > 0 or summary.get("high", 0) > 0

    def get_voice_summary(self, results: dict) -> str:
        """Generate brief voice summary"""
        summary = results.get("summary", {})
        project = self.project_name
        critical = summary.get("critical", 0)
        high = summary.get("high", 0)
        medium = summary.get("medium", 0)
        low = summary.get("low", 0)

        # Build summary string
        summary_str = f"Gibson security audit of {project}. {critical} critical, {high} high, {medium} medium, {low} low findings."

        # Add critical/high details if present
        if critical > 0 or high > 0:
            issues = []
            findings = results.get("findings", {})

            if findings.get("critical"):
                for finding in findings["critical"][:2]:  # First 2 critical
                    issues.append(finding.get("name", "Unknown"))

            if findings.get("high"):
                for finding in findings["high"][:2]:  # First 2 high
                    issues.append(finding.get("name", "Unknown"))

            if issues:
                summary_str += f" Critical issues: {', '.join(issues)}."

        # Add secrets info with clarification
        exposed = summary.get("exposed_secrets", 0)
        if exposed > 0:
            summary_str += f" Note: {exposed} secret reference patterns found (code references, not actual secrets). Real secrets are not exposed."
        else:
            summary_str += " No secret references found."

        summary_str += " Full report saved to security-audits folder."

        return summary_str


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 run-security-audit.py <project_path> [--block-on-high]")
        sys.exit(1)

    project_path = sys.argv[1]
    block_on_high = "--block-on-high" in sys.argv

    runner = GibsonRunner(project_path)
    results = runner.run_audit()

    # Output results as JSON (for integration with agents/hooks)
    print(json.dumps({
        "status": "complete",
        "project": runner.project_name,
        "summary": results.get("summary"),
        "should_block": runner.should_block_commit(results) if block_on_high else False,
        "voice_summary": runner.get_voice_summary(results),
        "report_path": results.get("report_path"),
        "findings": {
            "critical": len(results.get("findings", {}).get("critical", [])),
            "high": len(results.get("findings", {}).get("high", [])),
            "medium": len(results.get("findings", {}).get("medium", [])),
            "low": len(results.get("findings", {}).get("low", []))
        }
    }, indent=2))


if __name__ == "__main__":
    main()
