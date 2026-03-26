---
title: "Your AI Agent Has Amnesia — Here's How to Fix It (MCP + Mem0 + Qdrant)"
published: false
description: "A deep dive into building persistent, scope-aware memory for multi-agent AI systems. How a CPU cache hierarchy analogy, neuroscience-inspired decay, and the MCP protocol come together to give your agents long-term memory."
tags: mcp, ai, python, architecture
---

Every AI agent you have ever built forgets everything the moment the conversation ends.

I run a fleet of AI agents on Feishu (think of it as the Chinese Slack) and Telegram. A main orchestrator, a devops agent, a content writer, half a dozen specialized workers. One day my content agent asked me, for the fifth time, what writing style I preferred. The devops agent had no idea we had already debugged the same DNS issue last week. Every morning, each agent woke up as a blank slate.

That is not a feature. It is a bug. So I built [Engram](https://github.com/lofder/Engram) to fix it.

This article is a conceptual deep-dive into the architecture decisions behind it. You do not need to know what MCP or Mem0 is. You just need to have felt the pain of stateless agents.

---

## The Memory Hierarchy Your Agent Is Missing

If you have taken a computer architecture class, you know the CPU cache hierarchy:

```
Access speed    +-----------+    Capacity
  fastest       |  L1 Cache |    smallest
                +-----------+
                |  L2 Cache |
                +-----------+
                |  L3 Cache |
                +-----------+
                |    RAM    |
                +-----------+
                |   Disk    |    largest
  slowest       +-----------+
```

AI agents have an equivalent hierarchy, but most developers only build two of the three layers:

```
Layer    | Analogy   | What It Is                        | Properties
---------|-----------|-----------------------------------|--------------------
L1       | L1 Cache  | Context window (conversation)     | Fast, small, gone when chat ends
L2       | L2 Cache  | Persistent semantic memory         | THIS IS THE MISSING PIECE
L3       | Disk      | Files, databases, wikis           | Slow to search, huge, unstructured
```

**L1** is what every agent already has: the conversation history. It is fast and relevant, but it vanishes when the session ends (or when the context window fills up and older messages get evicted).

**L3** is what people reach for first when they want "memory": dump everything into a vector database, a folder of markdown files, or a RAG pipeline over your documents. It works for reference material, but it is cold storage. Searching for "what does the user prefer" across thousands of documents is slow and imprecise.

**L2** -- persistent semantic memory -- is what sits between them. It stores extracted facts, preferences, lessons, and decisions. It is small enough to search quickly, structured enough to filter precisely, and persistent across every conversation. This is what Engram provides.

The key insight: your agent does not need to remember every word of every conversation. It needs to remember the *conclusions* -- the user prefers concise writing, the production database is on port 5433, we decided to use Redis for caching last Tuesday.

---

## Why Scope Matters More Than You Think

Here is a concrete problem. I run two agents on the same Feishu platform:

- A **devops agent** that manages servers, monitors logs, and runs deployments
- A **content agent** that drafts articles, manages social media, and writes ad copy

Without scope isolation, here is what actually happened: the content agent started referring to "the cluster" in marketing copy. The devops agent once suggested we should "A/B test the nginx configuration." Their memories had bled into each other.

The solution is a 4-scope model:

```
                        +-----------+
                        |  global   |  Shared across all agents and chats
                        +-----+-----+  (user facts, cross-cutting preferences)
                              |
              +---------------+---------------+
              |               |               |
        +-----+-----+  +-----+-----+  +-----+-----+
        | group:oc01 |  | group:oc02 |  |    dm     |  Per-chat / per-group
        +-----+-----+  +-----+-----+  +-----+-----+  (project context, group decisions)
              |               |               |
        +-----+-----+  +-----+-----+  +-----+-----+
        | agent:devops  | agent:writer  | agent:...  |  Per-agent private
        +-----+-----+  +-----+-----+  +-----+-----+  (agent-specific procedures)
```

Every memory is tagged with exactly one scope at write time. Every search merges results from the current scope *and* global, so agents always have access to cross-cutting knowledge (like user preferences) without seeing each other's operational details.

The config makes this concrete. Here is the permission model from the actual `config.yaml`:

```yaml
agents:
  main:
    read: [global, "group:*", dm, "agent:*"]
    write: [global, "group:*", dm]
    allowed_types: [preference, fact, procedure, lesson, decision, task_log]
  devops:
    read: [global, "group:*", dm, "agent:*"]
    write: [global, "group:*", dm, "agent:*"]
    allowed_types: [preference, fact, procedure, lesson, decision, task_log]
  writer:
    read: []
    write: ["agent:writer"]
    allowed_types: [procedure, task_log]

default_agent_policy:
  read: [global]
  write: []
  allowed_types: []
```

The main orchestrator can read and write broadly. Specialized workers like `writer` can only write to their own private scope. And by default, unknown agents get read-only access to global memory and cannot write at all.

This is not just about data hygiene. It is about trust boundaries. If an agent gets compromised or hallucinates, the blast radius is contained.

---

## The MCP Interface: Why Not Just a REST API?

MCP stands for [Model Context Protocol](https://modelcontextprotocol.io/) -- it is an open standard for connecting AI agents to tools and data sources. You might be wondering: why not just expose memory as a REST API?

The answer is ergonomics. With a REST API, you need to write custom integration code in every agent: HTTP client setup, authentication, response parsing, error handling. With MCP, your agent calls memory tools the exact same way it calls *any other tool* -- file operations, web search, code execution. The model already knows how to use tools. Memory becomes just another tool in the toolbox.

Engram exposes 5 tools through FastMCP:

| Tool | Purpose |
|------|---------|
| `mem0_add` | Store a memory with scope, type, trust level, provenance |
| `mem0_search` | Semantic search with scope isolation and dual-query merge |
| `mem0_get_all` | List all memories, optionally filtered by scope |
| `mem0_status` | Health check: memory counts, scope distribution, backend status |
| `mem0_maintenance` | Trigger daily/weekly maintenance cycles |

Here is what a real conversation flow looks like. When my agent starts a new chat, it does not ask "what do you like?" again. It searches memory first:

```
User: Help me write a product description for the new headphones.

Agent (internal): call mem0_search(
    query="user writing style preferences",
    scope="group:oc_marketing",
    limit=5
)

Memory returns:
  - "User prefers concise, no-fluff writing style" (trust: high)
  - "Product descriptions should lead with the benefit, not specs" (trust: medium)
  - "Avoid exclamation marks in copy" (trust: high)

Agent: Here's a draft in your preferred concise style,
       leading with the benefit...
```

And after the conversation, the agent stores the conclusion, not the whole chat:

```
Agent (internal): call mem0_add(
    content="Headphone product line uses the tagline format:
             [benefit] + [one technical proof point]",
    scope="group:oc_marketing",
    mem_type="decision",
    source="user_approved",
    trust="high"
)
```

I also built a [separate MCP server for dropshipping product imports](https://dev.to/_95a3e57463e6442feacd0/i-built-an-mcp-server-to-automate-dropshipping-product-imports-3m5b) that consumes this memory as a client. When that agent processes a new product, it queries memory for supplier preferences, pricing rules, and past decisions -- all scoped to the relevant workspace.

---

## The Write Path Trade-off: Fast vs. Smart

This was the single most impactful architecture decision in the project, and I almost got it wrong.

Mem0 has a built-in feature where every `add()` call passes through an LLM to extract structured entities and relationships from the raw text. It is smart. It is also slow.

```
Write with LLM extraction (infer=True):     5-8 seconds
Write with embedding only  (infer=False):   ~1.3 seconds
```

In a real-time chat, 5-8 seconds of latency on every memory write is unacceptable. The user is waiting for a response while the agent is quietly making an API call to Claude or GPT to analyze the memory content.

The solution is a hot/cold split inspired by the [MAPLE paper](https://arxiv.org/abs/2602.13258):

```
                HOT PATH (real-time)              COLD PATH (scheduled)
                ~1.3s per write                   Runs at 3:00 AM

User talks  ──> mem0_add(infer=False) ──>  Qdrant    <── maintenance.py
to agent        Embedding only                         │
                No LLM extraction                      ├── Opus re-extraction
                No classification                      ├── Dedup (0.92 threshold)
                                                       ├── Classification
                                                       ├── Conflict detection
                                                       └── Decay scoring
```

During the day, writes are fast: embed the text, store it with metadata, move on. The `infer=False` flag tells Mem0 to skip the LLM extraction step:

```python
result = mem.add(content, user_id="default", metadata=metadata, infer=False)
```

At 3 AM, the maintenance script wakes up, pulls all of today's memories, and re-processes them through a high-quality model (Claude Opus) for proper entity extraction, deduplication, and classification. It is the same data, but now with rich structure.

This means there is a window -- roughly from when a memory is written until the next maintenance run -- where the memory exists but is not fully classified. In practice, this rarely matters because semantic search works on the embedding regardless. But if you needed a memory classified as `procedure` vs `task_log` for filtering, you would have to wait until maintenance runs.

The fallback chain also deserves a mention. If Mem0 is unavailable at write time, the server does not drop the memory. It queues it:

```python
if mem is None:
    entry = {"write_id": write_id, "content": content, "metadata": metadata}
    with open(WRITE_QUEUE_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return {"queued": True, "reason": "Mem0 unavailable, cached for replay"}
```

On the next successful write, the queue gets replayed. Writes are never lost, even when the backend crashes.

---

## Keeping Memory Alive: Decay, Consolidation, and Conflict

Here is something most "memory for AI" projects get wrong: they treat memory as write-once-read-forever. Store it and forget about it (no pun intended).

But memory decays. Memory conflicts. Memory fragments. If you have used your system for three months, you have duplicates, contradictions, and a pile of task logs from February that nobody will ever query again. Without maintenance, search quality degrades as noise drowns out signal.

The Engram maintenance system has four cognitive engines, and each one draws from a different idea about how memory works.

### Decay: The Forgetting Curve

Inspired by [Bjork's storage-retrieval strength theory](https://en.wikipedia.org/wiki/Retrieval_practice) and the [FadeMem paper](https://arxiv.org/abs/2601.18642), each memory gets an importance score that decays exponentially over time:

```
I(t) = exp(-lambda * effective_age)

where:
  effective_age = age_days / (1 + min(log(1 + access_count), cap))
  lambda = ln(2) / half_life_days
```

The crucial detail: `access_count` slows the decay. A memory that gets retrieved often decays slower than one that was written and never read again. This mirrors how human memory works -- the more you recall something, the harder it is to forget.

Different memory types have different half-lives:

| Type | Half-life | Rationale |
|------|-----------|-----------|
| `task_log` | 30 days | "Deployed v2.1 to staging" -- useful for a month, noise after that |
| `procedure` | 90 days | "Restart command is X" -- lasts longer but can become stale |
| `fact`, `preference`, `lesson` | Never decays | "User's name is Y" -- these are permanent |

When importance drops below 0.10, the memory gets archived -- not deleted. It is soft removal. You can always un-archive if needed.

### Consolidation: Turning Fragments Into Knowledge

After a week of conversations, you might have 15 `task_log` entries about debugging the same service. Individually, they are noise. Together, they contain a lesson.

The consolidation engine groups related memories, sends them through an LLM, and produces a single `knowledge` summary. The original fragments get an accelerated decay but are not deleted -- provenance is tracked through a `consolidated_from` field.

### Conflict Resolution: When Memory Contradicts Itself

"User prefers dark mode" and "User prefers light mode" -- stored two months apart. Which one is true?

The conflict engine identifies same-type memories within the same scope that might contradict each other, then uses an LLM to judge: are they actually contradictory, or just about different topics? If contradictory, the newer one wins (with a `superseded_by` marker on the loser).

### Putting It Together

The maintenance runs on a two-tier schedule:

```
Daily (3:00 AM):
  1. Re-extract today's memories with Opus (high-quality LLM)
  2. Deduplicate (cosine similarity > 0.92 = auto-merge)

Weekly (Sunday):
  3. All daily steps, plus:
  4. Conflict detection and resolution
  5. Consolidation of fragmented task_logs
  6. Decay scoring and archival
```

A typical weekly report (sent to Feishu automatically) looks like: 4 memories re-extracted, 2 duplicates merged, 1 conflict resolved, 3 task_log groups consolidated into knowledge, 7 old entries archived. Total: 142 active memories across 6 scopes.

---

## What I Would Do Differently

No project survives contact with production unchanged. Here is what I learned.

**The classification cascade was over-engineered early on.** I built a two-layer classifier (keyword rules + LLM fallback) before I had enough data to know which memory types actually mattered. In practice, the keyword layer catches about 70% of cases and the remaining 30% default to `task_log` until maintenance reclassifies them. If I started over, I would ship with keywords-only and add the LLM layer only after accumulating a month of production data.

**Scope granularity hit a sweet spot.** I initially considered per-message scoping, which would have been too fine-grained. The 4-scope model (global / group / dm / agent) turned out to be exactly right. Every memory naturally fits one of these, and I have never needed a fifth scope.

**The write queue was a late addition that saved me multiple times.** I did not plan for Qdrant downtime when I started. The first time Qdrant crashed during a conversation, memories were silently lost. Adding the JSONL write queue with replay-on-next-write was a 30-line change that made the system genuinely resilient. Build your degradation path early.

**Real-time LLM extraction is a trap for multi-agent systems.** Every article about Mem0 shows the `infer=True` default, where the LLM enriches memories on write. That works for a single-user chatbot. With 8 agents generating memories throughout the day, those 5-8 second writes would have serialized everything. The hot/cold split was the right call. If you are building for multiple agents, start with `infer=False`.

**What surprised me most:** how quickly semantic search quality improves once you add scope filtering. Without scopes, searching "deployment process" returns a mix of devops procedures and content publishing workflows. With scope, the results are precise and relevant immediately. Scoping is not just an access control feature; it is a search quality feature.

---

## Getting Started

The full source is at [Engram](https://github.com/lofder/Engram). It runs as a standard MCP server -- plug it into any MCP-compatible framework.

If you want to see a real-world consumer of this memory system, check out my [dropshipping product import MCP server](https://dev.to/_95a3e57463e6442feacd0/i-built-an-mcp-server-to-automate-dropshipping-product-imports-3m5b), which queries memory for supplier preferences and pricing rules every time it processes a product.

The stack is intentionally simple: Python + FastMCP + Mem0 + Qdrant. No Kubernetes. No microservices. Just a single-process MCP server that starts with `python src/server.py` and a Qdrant instance you can run from a single binary.

Your agents do not have to start every conversation from scratch. Give them memory. They will thank you -- and more importantly, your users will stop repeating themselves.
