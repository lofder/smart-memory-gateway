# Engram v3 — 记忆系统设计文档

> 版本: 1.0 | 日期: 2026-03-14 | 作者: Cursor Agent + 用户共同设计
> 本文档面向 AI agent 和人类开发者，新论文或更新可按章节调整。

---

## 第一部分：概述与快速参考

### 设计理念

一句话：**让 AI agent 像有经验的员工一样记住用户偏好、工作流程和历史决策，而不是每次从零开始。**

### 架构总览

```
L1 Working Memory (host framework session context, 5min TTL)
    ↓ 搜索注入
L2 Engram (Mem0 + Qdrant Server, 本文档)
    ↓ 归档衰减
L3 File Archive (daily logs, cold storage)
```

### 快速参考卡片

| 操作 | 工具 | 示例 |
|------|------|------|
| 搜记忆 | `mcp(action="call", server="mem0", tool="mem0_search", args={...})` | `args={"query": "用户偏好", "scope": "group:oc_xxx", "limit": 5}` |
| 存记忆 | `mcp(action="call", server="mem0", tool="mem0_add", args={...})` | `args={"content": "...", "scope": "global", "mem_type": "preference"}` |
| 看状态 | `mcp(action="call", server="mem0", tool="mem0_status", args={})` | 返回总量/分布/健康度 |
| 跑维护 | `mcp(action="call", server="mem0", tool="mem0_maintenance", args={...})` | `args={"mode": "daily"}` |

**谁读谁写：**
- Main: 读全部 scope + 写 global/group/dm
- ops agent: 读写 global 的 procedure/lesson
- Worker agents: 写自己域的 procedure/task_log（`scope="agent:{name}"`），偏好从 Main 指令获取

**绝对不存：** 密码、API key、token、cookie 明文

---

## 第二部分：架构设计

### 组件清单

| 组件 | 版本 | 职责 | 端口/路径 |
|------|------|------|-----------|
| Qdrant Server | 1.17.0 | 向量存储 + 过滤 | localhost:6333 |
| Mem0 | 1.0.5 | 记忆管理（add/search/get_all） | Python library |
| MCP Server (FastMCP) | v3 | 工具注册 + 权限校验 + 降级 | stdio (host framework 插件) |
| 认知引擎 | v1 | 衰减/分类/巩固/冲突检测 | Python modules |
| 维护脚本 | v1 | 每日/每周自动维护 | cron |
| Gemini Embedding | 001 | MTEB #1 embedding 模型 | Google API (VPN) / lingyun 备选 |

### Scope 隔离模型

所有记忆统一 `user_id="default"`，通过 `metadata.scope` 实现多租户隔离：

| scope | 含义 | 示例 |
|-------|------|------|
| `global` | 全局共享 | 用户偏好、事实、经验 |
| `group:oc_xxx` | 群聊专属 | 群工作模板、群决策 |
| `dm` | 私聊专属 | 私聊上下文 |
| `agent:{name}` | Worker 私有域 | Writer SOP、Creator 参数 |
| `unscoped` | 待归类隔离区 | 迁移来源不明的旧数据 |
| `all` | 搜索专用 | 私聊时回忆全部 |
| `cross:oc_xxx` | 搜索专用 | 群内引用其他群 |

**搜索时双查询合并**：global + 当前 scope，交替插入排序（scope 优先）。

**写入时 scope 强制必传**：空 scope 拒绝写入。`all`/`cross:*` 只读不可写。

### 数据流

```
用户消息 → Main 判断是否搜记忆（~30%）
  ↓ 是
Main 调 mem0_search(scope="group:oc_xxx") → 返回 global + 群记忆
  ↓
Main 注入偏好到 Worker 指令 → Worker 执行
  ↓
Main 判断是否存记忆（~10%）→ mem0_add(infer=False)
  ↓
凌晨 03:00 维护 → Opus re-extract + 去重 + 报告
```

### 降级策略

| 故障层 | 降级行为 |
|--------|---------|
| Embedding API 超时 | 搜索返回空；写入缓存到 write_queue.jsonl |
| Qdrant Server 宕机 | 同上 + LaunchAgent KeepAlive 自动重启 |
| MCP Server 异常 | 返回错误信息，不崩溃进程 |

---

## 第三部分：神经科学基础

