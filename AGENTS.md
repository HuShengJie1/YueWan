# Codex Agent Guide

## 项目目标

「约玩 / MeetUp Vote」是帮助朋友确定参与者、活动地点和时间的微信小程序。本仓库当前是一个小型 MVP 的全栈 Monorepo，优先保持简单、清晰和可迭代。

## 技术栈

- 前端：微信原生小程序、TypeScript、TDesign Miniprogram、ESLint、Prettier
- 后端：Python 3.12+、FastAPI、SQLAlchemy 2.x（异步）、Pydantic 2.x、Alembic、pytest、ruff
- 数据库：MySQL 8 + asyncmy

## 开发原则

1. 修改代码前先阅读与任务相关的 `docs/` 文档。
2. 不要随意改变既有架构，也不要擅自增加大型依赖。
3. Router 只处理 HTTP；业务逻辑进入 Service；数据库访问进入 Repository。
4. 小程序页面不得散落 `wx.request`；所有后端请求统一经过 `services/`。
5. 数据库结构变更必须通过 Alembic migration。
6. 新增或修改 API 时同步维护 `docs/api-conventions.md` 及相关说明。
7. 新增核心数据结构时同步维护 `docs/database.md`。
8. 禁止向仓库写入 secrets、真实 AppID、密码或生产凭据。
9. 完成任务后运行相关测试、lint 和类型检查。
10. 不要顺手重构无关代码；修改范围尽可能聚焦当前任务。
11. 第三方平台代码集中到 `app/integrations/`，不得逆向私有 API。

## 文档导航

- 了解产品目标、MVP 边界和核心概念：`docs/product.md`
- 修改模块边界、认证、数据流或第三方集成：`docs/architecture.md`
- 修改模型、ID、时间、软删除或 migration：`docs/database.md`
- 新增接口、分页、错误码或认证 Header：`docs/api-conventions.md`
- 安装依赖、运行服务、测试、迁移或导入小程序：`docs/development.md`
