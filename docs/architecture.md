# 架构说明

## 总体架构

仓库采用前后端分离的 Monorepo：微信原生小程序通过 REST API 访问 FastAPI；FastAPI 通过 SQLAlchemy 2.x 的异步会话访问 MySQL 8。API 统一使用 `/api/v1` 前缀。

```text
WeChat page/component
        ↓
frontend services/request
        ↓ HTTPS + JSON
FastAPI Router → Service → Repository → SQLAlchemy async → MySQL
                         ↘ Integration adapter → verified third party / media storage
```

## 后端职责

- `app/api/`：HTTP 参数、请求验证、响应和状态码；禁止承载业务流程。
- `app/services/`：业务规则与用例编排。
- `app/repositories/`：SQLAlchemy 查询和持久化。
- `app/models/`：ORM 模型。
- `app/schemas/`：Pydantic 请求、响应和共享 envelope。
- `app/db/`：Engine、Session、Base 和数据库生命周期。
- `app/core/`：配置、日志等横切能力。
- `app/integrations/`：微信、文件存储等外部能力适配器；业务层只依赖清晰的适配边界。

投票用例独立收敛在 `votes` Router、`VoteService` 和 `VoteRepository`。Router 只映射 HTTP 路径与 schema；Service 负责 active 成员、Hangout 状态、截止时间、跨 Hangout 作用域和事务编排；Repository 负责 MySQL upsert、时间票整体替换和批量聚合。开启投票仍属于 Hangout 用例，由 `HangoutService` 编排 `draft → voting`。

候选写入与开启投票按 active GroupMember、Hangout 的固定顺序获取排他行锁，以同一 Hangout 行作为并发边界。投票写入对当前成员关系加排他锁、对 Hangout 加共享行锁：同一成员的替换操作串行化，不同成员可并发投票，同时阻止后续 Hangout 状态变更跨过未完成的写票事务。

手动确认用例独立收敛在 `events` Router、`EventService` 和 `EventRepository`。投票结果只作为输入参考，Service 不计算获胜者；它校验确认者权限和 Proposal/TimeOption 的 Hangout 作用域，并从候选复制 Event 快照。Event 查询也先验证 active 成员和路径中的 Group/Hangout 作用域，不通过 Event 查询泄露资源存在性。

确认写入沿用 active GroupMember、Hangout 的固定锁顺序，并对 Hangout 获取排他锁。Event 创建、`Hangout.status=confirmed` 和 `confirmed_at` 在同一数据库事务中 flush/commit；Hangout 排他锁将不同确认请求串行化，`events.hangout_id` 唯一约束继续作为数据库兜底。确认会等待已取得 Hangout 共享锁的写票事务完成；确认提交后，后续写票重新校验状态并返回冲突。相同候选的重复确认返回既有 Event，不同候选返回安全冲突。

## 小程序职责

- `pages/`：页面与页面局部状态。
- `components/`：可复用 UI。
- `services/`：统一网络访问和按领域拆分的 API 调用。
- `stores/`：确有跨页面需求的全局状态。
- `types/`：共享领域及 API 类型。
- `constants/`：环境无关的常量和开发配置入口。
- `utils/`：不包含业务编排的小型工具。

页面不得直接调用 `wx.request` 或 `wx.uploadFile`。普通后端请求统一经过 `services/request.ts`；
云存储上传等领域编排放在对应的 `services/*.ts`（当前头像上传位于 `services/user.ts`）。

## 配置与启动

后端通过 `pydantic-settings` 读取环境变量和 `apps/backend/.env`。所有设置集中在
`app/core/config.py`。数据库连接使用 `DB_HOST`、`DB_PORT`、`DB_USER`、`DB_PASSWORD` 和
`DB_NAME` 等结构化配置，再通过 SQLAlchemy `URL.create()` 生成 `mysql+asyncmy` URL，避免要求
运维人员手工编码密码中的特殊字符。`.env.example` 只提供无秘密的开发模板，真实凭据不得提交。

