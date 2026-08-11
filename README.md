# 约玩 / MeetUp Vote

一个帮助朋友快速决定“谁参加、什么时候去、去哪里”的微信小程序。当前后端已实现微信登录、用户资料、群组与成员，以及约玩局的创建、读取、分页和草稿编辑基础闭环；候选活动、时间选项、投票、状态流转和正式活动仍待后续迭代。

## 技术栈

- 微信原生小程序 + TypeScript + TDesign Miniprogram
- FastAPI + SQLAlchemy 2.x async + Pydantic 2.x
- PostgreSQL + asyncpg + Alembic
- pytest、ruff、ESLint、Prettier 和 GitHub Actions

## 目录

```text
apps/miniprogram/   微信小程序
apps/backend/       REST API 与数据库基础设施
docs/               产品、架构、数据和开发文档
scripts/            后续可复用的项目脚本
.github/workflows/  基础 CI
```

## 环境要求

- Python 3.12+
- PostgreSQL 14+
- Node.js 20+
- 微信开发者工具

## 快速开始

后端：

```bash
cd apps/backend
cp .env.example .env
uv sync --extra dev
uv run uvicorn app.main:app --reload
```

打开 <http://127.0.0.1:8000/health> 验证服务。

小程序：

```bash
cd apps/miniprogram
npm install
```

然后用微信开发者工具导入 `apps/miniprogram`，执行“工具 → 构建 npm”。仓库使用开发者工具支持的 `touristappid` 测试配置，不包含真实 AppID。

完整说明见 [`docs/development.md`](docs/development.md)，文档索引见 [`docs/README.md`](docs/README.md)。
