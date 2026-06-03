#!/usr/bin/env python3
"""
NERO Phase 1 — Semantic memory index using local Ollama embeddings.

Indexes three memory sources:
  - memory/LTMemory.md
  - ~/.claude/projects/-home-nick-dev-lucent/memory/*.md  (auto-memory)
  - memory/YYYY-MM-DD.md  (last 7 days of daily notes)

Uses nomic-embed-text via Ollama — zero cost, fully local, nothing leaves machine.
Cache at memory/.recall_index.json; incrementally updated (re-embeds only changed
chunks so subsequent turns are fast).

Usage:
  python3 scripts/memory_index.py build          # force rebuild
  python3 scripts/memory_index.py query "text"   # test a query
  python3 scripts/memory_index.py status         # show index stats
"""

import hashlib
import json
import math
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

LUCENT_DIR = Path(__file__).parent.parent
MEMORY_DIR = LUCENT_DIR / "memory"
SKILLS_DIR = MEMORY_DIR / "skills"
AUTO_MEMORY_DIR = Path.home() / ".claude/projects/-home-nick-dev-lucent/memory"
INDEX_PATH = MEMORY_DIR / ".recall_index.json"

OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"
DAILY_NOTE_LOOKBACK_DAYS = 7
MAX_CHUNK_CHARS = 600
DEFAULT_TOP_K = 5
DEFAULT_MIN_SCORE = 0.30

