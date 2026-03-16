#!/usr/bin/env python3
"""Memory migration script: OpenClaw .md files -> Mem0 + Qdrant Server.

Usage:
    python3 migrate.py --dry-run          # Preview only
    python3 migrate.py --execute --limit 30   # Small sample
    python3 migrate.py --execute          # Full migration
"""
import argparse, hashlib, json, os, re, sys, time
from pathlib import Path
from datetime import datetime

os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

WORKSPACE = Path.home() / ".openclaw" / "workspace-external"
WORKSPACE_OLD = Path.home() / ".openclaw" / "workspace" / "memory"

SCOPE_RULES = {
    "lessons-learned.md": ("lesson", "global"),
    "solutions_and_skills.md": ("knowledge", "global"),
    "tools-reference.md": ("procedure", "global"),
    "team-routing.md": ("procedure", "global"),
    "dianxiaomi_sop.md": ("procedure", "global"),
    "dianxiaomi-sku-import-guide.md": ("procedure", "global"),
    "dianxiaomi_notes.md": ("knowledge", "global"),
    "ops-experience.md": ("lesson", "global"),
    "cursor-agent-skills.md": ("procedure", "global"),
    "creation-experience.md": ("lesson", "agent:creator"),
    "content-creation-guide.md": ("procedure", "agent:creator"),
    "task-patterns.md": ("procedure", "agent:creator"),
    "xhs-operations.md": ("procedure", "agent:creator"),
}

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")


def classify_file(filepath: Path, agent: str) -> tuple:
    """Return (mem_type, scope) for a file."""
    name = filepath.name
    if name in SCOPE_RULES:
        return SCOPE_RULES[name]
    if name == "profile.md":
        parent = filepath.parent.name
        return ("procedure", f"group:{parent}")
    if DATE_PATTERN.match(name):
        return ("task_log", "unscoped")
    if "learning" in str(filepath):
        return ("lesson", "global")
    if name == "README.md":
        return None
    return ("knowledge", "global")


def split_sections(text: str) -> list:
    """Split markdown by ## headers into sections."""
    sections = []
    current_title = ""
    current_lines = []
    for line in text.split("\n"):
        if line.startswith("## "):
            if current_lines:
                content = "\n".join(current_lines).strip()
                if content and len(content) > 20:
                    sections.append((current_title, content))
            current_title = line.lstrip("# ").strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        content = "\n".join(current_lines).strip()
        if content and len(content) > 20:
            sections.append((current_title, content))
    return sections


def make_migration_id(filepath: str, section_idx: int) -> str:
    """Deterministic ID for idempotent migration."""
    raw = f"{filepath}::{section_idx}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def scan_files() -> list:
    """Scan all memory files and produce migration records."""
    records = []
    agents_dirs = [
        ("main", WORKSPACE / "main" / "memory"),
        ("devops", WORKSPACE / "devops" / "memory"),
        ("monitor", WORKSPACE / "monitor" / "memory"),
        ("creator", WORKSPACE / "creator" / "memory"),
    ]
    for agent, base_dir in agents_dirs:
        if not base_dir.exists():
            continue
        for md_file in sorted(base_dir.rglob("*.md")):
            rel = md_file.relative_to(base_dir)
            result = classify_file(md_file, agent)
            if result is None:
                continue
            mem_type, scope = result
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            if len(text.strip()) < 30:
                continue
            sections = split_sections(text)
            if not sections:
                mid = make_migration_id(str(rel), 0)
                records.append({
                    "content": text.strip()[:2000],
                    "mem_type": mem_type,
                    "scope": scope,
                    "agent": agent,
                    "source": "migration",
                    "trust": "medium",
                    "original_file": str(rel),
                    "migration_id": mid,
                })
            else:
                for idx, (title, content) in enumerate(sections):
                    mid = make_migration_id(str(rel), idx)
                    prefix = f"[{title}] " if title else ""
                    records.append({
                        "content": f"{prefix}{content}"[:2000],
                        "mem_type": mem_type,
                        "scope": scope,
                        "agent": agent,
                        "source": "migration",
                        "trust": "medium",
                        "original_file": str(rel),
                        "migration_id": mid,
                    })
    return records


def dry_run(records):
    """Print migration preview."""
    from collections import Counter
    scope_counts = Counter(r["scope"] for r in records)
    type_counts = Counter(r["mem_type"] for r in records)
    agent_counts = Counter(r["agent"] for r in records)

    print(f"Total: {len(records)} memories to migrate\n")
    print("By scope:")
    for s, c in scope_counts.most_common():
        print(f"  {s}: {c}")
    print("\nBy type:")
    for t, c in type_counts.most_common():
        print(f"  {t}: {c}")
    print("\nBy agent:")
    for a, c in agent_counts.most_common():
        print(f"  {a}: {c}")
    print("\nSamples (first 2 per type):")
    shown = Counter()
    for r in records:
        if shown[r["mem_type"]] < 2:
            shown[r["mem_type"]] += 1
            print(f"  [{r['mem_type']}/{r['scope']}] {r['content'][:80]}...")


def execute(records, limit=None):
    """Write records to Mem0."""
    from mem0 import Memory

    oc = json.load(open(Path.home() / ".openclaw" / "openclaw.json"))
    config = {
        "vector_store": {"provider": "qdrant", "config": {
            "collection_name": "openclaw_memories",
            "host": "localhost", "port": 6333,
        }},
        "llm": {"provider": "openai", "config": {
            "model": "claude-opus-4-6",
            "api_key": oc["models"]["providers"]["your_provider"]["apiKey"],
            "openai_base_url": oc["models"]["providers"]["your_provider"].get("baseUrl", "https://api.your_provider.top") + "/v1",
        }},
        "embedder": {"provider": "gemini", "config": {
            "model": "models/gemini-embedding-001",
            "embedding_dims": 3072,
        }},
        "version": "v1.1",
    }
    m = Memory.from_config(config)

    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    qc = QdrantClient(host="localhost", port=6333)

    if limit:
        records = records[:limit]

    ok, fail, skip = 0, 0, 0
    for i, r in enumerate(records):
        try:
            existing = qc.scroll("openclaw_memories", scroll_filter=Filter(
                must=[FieldCondition(key="migration_id", match=MatchValue(value=r["migration_id"]))]
            ), limit=1)
            if existing[0]:
                skip += 1
                if skip <= 5:
                    print(f"  [{i+1}/{len(records)}] SKIP: {r['original_file']}")
                continue
        except Exception:
            pass

        metadata = {
            "scope": r["scope"],
            "mem_type": r["mem_type"],
            "source": r["source"],
            "trust": r["trust"],
            "agent": r["agent"],
            "original_file": r["original_file"],
            "migration_id": r["migration_id"],
            "access_count": 0,
            "archived": False,
            "embedding_model": "gemini-embedding-001",
            "schema_version": 1,
        }
        try:
            result = m.add(r["content"], user_id="main", metadata=metadata)
            ok += 1
            if (i + 1) % 10 == 0:
                print(f"  [{i+1}/{len(records)}] OK: {r['mem_type']}/{r['scope']} - {r['content'][:50]}...")
        except Exception as e:
            fail += 1
            print(f"  [{i+1}/{len(records)}] FAIL: {e}")
        time.sleep(0.5)

    print(f"\nDone: {ok} OK, {fail} FAIL, {skip} SKIP")
    total = m.get_all(user_id="main")
    items = total if isinstance(total, list) else total.get("results", [])
    print(f"Total memories in Mem0: {len(items)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    records = scan_files()
    if args.dry_run or (not args.execute):
        dry_run(records)
    elif args.execute:
        execute(records, args.limit)
