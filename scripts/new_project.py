#!/usr/bin/env python3
"""
new_project.py — Deterministic scaffolder for Lucent `idea/` projects.

Two subcommands so the workflow matches Nick's "propose, then I confirm" rule:

    ports                 Show the ledger + live-bound ports, then PROPOSE
                          candidate free ports. Writes nothing.

    create --name N --port P [...]   Scaffold the project with the CONFIRMED
                          port: dir, CLAUDE.md, planning.md, README.md,
                          .gitignore, .lucentrc, and a ledger row.

Port deconfliction is a hard mandate. `create` refuses to run if the chosen
port is reserved, already in the ledger, or currently bound.

Single source of truth for ports: idea/PORTS.md
Drift sources also scanned read-only: idea/project-health.sh, project configs.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/nick/dev/lucent")
IDEA = ROOT / "idea"
LEDGER = IDEA / "PORTS.md"
HEALTH = IDEA / "project-health.sh"
TEMPLATE = ROOT / "memory" / "templates" / "project_CLAUDE.md"

RESERVED = {8000, 8001, 8002, 8003, 8010}
ASSIGN_FLOOR = 8100  # new web services climb from here


# --------------------------------------------------------------------------
# Port discovery
# --------------------------------------------------------------------------
def ports_from_ledger() -> set[int]:
    if not LEDGER.exists():
        return set()
    found = set()
    for line in LEDGER.read_text().splitlines():
        m = re.match(r"\s*\|\s*(\d{2,5})\s*\|", line)
        if m:
            found.add(int(m.group(1)))
    return found


def ports_from_health() -> set[int]:
    """Catch drift: ports registered in project-health.sh but not the ledger."""
    if not HEALTH.exists():
        return set()
    found = set()
    for m in re.finditer(r"\]=(\d{3,5})\b", HEALTH.read_text()):
        found.add(int(m.group(1)))
    return found


def ports_from_configs() -> set[int]:
    """Best-effort grep of project configs for stray --port / PORT= values."""
    found = set()
    patterns = ["*/.lucentrc", "*/CLAUDE.md", "*/README.md", "*/*.env", "*/docker-compose*.yml"]
    for pat in patterns:
        for f in IDEA.glob(pat):
            try:
                text = f.read_text(errors="ignore")
            except OSError:
                continue
            for m in re.finditer(r"(?:--port[ =]+|PORT[ =:]+|localhost:|127\.0\.0\.1:)\s*(\d{4,5})", text):
                found.add(int(m.group(1)))
    return found


def bound_ports() -> set[int]:
    """Ports currently LISTENing on the box."""
    found = set()
    try:
        out = subprocess.run(
            ["ss", "-ltnH"], capture_output=True, text=True, timeout=5
        ).stdout
    except (OSError, subprocess.SubprocessError):
        try:
            out = subprocess.run(
                ["netstat", "-ltn"], capture_output=True, text=True, timeout=5
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return found
    for m in re.finditer(r"[:\]](\d{4,5})\s", out):
        found.add(int(m.group(1)))
    return found


def all_used() -> tuple[set[int], dict[str, set[int]]]:
    led = ports_from_ledger()
    health = ports_from_health()
    cfg = ports_from_configs()
    live = bound_ports()
    combined = RESERVED | led | health | cfg | live
    return combined, {"ledger": led, "health": health, "configs": cfg, "live": live}


def suggest(n: int = 3) -> list[int]:
    used, _ = all_used()
    out, port = [], ASSIGN_FLOOR
    while len(out) < n and port < 65535:
        if port not in used:
            out.append(port)
        port += 1
    return out


# --------------------------------------------------------------------------
# Subcommand: ports
# --------------------------------------------------------------------------
def cmd_ports(_args) -> int:
    used, by_src = all_used()
    print("=== Port Ledger State ===")
    print(f"Reserved (never assign): {sorted(RESERVED)}")
    print(f"In ledger:   {sorted(by_src['ledger'])}")
    print(f"In health:   {sorted(by_src['health'])}")
    print(f"In configs:  {sorted(by_src['configs'])}")
    print(f"Live-bound:  {sorted(by_src['live'])}")
    drift = (by_src["health"] | by_src["configs"]) - by_src["ledger"] - RESERVED
    if drift:
        print(f"\n[!] DRIFT — used but missing from ledger: {sorted(drift)}")
        print("    Consider adding these rows to idea/PORTS.md.")
    cands = suggest(3)
    print(f"\n>>> PROPOSED free ports (confirm one): {cands}")
    print(">>> Then: new_project.py create --name <Name> --port <chosen> ...")
    return 0


# --------------------------------------------------------------------------
# Subcommand: create
# --------------------------------------------------------------------------
def fail(msg: str) -> int:
    print(f"[ABORT] {msg}", file=sys.stderr)
    return 1


def cmd_create(a) -> int:
    name = a.name.strip()
    port = a.port
    proj = IDEA / name

    # --- Port deconfliction mandate -------------------------------------
    used, by_src = all_used()
    if port in RESERVED:
        return fail(f"Port {port} is RESERVED. Pick another.")
    if port in used:
        srcs = [s for s, ps in by_src.items() if port in ps]
        return fail(f"Port {port} already in use ({', '.join(srcs)}). Run `ports` for free candidates.")
    if proj.exists():
        return fail(f"{proj} already exists. Choose a different name or remove it first.")

    planning_rel = f"memory/{name.lower().replace(' ', '_')}_planning.md"

    # --- Directory + CLAUDE.md ------------------------------------------
    proj.mkdir(parents=True)
    tmpl = TEMPLATE.read_text()
    tmpl = re.sub(r"> \*\*Template\.\*\*.*?notice block\.\n\n---\n\n", "", tmpl, flags=re.S)
    tmpl = (tmpl.replace("{{PROJECT_NAME}}", name)
                .replace("{{PLANNING_DOC}}", planning_rel)
                .replace("{{PORT}}", str(port)))
    (proj / "CLAUDE.md").write_text(tmpl)

    # --- .lucentrc ------------------------------------------------------
    (proj / ".lucentrc").write_text(
        f"LUCENT_PROJECT={name.lower().replace(' ', '')}\n"
        f"LUCENT_PROJECT_PATH={proj}\n"
        f"LUCENT_PROJECT_PORT={port}\n"
        + (f"LUCENT_PROJECT_FOCUS={a.focus}\n" if a.focus else "")
    )

    # --- planning.md ----------------------------------------------------
    features = a.features.split("||") if a.features else []
    phases = "\n".join(
        f"### Phase {i}: {feat.strip()}\n- [ ] {feat.strip()}\n"
        for i, feat in enumerate(features, 1)
    ) or "### Phase 1: Define scope\n- [ ] Outline first deliverable\n"
    (proj / "planning.md").write_text(
        f"# {name} — Planning\n\n"
        f"**Purpose:** {a.purpose or 'TBD'}\n\n"
        f"**Type:** {a.type}  \n**Port:** {port}  \n"
        f"**Tech:** {a.tech or 'TBD'}\n\n"
        f"**Scope in:** {a.scope_in or 'this directory'}  \n"
        f"**Scope out:** {a.scope_out or 'Lucent memory/, other idea/ projects'}\n\n"
        f"## Phases\n\n{phases}\n"
        f"## Reference\n\n{a.reference or '- (none provided)'}\n"
    )

    # --- README.md ------------------------------------------------------
    (proj / "README.md").write_text(
        f"# {name}\n\n{a.purpose or ''}\n\n"
        f"## Quick start\n\n```bash\ncd {proj} && claude\n```\n\n"
        f"Launches in project mode: voice + daily-note rules only, no Lucent bundle.\n\n"
        f"## Service\n\n- **Port:** {port} (registered in `idea/PORTS.md`)\n\n"
        f"## Planning\n\nSee `planning.md` for phases and scope.\n"
    )

    # --- .gitignore -----------------------------------------------------
    (proj / ".gitignore").write_text(
        "__pycache__/\n*.pyc\n.venv/\nnode_modules/\n.env\n*.log\ndist/\nbuild/\n"
    )

    # --- Ledger row (idea/PORTS.md) -------------------------------------
    led = LEDGER.read_text()
    row = f"| {port} | {name} | server | `idea/{name}` |\n"
    marker = "<!-- new_project.py appends"
    if marker in led:
        led = led.replace(marker, row + marker)
    else:
        led = led.rstrip() + "\n" + row
    LEDGER.write_text(led)

    # --- Register in project-health.sh PORTS map (keep both in sync) -----
    health_ok = register_in_health(name, port)

    print(f"[OK] Project '{name}' scaffolded at {proj}")
    print(f"     Port {port} registered in idea/PORTS.md")
    if health_ok:
        print(f"     Port {port} registered in idea/project-health.sh PORTS map")
    else:
        print(f"     [!] Could not auto-edit project-health.sh — add ['{name.lower().replace(' ', '_')}']={port} by hand")
    print(f"     Files: CLAUDE.md, planning.md, README.md, .gitignore, .lucentrc")
    print(f"     Planning doc path declared: {planning_rel} (create it in Lucent if non-trivial)")
    print(f"\n     NOTE: once the service runs, add START/STOP/STATUS entries for it")
    print(f"           in project-health.sh so the control script can manage it.")
    print(f"\n     Launch:  cd {proj} && claude")
    return 0


def register_in_health(name: str, port: int) -> bool:
    """Insert a key into the project-health.sh `declare -A PORTS=( ... )` block."""
    if not HEALTH.exists():
        return False
    text = HEALTH.read_text()
    key = name.lower().replace(" ", "_")
    m = re.search(r"(declare -A PORTS=\(\n)(.*?)(\n\))", text, flags=re.S)
    if not m:
        return False
    if re.search(rf'\["{re.escape(key)}"\]', m.group(2)) or f"]={port}\n" in m.group(2):
        return True  # already present
    new_block = m.group(1) + m.group(2) + f'\n  ["{key}"]={port}' + m.group(3)
    HEALTH.write_text(text[:m.start()] + new_block + text[m.end():])
    return True


# --------------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser(description="Scaffold a Lucent idea/ project.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ports", help="Show ledger + propose free ports (writes nothing).")

    c = sub.add_parser("create", help="Scaffold project with a confirmed port.")
    c.add_argument("--name", required=True)
    c.add_argument("--port", type=int, required=True)
    c.add_argument("--purpose", default="")
    c.add_argument("--type", default="lightweight", choices=["lightweight", "full"])
    c.add_argument("--tech", default="")
    c.add_argument("--scope-in", dest="scope_in", default="")
    c.add_argument("--scope-out", dest="scope_out", default="")
    c.add_argument("--features", default="", help="Pipe-delimited: 'Feat A||Feat B||Feat C'")
    c.add_argument("--reference", default="")
    c.add_argument("--focus", default="")

    args = p.parse_args()
    if args.cmd == "ports":
        return cmd_ports(args)
    if args.cmd == "create":
        return cmd_create(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