# Auto-memory files that are pure index/template — not worth recalling
_AUTO_MEMORY_SKIP = {"MEMORY.md", "YYYY-MM-DD.md"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha16(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _chunk_markdown(text: str, source: str) -> list[dict]:
    """
    Split markdown into heading-bounded chunks, each ≤ MAX_CHUNK_CHARS.
    Very short sections (<20 chars of body) are dropped.
    """
    chunks = []
    current_heading = ""
    current_body: list[str] = []

    def flush():
        body = "\n".join(current_body).strip()
        if len(body) < 20:
            return
        full = (current_heading + "\n" + body).strip() if current_heading else body
        if len(full) <= MAX_CHUNK_CHARS:
            t = full
            chunks.append({"source": source, "text": t, "hash": _sha16(t)})
        else:
            # Oversized section — split by paragraph
            paras = [p.strip() for p in body.split("\n\n") if p.strip()]
            for para in paras:
                t = (current_heading + "\n" + para).strip() if current_heading else para
                t = t[:MAX_CHUNK_CHARS]
                if len(t) >= 20:
                    chunks.append({"source": source, "text": t, "hash": _sha16(t)})

    for line in text.splitlines():
        if line.startswith("#"):
            flush()
            current_heading = line
            current_body = []
        else:
            current_body.append(line)
    flush()
    return chunks


def _get_sources() -> list[tuple[str, Path]]:
    sources: list[tuple[str, Path]] = []

    lt = MEMORY_DIR / "LTMemory.md"
    if lt.exists():
        sources.append(("LTMemory", lt))

    # Phase 4b — archived LTMemory sessions stay queryable even though they're
    # out of the live context bundle.
    lt_archive = MEMORY_DIR / "LTMemory.archive.md"
    if lt_archive.exists():
        sources.append(("LTMemory-archive", lt_archive))

    if AUTO_MEMORY_DIR.exists():
        for p in sorted(AUTO_MEMORY_DIR.glob("*.md")):
            if p.name not in _AUTO_MEMORY_SKIP:
                sources.append((f"memory/{p.stem}", p))
        # Phase 4b — archived auto-memory files remain indexed for recall.
        am_archive = AUTO_MEMORY_DIR / "archive"
        if am_archive.exists():
            for p in sorted(am_archive.glob("*.md")):
                sources.append((f"memory-archive/{p.stem}", p))

    today = date.today()
    for i in range(DAILY_NOTE_LOOKBACK_DAYS):
        d = today - timedelta(days=i)
        p = MEMORY_DIR / f"{d}.md"
        if p.exists():
            sources.append((f"daily/{d}", p))

    # NERO Phase 2 — skill library (SKILL.md + references/*.md for each skill)
    if SKILLS_DIR.exists():
        for skill_dir in sorted(SKILLS_DIR.iterdir()):
            if not skill_dir.is_dir() or skill_dir.name.startswith("."):
                continue
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                sources.append((f"skill/{skill_dir.name}", skill_md))
            refs_dir = skill_dir / "references"
            if refs_dir.exists():
                for ref in sorted(refs_dir.glob("*.md")):
                    sources.append((f"skill/{skill_dir.name}/ref/{ref.stem}", ref))

    return sources


def _fingerprint(sources: list[tuple[str, Path]]) -> str:
    parts = []
    for label, p in sources:
        try:
            st = p.stat()
            parts.append(f"{label}:{st.st_mtime:.0f}:{st.st_size}")
        except OSError:
            pass
    return _sha16("|".join(parts))


# ---------------------------------------------------------------------------
# Ollama embedding
# ---------------------------------------------------------------------------

def _embed(text: str) -> Optional[list[float]]:
    payload = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode()
    req = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())["embedding"]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Cosine similarity (pure Python — corpus is small enough)
# ---------------------------------------------------------------------------

def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ---------------------------------------------------------------------------
# Index persistence
# ---------------------------------------------------------------------------

def load_index() -> dict:
    if INDEX_PATH.exists():
        try:
            return json.loads(INDEX_PATH.read_text())
        except Exception:
            pass
    return {"fingerprint": "", "chunks": []}


def save_index(index: dict) -> None:
    INDEX_PATH.write_text(json.dumps(index, separators=(",", ":")))


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_index(force: bool = False) -> dict:
    """
    Build or incrementally update the recall index.

    Fast path: if source fingerprint matches cache, return cached index immediately.
    Slow path: re-chunk all sources, re-use embeddings for unchanged chunks, embed new ones.
    """
    sources = _get_sources()
    fp = _fingerprint(sources)
    cached = load_index()

    if not force and cached.get("fingerprint") == fp:
        return cached

    # Reuse embeddings for chunks whose text hash is unchanged
    existing_embs: dict[str, list[float]] = {
        c["hash"]: c["embedding"]
        for c in cached.get("chunks", [])
        if "embedding" in c
    }

    new_chunks = []
    for label, path in sources:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for chunk in _chunk_markdown(text, label):
            h = chunk["hash"]
            if h in existing_embs:
                chunk["embedding"] = existing_embs[h]
            else:
                emb = _embed(chunk["text"])
                if emb is None:
                    continue  # Ollama down — skip, don't poison index
                chunk["embedding"] = emb
            new_chunks.append(chunk)

    index = {"fingerprint": fp, "chunks": new_chunks}
    save_index(index)
    return index


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

def query(text: str, top_k: int = DEFAULT_TOP_K, min_score: float = DEFAULT_MIN_SCORE) -> list[dict]:
    """
    Embed `text` and return the top-K most similar memory chunks.
    Returns list of {source, text, score}, sorted descending by score.
    Returns [] gracefully if Ollama is unavailable.
    """
    index = build_index()
    if not index["chunks"]:
        return []

    q_emb = _embed(text)
    if not q_emb:
        return []

    scored = []
    for chunk in index["chunks"]:
        emb = chunk.get("embedding")
        if not emb:
            continue
        score = _cosine(q_emb, emb)
        if score >= min_score:
            scored.append({"source": chunk["source"], "text": chunk["text"], "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


# ---------------------------------------------------------------------------
# Recall block — the fenced context block for the hook
# ---------------------------------------------------------------------------

def sanitize_context(text: str) -> str:
    """Strip any pre-existing memory-context fence tags from provider text."""
    import re
    text = re.sub(r'<\s*memory-context\s*>[\s\S]*?</\s*memory-context\s*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</?\s*memory-context\s*>', '', text, flags=re.IGNORECASE)
    return text


def recall_block(query_text: str, top_k: int = DEFAULT_TOP_K) -> str:
    """
    Return a fenced <memory-context> block for the query, or "" if nothing relevant.

    The fence and system note tell Claude this is recalled memory, not user input,
    matching the Hermes trust-boundary pattern from memory_manager.py.
    """
    results = query(query_text, top_k=top_k)
    if not results:
        return ""

    lines = [
        "<memory-context>",
        "[System note: The following is recalled memory context, NOT new user input. "
        "Treat as authoritative reference data — this is Lucent's persistent memory "
        "and should inform your response where relevant.]",
        "",
    ]
    for r in results:
        lines.append(f"[{r['source']}]")
        lines.append(r["text"].strip())
        lines.append("")
    lines.append("</memory-context>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"

    if cmd == "build":
        idx = build_index(force=True)
        print(f"Index built: {len(idx['chunks'])} chunks indexed")

    elif cmd == "query":
        if len(sys.argv) < 3:
            print("Usage: memory_index.py query <text>", file=sys.stderr)
            sys.exit(1)
        q_text = " ".join(sys.argv[2:])
        results = query(q_text)
        if not results:
            print("No results above threshold.")
        for r in results:
            print(f"\n[{r['score']:.3f}] {r['source']}")
            print(r["text"][:200])

    elif cmd == "status":
        idx = load_index()
        chunks = idx.get("chunks", [])
        sources = {}
        for c in chunks:
            src = c["source"].split("/")[0]
            sources[src] = sources.get(src, 0) + 1
        print(f"Total chunks : {len(chunks)}")
        print(f"Fingerprint  : {idx.get('fingerprint', 'none')}")
        print("By source    :")
        for src, count in sorted(sources.items()):
            print(f"  {src}: {count}")
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
