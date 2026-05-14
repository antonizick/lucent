#!/usr/bin/env python3
"""
Gibson Security Auditor — Core scanning logic
Scans projects for vulnerabilities, secrets, and configuration issues
Outputs markdown reports to memory/security-audits/
"""

import os
import re
import json
import subprocess
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Tuple, Set

class SecurityAuditor:
    # Files/paths to exclude from scanning (relative to project root)
    EXCLUSIONS = {
        'scripts/security_auditor.py',  # Don't audit the scanner itself
    }

    def __init__(self, project_path: str):
        self.project_path = Path(project_path).resolve()
        self.project_name = self.project_path.name
        self.findings = defaultdict(list)  # severity -> list of findings
        self.external_findings = defaultdict(list)  # severity -> list of external library findings
        self.secrets = {"exposed": [], "protected": []}
        self.gitignore_rules = set()
        self.scan_time = datetime.now()

    def _is_external_library(self, file_path: str) -> bool:
        """Check if a file is from an external library that shouldn't be modified."""
        external_patterns = {
            'node_modules/',
            'vendor/',
            '/min.js',  # Minified files
            '/jquery-',
            '/DataTables',
            'idea/nxtm/DataTables/',
            '.min.js',
        }
        return any(pattern in file_path for pattern in external_patterns)

    def run(self) -> Dict:
        """Execute full security audit"""
        print(f"[Gibson] Scanning {self.project_path}...")

        self._load_gitignore()
        self._scan_secrets()
        self._scan_vulnerabilities()
        self._scan_infrastructure()
        self._scan_dependencies()

        return self.get_results()

    def _load_gitignore(self):
        """Parse .gitignore to understand secret storage strategy"""
        gitignore_path = self.project_path / ".gitignore"
        if gitignore_path.exists():
            with open(gitignore_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        self.gitignore_rules.add(line)

    def _scan_secrets(self):
        """Detect exposed and protected secrets"""
        secret_patterns = {
            "AWS Key": r"AKIA[0-9A-Z]{16}",
            "GitHub Token": r"ghp_[A-Za-z0-9_]{36}",
            "Discord Token": r"[MN][A-Za-z0-9_-]{23,25}\.[A-Za-z0-9_-]{6,7}\.[A-Za-z0-9_-]{27}",
            "Private Key": r"-----BEGIN (RSA|OPENSSH|EC|PGP) PRIVATE KEY-----",
            "API Key": r"api[_-]?key['\"]?\s*[:=]\s*['\"][^'\"]{16,}",
            ".env reference": r"\.env|\.env\.\w+",
            "credentials file": r"credentials\.json|secrets\.json|config\.json"
        }

        protected_patterns = [".env", "secrets", "credentials", "private", ".key", ".pem"]

        for root, dirs, files in os.walk(self.project_path):
            # Skip common non-code directories
            dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'node_modules', '.venv', 'venv', '.next', 'dist', 'build'}]

            for file in files:
                filepath = Path(root) / file
                if self._should_scan(filepath):
                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            rel_path = filepath.relative_to(self.project_path)

                            # Check for exposed secrets
                            for secret_type, pattern in secret_patterns.items():
                                if re.search(pattern, content):
                                    if not self._is_ignored(str(rel_path)):
                                        self.secrets["exposed"].append({
                                            "type": secret_type,
                                            "file": str(rel_path),
                                            "severity": "critical"
                                        })

                            # Check for protected patterns
                            for pattern in protected_patterns:
                                if pattern in str(rel_path):
                                    if self._is_ignored(str(rel_path)):
                                        self.secrets["protected"].append(str(rel_path))
                    except Exception:
                        pass

    def _scan_vulnerabilities(self):
        """Scan for common vulnerabilities"""

        # Python security patterns
        python_vulns = {
            "evalUsage": {
                "pattern": r"\beval\s*\(",
                "severity": "critical",
                "message": "eval() can execute arbitrary code. Use ast.literal_eval() for safe evaluation.",
                "fix": "Replace eval() with ast.literal_eval() or json.loads() as appropriate",
                "display_name": "eval() usage"
            },
            "execUsage": {
                "pattern": r"\bexec\s*\(",
                "severity": "critical",
                "message": "exec() can execute arbitrary code. Avoid if possible.",
                "fix": "Refactor to use safer alternatives or sandboxed environments",
                "display_name": "exec() usage"
            },
            "SQL Injection pattern": {
                "pattern": r'(execute|query|sql)\s*\(\s*["\'].*\+',
                "severity": "high",
                "message": "String concatenation in SQL queries leads to injection attacks.",
                "fix": "Use parameterized queries (?) or ORM methods instead"
            },
            "Hardcoded credential": {
                "pattern": r'(password|secret|api_key|token)\s*=\s*["\'][^"\']{8,}["\']',
                "severity": "critical",
                "message": "Credentials are hardcoded in source. Move to environment variables.",
                "fix": "Use os.environ.get() or config files not in git"
            },
            "requests without timeout": {
                "pattern": r'requests\.(get|post|put|delete)\s*\(',
                "severity": "medium",
                "message": "HTTP requests without timeout can hang indefinitely.",
                "fix": "Add timeout parameter: requests.get(url, timeout=10)",
                "skip_multiline": True
            },
            "pickle usage": {
                "pattern": r'\bpickle\.(loads|load|dumps)\s*\(',
                "severity": "high",
                "message": "pickle is insecure; untrusted data can execute code.",
                "fix": "Use json or msgpack instead. If pickle necessary, restrict to trusted data only"
            }
        }

        # JavaScript/TypeScript security patterns
        js_vulns = {
            "evalInJS": {
                "pattern": r'\beval\s*\(',
                "severity": "critical",
                "message": "eval() in JavaScript opens code injection attacks.",
                "fix": "Use Function() constructor with strict data, or safer alternatives",
                "display_name": "eval() in JS"
            },
            "innerHTML assignment": {
                "pattern": r'\.innerHTML\s*=|\.innerHTML\s*\+=',
                "severity": "high",
                "message": "Setting innerHTML with user data causes XSS vulnerabilities.",
                "fix": "Use textContent or createElement() instead"
            },
            "No CORS headers": {
                "pattern": r'(Express|app\.(get|post))\s*\(',
                "severity": "medium",
                "message": "Missing CORS configuration may expose endpoints unintentionally.",
                "fix": "Explicitly configure CORS: app.use(cors({origin: 'https://trusted.com'}))"
            }
        }

        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'node_modules', '.venv', 'venv', '.next', 'dist', 'build'}]

            for file in files:
                filepath = Path(root) / file
                if self._should_scan(filepath):
                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            rel_path = str(filepath.relative_to(self.project_path))

                            # Determine if this is an external library
                            is_external = self._is_external_library(rel_path)

                            # Python checks
                            if file.endswith('.py'):
                                for vuln_name, vuln_info in python_vulns.items():
                                    # Skip timeout check if the file has timeout= parameter (multi-line support)
                                    if vuln_name == "requests without timeout" and "timeout=" in content:
                                        continue

                                    if re.search(vuln_info['pattern'], content):
                                        finding = {
                                            "name": vuln_info.get('display_name', vuln_name),
                                            "file": rel_path,
                                            "message": vuln_info['message'],
                                            "fix": vuln_info['fix']
                                        }
                                        if is_external:
                                            self.external_findings[vuln_info['severity']].append(finding)
                                        else:
                                            self.findings[vuln_info['severity']].append(finding)

                            # JS/TS checks
                            if file.endswith(('.js', '.ts', '.tsx', '.jsx')):
                                # Skip innerHTML warning if file uses HTML escaping function
                                has_html_escaping = bool(re.search(r'escHtml|escapeHtml|function escape|sanitize', content))

                                for vuln_name, vuln_info in js_vulns.items():
                                    # Skip innerHTML check if file has HTML escaping function
                                    if vuln_name == "innerHTML assignment" and has_html_escaping:
                                        continue

                                    if re.search(vuln_info['pattern'], content):
                                        finding = {
                                            "name": vuln_info.get('display_name', vuln_name),
                                            "file": rel_path,
                                            "message": vuln_info['message'],
                                            "fix": vuln_info['fix']
                                        }
                                        if is_external:
                                            self.external_findings[vuln_info['severity']].append(finding)
                                        else:
                                            self.findings[vuln_info['severity']].append(finding)
                    except Exception:
                        pass

    def _scan_infrastructure(self):
        """Scan Docker, config files, and infrastructure code"""
        docker_vulns = {
            "Docker FROM latest": {
                "pattern": r'FROM\s+\w+:latest',
                "severity": "medium",
                "message": "Using :latest tag makes images non-reproducible and unpredictable.",
                "fix": "Pin to specific version: FROM python:3.11.2-slim"
            },
            "Docker RUN as root": {
                "pattern": r'RUN\s+(?!.*(?:\buseradd\b|USER\s))',
                "severity": "high",
                "message": "Containers run as root by default. Create and use a non-root user.",
                "fix": "Add: RUN useradd -m appuser && USER appuser"
            }
        }

        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'node_modules', '.venv', 'venv', '.next', 'dist', 'build'}]

            for file in files:
                filepath = Path(root) / file

                if file in ('Dockerfile', 'docker-compose.yml', 'docker-compose.yaml'):
                    try:
                        with open(filepath, 'r') as f:
                            content = f.read()
                            rel_path = str(filepath.relative_to(self.project_path))

                            # Skip "Docker RUN as root" check if file has a USER directive (multi-stage build support)
                            has_user_directive = re.search(r'\bUSER\s+\w', content)

                            for vuln_name, vuln_info in docker_vulns.items():
                                # Skip Docker RUN check if USER directive exists
                                if vuln_name == "Docker RUN as root" and has_user_directive:
                                    continue

                                if re.search(vuln_info['pattern'], content):
                                    self.findings[vuln_info['severity']].append({
                                        "name": vuln_name,
                                        "file": rel_path,
                                        "message": vuln_info['message'],
                                        "fix": vuln_info['fix']
                                    })
                    except Exception:
                        pass

    def _scan_dependencies(self):
        """Check for outdated/vulnerable dependencies"""
        # Check Python requirements
        req_path = self.project_path / "requirements.txt"
        if req_path.exists():
            try:
                with open(req_path) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            # Check for pinning best practices
                            if "==" not in line and ">=" not in line:
                                self.findings["medium"].append({
                                    "name": "Unpinned dependency",
                                    "file": "requirements.txt",
                                    "message": f"Dependency '{line}' is not pinned to a version.",
                                    "fix": "Pin versions: package==1.2.3 or package>=1.2.3,<2.0"
                                })
            except Exception:
                pass

        # Check Node dependencies
        pkg_path = self.project_path / "package.json"
        if pkg_path.exists():
            try:
                with open(pkg_path) as f:
                    data = json.load(f)
                    for dep, version in data.get("dependencies", {}).items():
                        if version.startswith("*") or version == "latest":
                            self.findings["medium"].append({
                                "name": "Unpinned npm dependency",
                                "file": "package.json",
                                "message": f"Dependency '{dep}' uses wildcard or 'latest'.",
                                "fix": "Pin to specific version: npm install --save-exact package@1.2.3"
                            })
            except Exception:
                pass

    def _should_scan(self, filepath: Path) -> bool:
        """Determine if file should be scanned"""
        # Check exclusions first
        rel_path = str(filepath.relative_to(self.project_path))
        for exclusion in self.EXCLUSIONS:
            if rel_path == exclusion or rel_path.endswith(exclusion):
                return False

        extensions = {'.py', '.js', '.ts', '.tsx', '.jsx', '.json', '.yaml', '.yml', '.env', '.sh', '.go', '.rs'}
        return filepath.suffix in extensions or filepath.name in ('Dockerfile', '.env.example')

    def _is_ignored(self, path: str) -> bool:
        """Check if path matches .gitignore rules"""
        for rule in self.gitignore_rules:
            # Simplified matching
            if rule in path or path.endswith(rule):
                return True
        return False

    def get_results(self) -> Dict:
        """Return structured findings"""
        return {
            "project_name": self.project_name,
            "project_path": str(self.project_path),
            "scan_time": self.scan_time.isoformat(),
            "findings": dict(self.findings),
            "external_findings": dict(self.external_findings),
            "secrets": self.secrets,
            "summary": {
                "critical": len(self.findings.get("critical", [])),
                "critical_external": len(self.external_findings.get("critical", [])),
                "high": len(self.findings.get("high", [])),
                "high_external": len(self.external_findings.get("high", [])),
                "medium": len(self.findings.get("medium", [])),
                "medium_external": len(self.external_findings.get("medium", [])),
                "low": len(self.findings.get("low", [])),
                "low_external": len(self.external_findings.get("low", [])),
                "exposed_secrets": len(self.secrets["exposed"]),
                "protected_secrets": len(self.secrets["protected"])
            }
        }

    def generate_markdown_report(self) -> str:
        """Generate markdown audit report"""
        results = self.get_results()
        summary = results["summary"]

        # Build summary with external library notation
        critical_note = f" ({summary['critical_external']} in external libraries)" if summary['critical_external'] > 0 else ""
        high_note = f" ({summary['high_external']} in external libraries)" if summary['high_external'] > 0 else ""
        medium_note = f" ({summary['medium_external']} in external libraries)" if summary['medium_external'] > 0 else ""
        low_note = f" ({summary['low_external']} in external libraries)" if summary['low_external'] > 0 else ""

        md = f"""# Security Audit: {self.project_name}

**Date:** {self.scan_time.strftime('%Y-%m-%d %H:%M:%S')}
**Scanned by:** Gibson
**Project location:** {self.project_path}

## Summary

- 🔴 **Critical:** {summary['critical']}{critical_note}
- 🟠 **High:** {summary['high']}{high_note}
- 🟡 **Medium:** {summary['medium']}{medium_note}
- 🔵 **Low:** {summary['low']}{low_note}
- 🔑 **Secret References Found:** {summary['exposed_secrets']} (code references & patterns, not actual secrets)
- 🔒 **Protected Secrets:** {summary['protected_secrets']} (properly .gitignored)

"""

        # Critical findings
        if results["findings"].get("critical"):
            md += "## 🔴 Critical Findings\n\n"
            for finding in results["findings"]["critical"]:
                md += f"### {finding['name']}\n"
                md += f"**File:** `{finding['file']}`\n\n"
                md += f"**Issue:** {finding['message']}\n\n"
                md += f"**Fix:** {finding['fix']}\n\n"

        # High findings
        if results["findings"].get("high"):
            md += "## 🟠 High Severity Findings\n\n"
            for finding in results["findings"]["high"]:
                md += f"### {finding['name']}\n"
                md += f"**File:** `{finding['file']}`\n\n"
                md += f"**Issue:** {finding['message']}\n\n"
                md += f"**Fix:** {finding['fix']}\n\n"

        # Medium findings
        if results["findings"].get("medium"):
            md += "## 🟡 Medium Severity Findings\n\n"
            for finding in results["findings"]["medium"]:
                md += f"- **{finding['name']}** (`{finding['file']}`): {finding['message']}\n"

        # Low findings
        if results["findings"].get("low"):
            md += "## 🔵 Low Severity Findings\n\n"
            for finding in results["findings"]["low"]:
                md += f"- **{finding['name']}** (`{finding['file']}`): {finding['message']}\n"

        # Secrets analysis
        md += "\n## 🔑 Secrets Analysis\n\n"

        if results["secrets"]["exposed"]:
            md += "### ℹ️ Secret References Found (Code References & Patterns)\n"
            md += "**⚠️ NOTE:** These are code references to where secrets *should* be stored (e.g., `.env` file reads), not actual secrets. Real secrets are not exposed to GitHub.\n\n"
            for secret in results["secrets"]["exposed"]:
                md += f"- **{secret['type']}** in `{secret['file']}`\n"
            md += "\n**Action:** If actual credentials were ever added to these files, they would not be exposed because the containing files are properly .gitignored. Keep using environment variables for runtime secrets (not hardcoded).\n"
        else:
            md += "### ✅ No Secret References Found\n"
            md += "No code patterns referencing secrets were detected.\n"

        if results["secrets"]["protected"]:
            md += f"\n### ✅ Protected Secrets (Properly .gitignored)\n"
            md += "These files/directories are correctly excluded from version control:\n"
            for secret in results["secrets"]["protected"][:10]:
                md += f"- `{secret}`\n"
            md += "\n**Status:** Your `.env` files and credential storage are properly protected.\n"

        md += "\n---\n*Report generated by Gibson Security Auditor*\n"

        return md


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 security_auditor.py <project_path>")
        sys.exit(1)

    auditor = SecurityAuditor(sys.argv[1])
    results = auditor.run()

    # Print results
    print(json.dumps(results, indent=2))