| 脑区/机制 | 功能 | 我们的实现 | 来源 |
|-----------|------|-----------|------|
| 海马体 | 时间线索引 + 情景记忆 | 每周时间线摘要 | BMAM (2601.20465) |
| 杏仁核 | 显著性过滤 | trust_level + 重要性评分 | BMAM |
| 前额叶 | 工作记忆 + 路由 | Main 搜→注入→分发 | BMAM |
| 睡眠巩固 | 短期→长期 + 冲突消解 | 每周维护巩固步骤 | Nature Comm 2022 |
| 遗忘曲线 | 指数衰减 + 间隔效应 | FadeMem 公式 + access_count | Ebbinghaus + FadeMem |
| 前摄干扰 | 旧信息干扰新信息 | 去重压缩 | arXiv 2506.08184 |

---

## 第四部分：学术依据

### 论文评估表

| 论文 | ID | 核心发现 | 采纳点 |
|------|-----|---------|--------|
| Hindsight | 2512.12818 | 4 网络 91.4% 准确率 | 区分 fact/preference/knowledge/log |
| MAPLE | 2602.13258 | trait +30% | HOT/COLD 分离，异步整理 |
| FadeMem | 2601.18642 | -45% 存储 | 重要性公式 + 衰减 |
| Multi-Agent Memory | 2603.10062 | 一致性是关键 | Main 集中写入避免冲突 |
| BMAM | 2601.20465 | 78.45% | 海马体时间索引 |
| TierMem | 2602.17913 | -54.1% token | 来源追踪 provenance |
| Proactive Interference | 2506.08184 | 干扰随量增长 | 去重压缩 |
| OWASP ASI06 | 2026 标准 | 攻击率 40%→80% | trust_level + never_store |

### 论文更新指南

1. 评估可信度（机构/评审/数据量/时间/可复现）
2. 对照本文档的具体章节
3. 如果更优则更新对应章节，标注变更原因 + 日期 + 论文来源

---

## 第五部分：记忆分类标准

### 类型定义

| 类型 | 说明 | 生命周期 | 冲突处理 |
|------|------|---------|---------|
| preference | 用户偏好 | 永久(可更新) | 保留最新 |
| fact | 用户事实 | 永久(可更新) | 验证来源 |
| procedure | 操作命令/SOP | 半衰期 90d | 保留最新版 |
| lesson | 教训/经验 | 永久 | 不覆盖 |
| decision | 决策及原因 | 永久 | 不覆盖 |
| task_log | 任务记录 | 半衰期 30d | 不去重 |
| knowledge | 巩固产出 | 永久 | 合并最新 |

### 分类陷阱

| 用户说的 | 正确类型 | 常见误判 |
|---------|---------|---------|
| "写文案主题是独居上海" | task（不是 fact） | 误判为 user_fact |
| "这次用简约" | transient（本次参数） | 误判为 preference |
| "以后都用简约" | preference | 正确 |
| 群里其他人说的 | 不是用户的 fact | 误判为 user_fact |
| AI 生成的文案 | 不存 | 误判为某类型 |

---

## 第六部分：来源追踪（Provenance）

每条记忆的 metadata 字段：

| 字段 | 值范围 | 说明 |
|------|--------|------|
| scope | global/group:oc_xxx/dm/agent:xxx/unscoped | 作用域 |
| source | user_direct/group_chat/web_scrape/agent_output/migration/consolidation | 来源 |
| trust | high/medium/low | 信任度 |
| mem_type | preference/fact/procedure/lesson/decision/task_log/knowledge | 类型 |
| agent | main/writer/creator/... | 写入者 |
| context | 当前对话场景描述 | 上下文 |
| access_count | 整数 | 被检索次数（异步更新） |
| archived | bool | 软删除标记 |
| embedding_model | gemini-embedding-001 | 嵌入模型版本 |
| schema_version | 1 | metadata 版本 |

### never_store 安全规则

正则检测，命中则拒绝写入：
- `sk-[A-Za-z0-9]{20,}` (API key)
- `password\s*[:=]\s*\S+`
- `token\s*[:=]\s*\S+`
- `cookie\s*[:=]\s*\S+`
- `-----BEGIN\s+(RSA\s+)?PRIVATE` (PEM key)

---

## 第七部分：选择性遗忘

### 衰减公式

```
I(t) = importance × exp(-λ × age_days / divisor)
divisor = 1 + min(log(1 + access_count), 3.0)
λ = ln(2) / half_life_days
```

