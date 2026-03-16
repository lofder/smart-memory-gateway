from __future__ import annotations
"""Memory classifier — two-layer cascade (keywords + LLM fallback).
记忆分类器 — 两层级联（关键词规则 + LLM 兜底）。

Layer 1: Fast keyword rules covering ~70% of clear-cut cases (zero latency).
第一层：关键词规则覆盖 ~70% 明确场景（零延迟）。

Layer 2: LLM classification for ambiguous cases (~30%), only used during maintenance.
第二层：LLM 分类处理歧义场景（~30%），仅在维护时使用。

Day-to-day add() does NOT classify — classification happens during nightly Opus re-add
and weekly maintenance.
日常 add() 不做分类 — 分类在凌晨 Opus 重提取和每周维护时进行。
"""
import re

KEYWORD_RULES: list[tuple[str, list[str]]] = [
    ("preference", [
        "以后", "以后都", "每次都", "偏好", "喜欢", "不喜欢", "风格",
        "always", "never", "prefer", "i like", "i dislike",
    ]),
    ("fact", [
        "我住在", "我是", "我叫", "我的名字", "我在.*工作",
        "my name", "i live in", "i am",
    ]),
    ("procedure", [
        "命令是", "步骤是", "流程是", "配置是", "路径是", "端口是",
        "帮我记住这个", "记住这个操作", "sop", "how to", "command",
    ]),
    ("decision", [
        "决定", "选择了", "确定用", "最终方案", "decided", "chosen",
    ]),
    ("lesson", [
        "教训", "踩坑", "经验是", "下次不要", "上次搞错", "lesson",
        "mistake", "learned that",
    ]),
    ("transient", [
        "^好的$", "^ok$", "^嗯$", "^收到$", "^谢谢$", "^明白$",
        "^yes$", "^no$", "^got it$",
    ]),
]

_compiled_rules: list[tuple[str, list[re.Pattern]]] = []
for mem_type, patterns in KEYWORD_RULES:
    _compiled_rules.append((mem_type, [re.compile(p, re.IGNORECASE) for p in patterns]))


def classify_by_keywords(content: str, context: str = "") -> str | None:
    """Classify memory by keyword rules. Returns mem_type or None if ambiguous.
    通过关键词规则分类记忆。返回 mem_type 或 None（歧义时交给 LLM）。
    """
    text = f"{content} {context}".strip().lower()

    for mem_type, patterns in _compiled_rules:
        for pat in patterns:
            if pat.search(text):
                return mem_type

    return None


def classify_by_llm(content: str, context: str, llm_call) -> dict:
    """Classify using LLM. llm_call is a callable(prompt) -> str.

    Returns {"type": "...", "confidence": 0.0-1.0, "reasoning": "..."}.
    """
    prompt = f"""Classify this memory into exactly one type. Return ONLY valid JSON.

Memory: "{content}"
Context: {context or "No additional context."}

Types and definitions:
- fact: User states something about themselves (name, location, job)
- preference: User expresses a lasting preference or style choice ("always use X", "I prefer Y")
- procedure: Operational command, config path, SOP, workflow step
- decision: A choice made with reasoning ("decided to use X because Y")
- task_log: Record of what was done and the result
- lesson: Mistake learned, gotcha, experience gained
- knowledge: Summarized insight or consolidated information
- transient: Greeting, confirmation, temporary instruction for this task only

Output: {{"type": "...", "confidence": 0.0-1.0, "reasoning": "..."}}"""

    try:
        import json
        response = llm_call(prompt)
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(cleaned)
    except Exception:
        return {"type": "task_log", "confidence": 0.3, "reasoning": "LLM classification failed, defaulting to task_log"}


def classify(content: str, context: str = "", llm_call=None) -> str:
    """Two-layer classification. Uses keywords first, LLM as fallback.
    两层级联分类。先用关键词，歧义时用 LLM 兜底。
    """
    result = classify_by_keywords(content, context)
    if result is not None:
        return result

    if llm_call is not None:
        llm_result = classify_by_llm(content, context, llm_call)
        return llm_result.get("type", "task_log")

    return "task_log"
