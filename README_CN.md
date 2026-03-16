# Smart Memory Gateway — 智能记忆网关

> 面向多 Agent AI 助手的 Scope 感知记忆架构，基于 Mem0 + Qdrant + MCP。

为 AI Agent 提供生产级的持久化结构化记忆，支持群聊隔离、来源追踪、神经科学启发的维护机制和可配置的访问控制。

## 核心特性

- **Scope 隔离** — 记忆按 `global`/`group`/`dm`/`agent` 命名空间隔离，群 A 的数据不会泄漏到群 B
- **双查询搜索** — 每次搜索自动合并全局上下文和当前 scope 的结果
- **结构化来源追踪** — 每条记忆附带 `source`、`trust`、`scope`、`mem_type`、`agent` 元数据
- **认知引擎** — 衰减（Bjork 间隔效应）、巩固、冲突检测、级联分类器
- **自动维护** — 每日 Opus 重提取 + 去重；每周巩固 + 冲突解决 + 衰减
- **凭证安全** — 正则检测阻止密码、API key、token 被存入记忆
- **优雅降级** — 3 级降级：Embedding API → Qdrant Server → MCP Server，含写入队列重放
- **配置驱动** — 所有权限、衰减参数、维护策略集中在一个 `config.yaml`
- **MCP 标准** — 作为 FastMCP Server 运行，兼容任何支持 MCP 的 AI 框架

## 快速开始

### 前置条件

- Python 3.11+
- Qdrant Server（[下载](https://github.com/qdrant/qdrant/releases)）
- Google API Key（用于 `gemini-embedding-001`）或 OpenAI 兼容的 embedding 服务

### 安装

```bash
pip install mem0ai qdrant-client mcp pyyaml
```

### 配置

```bash
cp config.example.yaml config.yaml
# 编辑 config.yaml：设置 API 密钥、Qdrant 地址、Agent 权限
```

### 运行

```bash
# 启动 Qdrant Server
./qdrant --config-path qdrant-config.yaml &

# 启动 MCP Server
python src/server.py
```

### 使用（从 AI Agent 调用）

```python
# 搜索记忆
mcp(action="call", server="mem0", tool="mem0_search",
    args={"query": "用户偏好", "scope": "group:oc_xxx", "limit": 5})

# 存储记忆
mcp(action="call", server="mem0", tool="mem0_add",
    args={"content": "用户喜欢简约风格", "scope": "global",
          "mem_type": "preference", "source": "user_direct", "trust": "high"})

# 健康检查
mcp(action="call", server="mem0", tool="mem0_status", args={})
```

## 文档

- [设计文档](docs/design_cn.md) — 完整 9 章系统设计
- [使用指南](docs/usage.md) — 如何集成到你的 AI Agent
- [开发指南](docs/development.md) — 如何扩展和贡献
- [配置参考](docs/configuration.md) — config.yaml 完整选项

## 许可证

MIT — 见 [LICENSE](LICENSE)