- task_log: half_life = 30d
- procedure: half_life = 90d
- fact/preference/lesson/decision/knowledge: 不衰减
- access_count >= 20 后保护效果封顶（divisor 最大 4.0）
- importance < 0.10 → 标记 archived

---

## 第八部分：维护 SOP

### 每日 03:00（cron 自动）

| 步骤 | 操作 | LLM |
|------|------|-----|
| 1 | Opus re-add（补全 entity extraction） | Opus |
| 2 | 自动去重 >= 0.92 | 无 |
| 3 | 候选去重 0.85-0.92（LLM 判断） | Opus |
| 4 | unscoped 二次归类 | Opus |
| 5 | 生成报告 → 发飞书 | 无 |

所有维护操作 scope-aware：只在同一 scope 内执行，不跨 scope。

### 每周日 03:00（在 daily 基础上追加）

| 追加步骤 | 操作 | LLM |
|---------|------|-----|
| 6 | 冲突检测 + 解决 | Opus |
| 7 | 巩固（task_log → knowledge 摘要） | Opus |
| 8 | 衰减 + 低分归档 | 无 |
| 9 | 时间线摘要 | Opus |

### 手动触发

飞书对话：跟 Main 说"跑一下维护"或"看一下记忆状态"

### 备份

- 每日 02:30 Qdrant snapshot（cron 自动，保留 7 天）
- 路径：`~/.mem0-gateway/mem0/backups/`

---

## 第九部分：故障排查

| 症状 | 可能原因 | 诊断 | 解法 |
|------|---------|------|------|
| 搜索返回空 | scope 不对 / embedding API 超时 | 检查 scope 参数；`mem0_status` | 确认 scope；检查 VPN |
| 写入失败 | scope 为空 / never_store 拦截 | 看 MCP 返回的 error | 传 scope；不存密码 |
| MCP 连接超时 | NO_PROXY 未设置 | 检查环境变量 | 加 `NO_PROXY=localhost,127.0.0.1` |
| Qdrant 不可达 | Server 宕机 | `curl localhost:6333` | `launchctl kickstart` |
| 去重漏了 | 阈值太高 | 检查相似度分布 | 调 dedup_auto_threshold |
| Gateway crash loop | config.json 有无效 key | `config validate` | 删无效 key |
| 记忆泄漏（跨群） | scope 过滤失败 | 跑隔离测试 | 检查 scope 字段 |
| args 参数不传 | 用了 params/arguments 而非 args | 检查 MCP 调用格式 | 改为 `args={...}` |

---

## 附录

### A. 文件清单

```
~/.mem0-gateway/extensions/mem0-mcp/
  server.py          # MCP Server v3 (FastMCP)
  server.py.bak      # 旧版备份
  config.yaml        # 权限/衰减/维护配置
  migrate.py         # 迁移脚本
  maintenance.py     # 维护脚本
  engines/
    __init__.py
    decay.py         # 衰减引擎
    classifier.py    # 分类器
    consolidation.py # 巩固引擎
    conflict.py      # 冲突检测

~/.mem0-gateway/qdrant/
  qdrant             # 二进制
  config.yaml        # Qdrant 配置

~/.mem0-gateway/mem0/
  qdrant_server_data/ # Qdrant 数据
  backups/            # 每日快照
  maintenance_plans/  # 维护计划
  maintenance_reports/# 维护报告
  write_queue.jsonl   # 降级写入队列

~/.mem0-gateway/scripts/
  run-maintenance.sh  # 维护 wrapper
  mem0-backup.sh      # 备份脚本
```

### B. 关键配置

Embedding: `gemini-embedding-001` (3072 dims, MTEB #1)
- 主通道：Google 直连（需 VPN）
- 备选：lingyun 代理（无需 VPN，按量付费）

LLM:
- 日常 add: `infer=False`（不调 LLM）
- 每日/每周维护: Opus 4.6
- Fallback: lingyun-1/opus → lingyun-3/opus → gpt-5.4

### C. 变更日志

| 日期 | 变更 |
|------|------|
| 2026-03-14 | v3 上线：Mem0 + Qdrant Server + scope 隔离 + 认知引擎 |
| 2026-03-14 | 原生 memorySearch 关闭 |
| 2026-03-14 | monitor agent 删除（心跳堵塞 Main 队列） |
