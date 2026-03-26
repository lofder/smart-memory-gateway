# Engram — Architecture v2

> Scope-aware memory for multi-agent AI systems. Mem0 + Qdrant + MCP.
>
> 三个设计目标：**最大化模型自主能力** / **减少 token** / **真正维持长久记忆**

---

## 核心架构

```
                    ┌──────────────────────────────┐
                    │     Agent Layer (L1)          │
                    │  Main / Workers / DevOps      │
                    │  会话上下文 ≈ 5min TTL         │
                    └──────────┬───────────────────┘
                               │ MCP (stdio)
                    ┌──────────▼───────────────────┐
                    │       Engram (L2)             │
                    │                               │
                    │  5 MCP Tools                  │
                    │  ┌─────────────────────────┐  │
                    │  │ mem0_add     (写入)      │  │
                    │  │ mem0_search  (双路检索)  │  │
                    │  │ mem0_get_all (全量列举)  │  │
                    │  │ mem0_status  (健康检查)  │  │
                    │  │ mem0_maintenance (报告)  │  │
                    │  └─────────────────────────┘  │
                    │                               │
                    │  Guards                       │
                    │  ├─ Permission (per-agent)    │
                    │  ├─ Never-Store (regex)       │
                    │  └─ Write Queue (degradation) │
                    └──────────┬───────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
     ┌──────────────┐  ┌────────────┐  ┌──────────────────┐
     │  Mem0 SDK    │  │  Qdrant    │  │  Maintenance CLI  │
     │  (向量写/搜) │  │  (scroll/  │  │  (cron 调度)      │
     │  infer=False │  │   payload) │  │                   │
     └──────────────┘  └────────────┘  │  Daily:           │
                                       │  ├─ Opus 重提取    │
                                       │  └─ 向量去重       │
                                       │                   │
                                       │  Weekly:          │
                                       │  ├─ 冲突检测       │
                                       │  ├─ 记忆巩固       │
                                       │  └─ Bjork 衰减     │
                                       └──────────────────────┘
                                                │
                                       ┌────────▼────────┐
                                       │  Cold Storage   │
                                       │  (L3)           │
                                       │  Qdrant 快照    │
                                       │  维护报告 JSON  │
                                       │  write_queue    │
                                       └─────────────────┘
```

---

## 目标 1：最大化模型自主能力

### 模型可以自主做的事

| 能力 | 工具 | 说明 |
|------|------|------|
| 主动记住 | `mem0_add` | 模型判断什么值得记，自主调用写入 |
| 按需回忆 | `mem0_search` | 模型在需要时主动检索相关记忆 |
| 自我审查 | `mem0_status` | 模型可以查看记忆健康状态、各 scope 统计 |
| 跨域引用 | `cross:` scope | 模型可以拉取其他群的记忆用于当前场景 |

### 权限分层保障自主但不越界

```
Main Agent     →  读全域 + 写 global/group/dm
Worker Agent   →  只写 agent:{self} + procedure/task_log
DevOps Agent   →  全权限（含迁移、维护）
Default        →  只读 global，不可写
```

- Main 像"总管"，可以跨 scope 搜索和注入
- Worker 像"专员"，在自己的命名空间里自主沉淀经验
- 模型**不需要人类干预**就能完成记忆的存取

### 白天快路径 / 夜间深处理

- 白天 `infer=False`：写入只做 embedding，不跑 LLM 提取，**不阻塞对话**
- 夜间 Opus 重提取：用更强的模型重新处理今天的记忆，提高结构化质量
- 模型感知不到维护——它只管用工具，后台自动优化记忆质量

---

## 目标 2：减少 Token

### 检索策略

| 机制 | 效果 |
|------|------|
| **双路合并** | scope 结果 + global 结果交错，一次检索覆盖局部和全局 |
| **trust 排序** | high > medium > low，确保有限 token 内信息质量最高 |
| **trust_min 过滤** | 丢掉低质量记忆，不浪费上下文 |
| **limit 截断** | 硬限制返回条数（默认 5） |
| **archived 过滤** | 已归档/已去重/已合并的不返回 |

