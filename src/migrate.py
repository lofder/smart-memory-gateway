#!/usr/bin/env python3
"""Memory migration script: Import memories from markdown files into Engram.

Usage:
    python3 migrate.py --source ~/my-project/memory --dry-run
    python3 migrate.py --source ~/my-project/memory --execute --limit 30
    python3 migrate.py --source ~/my-project/memory --execute
"""
import argparse, hashlib, json, os, re, sys, time
from pathlib import Path
from datetime import datetime

os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

import yaml

CONFIG_PATH = Path(os.environ.get(
    "ENGRAM_CONFIG",
    Path(__file__).parent.parent / "config.yaml",
))
HOST_CONFIG_PATH = Path(os.environ.get(
    "ENGRAM_HOST_CONFIG",
    Path.home() / ".mem0-gateway" / "config.json",
))
ENV_PATHS = [
    Path.home() / ".mem0-gateway" / ".env",
    Path.home() / ".mem0-gateway" / ".env.main",
]
ENV_PLACEHOLDER_RE = re.compile(r"^\$\{([^}]+)\}$")

with open(CONFIG_PATH) as f:
    CFG = yaml.safe_load(f)


def _load_env_layers():
    for env_path in ENV_PATHS:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value


def _resolve_env_placeholder(value):
    if not isinstance(value, str):
        return value
    match = ENV_PLACEHOLDER_RE.fullmatch(value.strip())
    if match:
        return os.environ.get(match.group(1), value)
    return value


def _normalize_openai_base_url(value, default):
    base_url = (_resolve_env_placeholder(value) or default).rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    return base_url


KEYWORD_RULES = [
    ("preference", ["prefer", "always", "never", "style", "like", "dislike",
                     "以后", "偏好", "喜欢", "不喜欢", "风格"]),
    ("procedure", ["command", "how to", "steps", "sop", "workflow", "config",
                    "命令", "步骤", "流程", "配置", "路径"]),
    ("lesson", ["mistake", "learned", "gotcha", "pitfall",
                "教训", "踩坑", "经验", "下次"]),
    ("decision", ["decided", "chosen", "we chose",
                   "决定", "选择了", "确定用"]),
    ("fact", ["my name", "i am", "i live",
              "我是", "我叫", "我住"]),
]


def classify_content(content: str) -> str:
    text = content.lower()
    for mem_type, keywords in KEYWORD_RULES:
        for kw in keywords:
            if kw in text:
                return mem_type
    return "knowledge"


DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")


def split_sections(text: str) -> list:
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
    raw = f"{filepath}::{section_idx}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def scan_files(source_dir: Path, scope: str = "global", agent: str = "main") -> list:
    records = []
    if not source_dir.exists():
        print(f"Source directory not found: {source_dir}")
        return records

    for md_file in sorted(source_dir.rglob("*.md")):
        rel = md_file.relative_to(source_dir)
        if rel.name == "README.md":
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue
        if len(text.strip()) < 30:
            continue

        if DATE_PATTERN.match(rel.name):
            file_type = "task_log"
        else:
            file_type = None

        sections = split_sections(text)
        if not sections:
            mid = make_migration_id(str(rel), 0)
            mem_type = file_type or classify_content(text)
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
                mem_type = file_type or classify_content(content)
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
    from collections import Counter
    scope_counts = Counter(r["scope"] for r in records)
    type_counts = Counter(r["mem_type"] for r in records)

    print(f"Total: {len(records)} memories to migrate\n")
    print("By scope:")
    for s, c in scope_counts.most_common():
        print(f"  {s}: {c}")
    print("\nBy type:")
    for t, c in type_counts.most_common():
        print(f"  {t}: {c}")
    print("\nSamples (first 2 per type):")
    shown = Counter()
    for r in records:
        if shown[r["mem_type"]] < 2:
            shown[r["mem_type"]] += 1
            print(f"  [{r['mem_type']}/{r['scope']}] {r['content'][:80]}...")


def execute(records, limit=None):
    from mem0 import Memory
    _load_env_layers()

    if HOST_CONFIG_PATH.exists():
        with open(HOST_CONFIG_PATH) as f:
            oc = json.load(f)
    else:
        oc = {}

    q_cfg = CFG["qdrant"]
    emb_primary = CFG["embedding"]["primary"]
    llm_cfg = CFG.get("llm", {})
    llm_base_url = llm_cfg.get("base_url", "https://api.openai.com/v1")

    embedder_config = {
        "provider": emb_primary["provider"],
        "config": {
            "model": emb_primary["model"],
            "embedding_dims": emb_primary["dimensions"],
        },
    }
    if emb_primary["provider"] == "gemini":
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if api_key:
            embedder_config["config"]["api_key"] = api_key

    config = {
        "vector_store": {"provider": "qdrant", "config": {
            "collection_name": q_cfg["collection"],
            "host": q_cfg["host"],
            "port": q_cfg["port"],
        }},
        "llm": {"provider": "openai", "config": {
            "model": llm_cfg.get("model", "gpt-4o-mini"),
            "api_key": os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY", ""),
            "openai_base_url": _normalize_openai_base_url(llm_base_url, llm_base_url),
        }},
        "embedder": embedder_config,
        "version": "v1.1",
    }
    m = Memory.from_config(config)

    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    qc = QdrantClient(host=q_cfg["host"], port=q_cfg["port"])

    if limit:
        records = records[:limit]

    ok, fail, skip = 0, 0, 0
    for i, r in enumerate(records):
        try:
            existing = qc.scroll(q_cfg["collection"], scroll_filter=Filter(
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
            "embedding_model": CFG["embedding"]["model"],
            "schema_version": CFG.get("schema_version", 1),
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate markdown files into Engram memory")
    parser.add_argument("--source", type=str, required=True, help="Source directory containing .md files")
    parser.add_argument("--scope", type=str, default="global", help="Memory scope (default: global)")
    parser.add_argument("--agent", type=str, default="main", help="Agent identity (default: main)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--execute", action="store_true", help="Actually write to Mem0")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of records")
    args = parser.parse_args()

    records = scan_files(Path(args.source), scope=args.scope, agent=args.agent)
    if args.dry_run or (not args.execute):
        dry_run(records)
    elif args.execute:
        execute(records, args.limit)
