# 文献处理 Agent

基于 React + FastAPI 的学术文献智能处理工具，支持：

- **摘要提炼** — 结构化提取研究背景、目的、方法、发现、创新点等
- **学术翻译** — 中英等多语言学术文献互译
- **润色优化** — 提升语法、用词与学术表达规范

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 19 + TypeScript + Vite + Tailwind CSS |
| 后端 | Python FastAPI + DeepSeek API |

## 快速开始

### 1. 配置 API Key

```bash
cd backend
copy .env.example .env
```

编辑 `backend/.env`，填入你的 DeepSeek API Key：

```env
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

### 2. 启动后端

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 http://localhost:5173

## 项目结构

```
Literature_Processing_Agnet/
├── backend/
│   ├── app/
│   │   ├── main.py       # API 路由
│   │   ├── llm.py        # LLM 调用
│   │   ├── prompts.py    # 提示词模板
│   │   └── config.py     # 配置
│   └── requirements.txt
└── frontend/
    └── src/
        ├── App.tsx
        ├── api/client.ts
        └── components/
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| POST | `/api/summarize` | 摘要提炼 |
| POST | `/api/translate` | 学术翻译 |
| POST | `/api/polish` | 润色优化 |

请求体示例：

```json
{
  "text": "文献内容...",
  "target_language": "中文"
}
```

## DeepSeek 模型

在 `.env` 中通过 `DEEPSEEK_MODEL` 切换模型：

- `deepseek-chat` — 通用对话（默认）
- `deepseek-reasoner` — 推理模型

## 部署到 Railway（无需 GitHub）

1. 安装 CLI 并登录：
   ```bash
   npm i -g @railway/cli
   railway login
   ```
2. 在项目根目录初始化并配置密钥：
   ```bash
   railway init
   railway variables set DEEPSEEK_API_KEY=sk-xxx
   railway variables set DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
   railway variables set DEEPSEEK_MODEL=deepseek-chat
   railway up
   railway domain
   ```
3. 浏览器打开生成的域名，访问 `/api/health` 确认 `api_configured` 为 `true`。
