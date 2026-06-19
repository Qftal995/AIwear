# AIWear 3.0

虚拟试衣 AI 穿搭助手 — Spring Boot + Python Flask + LangGraph Agent + Vue 3 前端

## 项目结构

```
D:\Agent\
├── apps/
│   ├── ai-service/        # Python Flask + LangGraph Agent 主流程
│   │   ├── agent/          # LangGraph agents (wardrobe/stylist/visualizer/copywriter)
│   │   ├── tools/          # 内建工具 (image/wardrobe/rag)
│   │   ├── utils/          # MCP client / token counter / CLIP
│   │   ├── memory/         # 用户画像 / 衣橱 FAISS
│   │   ├── vector_store/   # FAISS 向量存储
│   │   ├── eval/           # 评测 runner / cases / reporter
│   │   └── server.py       # Flask 入口
│   ├── api-java/           # Spring Boot 3.2 网关 + 业务 API
│   │   └── src/            # Java 源码
│   └── web/                # Vue 3 + Vite + Element Plus 前端
│       └── src/            # 前端源码
├── deploy/
│   ├── docker-compose-mid.yml  # Docker 中间件 + AI 服务编排
│   ├── nginx/conf/             # Nginx 反向代理配置
│   ├── mysql/init/             # 数据库初始化 SQL
│   └── scripts/                # 启动脚本
├── data/                   # 运行时数据（uploads/、faiss_index/）
├── docs/openapi/           # API 文档
├── .env                    # 环境变量（不入库）
├── .env.example            # 环境变量模板
└── README.md
```

## 快速启动

### 1. 配置环境变量

```powershell
copy .env.example .env
# 编辑 .env 填入真实 API Key
```

### 2. Docker Compose（中间件 + AI 服务）

```powershell
.\deploy\scripts\start-all.ps1
```

### 3. 启动前端

```powershell
.\deploy\scripts\start-web.ps1
```

### 4. 启动 Java 后端

IntelliJ IDEA 打开 `apps/api-java`，运行 `BiteWearApplication.java`。

或安装 Maven 后：

```powershell
.\deploy\scripts\start-java.ps1
```

## 端口表

| 服务 | 端口 | 健康检查 | 说明 |
|------|------|----------|------|
| nginx | 80 | `nginx -t` | 前端静态文件 + 反向代理 |
| ai-service | 5001 (host) → 5000 (容器) | `GET /api/health` | LangGraph Agent 主流程 |
| Java 后端 | 8081 | `GET /api/health` | 网关 + 业务 API |
| 前端 (Vite) | 5173 | HTTP 200 | Vue 3 开发服务器 |
| MySQL | 3307 | `mysql SELECT 1` | 8.4.2 |
| Redis | 6379 | `redis-cli ping` | 7.0.15 |
| RabbitMQ | 5672 / 15672 | `check_port_connectivity` | 3.13-management |
| ai-worker | — | `exit 0` | Celery 异步任务 |

## API 总览

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| POST | `/api/chat` | DRAFT | Agent 对话 |
| GET | `/api/chat/stream` | DRAFT | SSE 流式对话 |
| POST | `/api/chat/resume` | DRAFT | HITL 续对话 |
| GET | `/api/health` | ✅ | ai-service 健康检查 |
| GET | `/api/mcp/status` | DRAFT | MCP Server 状态 |
| GET | `/api/mcp/tools` | DRAFT | MCP Tool 列表 |
| POST | `/api/mcp/test-call` | DRAFT | MCP Tool 测试调用 |
| POST | `/api/rag/search` | DRAFT | RAG 检索 |
| GET | `/api/traces/{sessionId}` | DRAFT | Trace 事件 |
| GET | `/api/session-stats` | ✅ | Token/Cost/Latency 统计 |
| POST | `/api/images/upload` | ✅ | 图片上传 |
| POST | `/api/images/audit` | ✅ | 图片审核 |
| GET | `/api/agent/wardrobe` | ✅ | 衣橱 CRUD |
| POST | `/api/agent/stats` | ✅ | Agent 统计 |

## 开发协作

并行 Agent 开发框架参见：

- [并行 Agent 开发路线](D:\obsidian\笔记\AIwear3.0\开发进度\AIWear3.0_并行Agent开发路线.md)
- [共享进度看板](D:\obsidian\笔记\AIwear3.0\开发进度\共享进度看板.md)
- [API 契约与跨 Agent 通信](D:\obsidian\笔记\AIwear3.0\开发进度\API契约与跨Agent通信.md)
- [Harness 工程规范](D:\obsidian\笔记\AIwear3.0\ClaudeCode_工程化与模块边界落地指南.md)

## 技术栈

| 层 | 技术 |
|----|------|
| Agent 框架 | LangGraph 1.2.5 + LangChain |
| LLM | DeepSeek Chat (planner) + Qwen VL Max (vision) |
| 向量检索 | FAISS + CLIP (图片) |
| 网关 | Spring Boot 3.2 + MyBatis-Plus |
| 鉴权 | JWT + BCrypt + Redis |
| 消息队列 | RabbitMQ |
| 前端 | Vue 3 + Vite 7 + Element Plus |
| 部署 | Docker Compose + Nginx |