Engine 在模块加载时创建，但不会在应用启动或健康检查时主动连接数据库；实际数据库操作或 migration
才建立连接。连接池启用 `pool_pre_ping`、定时回收和有界容量，事务隔离级别固定为
`READ COMMITTED`；每条新 MySQL 连接将会话时区设置为 UTC。

## 认证与微信登录

登录流：

```text
wx.login()
→ code
→ POST /api/v1/auth/wechat/login
→ 后端 WeChat integration 换取 openid / unionid
→ 查找或创建 User
→ 签发本系统 JWT access token
```

各层责任：

- `app/integrations/wechat/` 只通过微信官方 `code2Session` 换取身份，将微信错误映射为内部安全异常。
- `AuthService` 编排微信换码、User upsert、事务和 access token 签发。
- `UserRepository` 使用 `wechat_openid` 唯一约束、行锁和 savepoint 后重试保证并发首次登录的幂等性。
- `get_current_user` 校验 Bearer token，并重新读取 User 以确认账号仍存在且未禁用。
- `UserService` 在事务中完成当前用户昵称更新和资料完整状态切换。

JWT 固定使用 HS256，包含 `sub`、`iat`、`exp`、`iss`、`aud` 和 `type=access`；JWT 密钥与微信 AppSecret 分离。当前为无状态 access token，不实现 refresh token、注销黑名单或多设备会话管理。

`code2Session` 返回的 `session_key` 只在适配器内校验后丢弃，不入库、不写日志、不向小程序返回。临时 code、AppSecret、token 和微信身份标识也不得进入日志。

小程序端已建立显式首次登录、会话持久化、冷启动用户验证、Bearer Token 注入、统一 401 清理、资料完善、用户主动头像选择/上传和退出登录的前端边界。微信头像回调的本地临时路径只用于上传前预览，不得直接持久化。具体联调契约见 `docs/api-conventions.md`。

## 用户头像上传

生产头像上传流：

```text
wx.chooseAvatar
→ 小程序校验 JPEG/PNG、像素和大小，并压缩 JPEG
→ wx.cloud.uploadFile 写入 avatars/<当前用户 ID>/<随机文件名>.jpg|png
→ services/user.ts 通过 callContainer 提交 file_id + Bearer Token
→ Users Router 校验 JSON
→ CloudBaseAvatarReference 校验环境、当前用户目录和受管文件名
→ UserRepository 更新 avatar_url 并提交事务
→ 小程序在失败时删除新文件，成功后尽力清理上一张客户端头像
```

- Router 只负责认证、multipart 解析和限制读取长度；图片规则及事务补偿由 `AvatarService` 编排。
- 本地 `POST /users/me/avatar` 仍由 Router 有界读取 multipart、由后端重新解码和处理；生产
  `PUT /users/me/avatar` 只接收 CloudBase `file_id`，不读取对象内容。
- 生产小程序只接受 JPEG/PNG，检查最大 5 MiB 和 2000 万源像素；JPEG 最长边压缩到 512 px，PNG
  保持原文件。内容处理属于客户端体验与流量控制，不作为服务端安全边界。
- `CloudBaseAvatarReference` 只接受当前环境、当前 JWT 用户的 `avatars/<user-id>/` 目录，以及
  时间戳加随机串的 `.jpg`/`.png` 文件名；CDN URL 始终由后端配置拼接，不接受客户端 URL。
- 生产链路不使用 CloudBase 管理凭证或存储 OpenAPI。数据库更新失败时小程序删除新文件，成功后只清理
  同一用户目录下、符合当前命名规则的旧头像；更早的服务端头像可能保留为孤儿对象，后续可按前缀清理。
- 本地开发保留 `LocalAvatarStorage` 和 `/media`，由 `AVATAR_STORAGE_BACKEND=local` 选择；云托管设置为
  `cloudbase`，不依赖容器临时磁盘。

## 第三方链接规划（未实现）

Proposal 使用通用的 `external_platform`、`external_url`、`external_data` 表达来源。平台识别、分享文本解析、metadata 获取和小程序跳转能力应进入 `app/integrations/` 下的平台适配器。只有确认存在且获准使用的公开 API 才能接入；不编写爬虫，不逆向私有 API。