### 记忆压缩

| 机制 | 效果 |
|------|------|
| **去重**（0.92 阈值） | 向量相似度高的记忆软合并，旧的标记 archived |
| **巩固**（task_log → knowledge） | 多条操作日志 → LLM 摘要成一条 knowledge |
| **衰减**（Bjork 模型） | 过期记忆自动归档，减少噪声 |

### Token 节省链路

```
原始：50 条 task_log（每条 200 token）= 10,000 token
  ↓ 去重（-30%）
  ↓ 巩固（10 条 → 1 条 knowledge）
  ↓ 衰减归档
检索时：返回 5 条 × 200 token = 1,000 token（节省 90%）
```

---

## 目标 3：真正维持长久记忆

### 分层生命周期

| 类型 | 衰减策略 | 预期寿命 |
|------|----------|----------|
| preference / fact | **永不衰减** | 永久 |
| lesson / decision | **永不衰减** | 永久 |
| knowledge（巩固产物）| **永不衰减** | 永久 |
| procedure | 90 天半衰期 | 数月 |
| task_log | 30 天半衰期 | 数周 |

- 用户画像（偏好、事实）一旦记住就不会忘
- 操作性记忆（task_log）随时间淡出，但在淡出前会被巩固成 knowledge
- knowledge 是"提纯后的长期记忆"，永不衰减

### 衰减公式（Bjork 增强）

```
effective_age = age_days / (1 + min(ln(1 + access_count), cap))
λ = ln(2) / half_life_days
importance = e^(-λ × effective_age)
```

- 被检索越多的记忆衰减越慢（access_count 抑制衰减）
- cap 防止极端值（默认 3.0）
- importance < 0.10 → 归档

### 持久化保障

| 层 | 机制 |
|----|------|
| 在线 | Qdrant 向量库持久化 |
| 降级 | write_queue.jsonl 离线排队 + 自动重放 |
| 备份 | 每日 Qdrant snapshot → 保留 7 天 |
| 冷存 | 维护报告 JSON + 维护计划 JSON |

### 防污染

| 机制 | 说明 |
|------|------|
| `never_store` | 正则拦截 API key、密码、token、私钥 |
| `trust` 分级 | 标记来源可信度，检索时过滤低信任 |
| 冲突检测 | 同 scope 内矛盾的 fact/preference 自动裁决 |
| scope 隔离 | 群 A 的记忆不会泄漏到群 B |

---

## 维护调度

| 任务 | 频率 | 内容 | 建议 cron |
|------|------|------|-----------|
| 备份 | 每日 | Qdrant snapshot | `15 2 * * *` |
| Daily | 每日 | Opus 重提取 + 向量去重 | `0 3 * * *` |
| Weekly | 每周日 | + 冲突检测 + 巩固 + 衰减 | `0 4 * * 0` |

---

## 已知问题（三方确认）

1. `mem0_maintenance` MCP 工具的 daily/weekly 为占位符，需通过 CLI 执行
2. `mem0_get_all` 缺少权限检查
3. 巩固分组用词桶启发式，非向量相似度
4. weekly 衰减用 dedup 后的旧快照，未在冲突/巩固后刷新
5. 分类器双层设计完整但维护管线未接入
6. ~~部署脚本路径与仓库路径不一致~~ ✅ 已修复

---

## 学术基础

| 论文 | 对应实现 |
|------|----------|
| Hindsight (2512.12818) | 7 种记忆类型分类 |
| MAPLE (2602.13258) | 白天快写 / 夜间深处理分离 |
| FadeMem (2601.18642) | 重要性衰减公式 |
| Bjork (1992) | access_count 抑制衰减 |
| OWASP ASI06 (2026) | trust + never_store 防投毒 |
| TierMem (2602.17913) | provenance 追踪减 token |
| Proactive Interference (2506.08184) | 去重压缩 |
