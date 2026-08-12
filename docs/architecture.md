# 架构说明

## 总体架构

仓库采用前后端分离的 Monorepo：微信原生小程序通过 REST API 访问 FastAPI；FastAPI 通过 SQLAlchemy 2.x 的异步会话访问 PostgreSQL。API 统一使用 `/api/v1` 前缀。

```text
WeChat page/component
        ↓
frontend services/request
        ↓ HTTPS + JSON
FastAPI Router → Service → Repository → SQLAlchemy async → PostgreSQL
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

## 小程序职责

- `pages/`：页面与页面局部状态。
- `components/`：可复用 UI。
- `services/`：统一网络访问和按领域拆分的 API 调用。
- `stores/`：确有跨页面需求的全局状态。
- `types/`：共享领域及 API 类型。
- `constants/`：环境无关的常量和开发配置入口。
- `utils/`：不包含业务编排的小型工具。

页面不得直接大量调用 `wx.request` 或 `wx.uploadFile`。当前 `services/request.ts` 是唯一的底层请求和文件上传入口；后续按 `auth.ts`、`user.ts`、`group.ts`、`hangout.ts`、`proposal.ts`、`vote.ts` 拆分领域调用。

## 配置与启动

后端通过 `pydantic-settings` 读取环境变量和 `apps/backend/.env`。所有设置集中在 `app/core/config.py`。`.env.example` 只提供无秘密的开发模板，真实凭据不得提交。

Engine 在模块加载时创建，但不会在应用启动或健康检查时主动连接 PostgreSQL；实际数据库操作或 migration 才建立连接。

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
- `UserRepository` 使用 `wechat_openid` 唯一约束和 PostgreSQL upsert 保证并发首次登录的幂等性。
- `get_current_user` 校验 Bearer token，并重新读取 User 以确认账号仍存在且未禁用。
- `UserService` 在事务中完成当前用户昵称更新和资料完整状态切换。

JWT 固定使用 HS256，包含 `sub`、`iat`、`exp`、`iss`、`aud` 和 `type=access`；JWT 密钥与微信 AppSecret 分离。当前为无状态 access token，不实现 refresh token、注销黑名单或多设备会话管理。

`code2Session` 返回的 `session_key` 只在适配器内校验后丢弃，不入库、不写日志、不向小程序返回。临时 code、AppSecret、token 和微信身份标识也不得进入日志。

小程序端已建立显式首次登录、会话持久化、冷启动用户验证、Bearer Token 注入、统一 401 清理、资料完善、用户主动头像选择/上传和退出登录的前端边界。微信头像回调的本地临时路径只用于上传前预览，不得直接持久化。具体联调契约见 `docs/api-conventions.md`。

## 用户头像上传

头像上传流：

```text
wx.chooseAvatar
→ services/user.ts 使用 Bearer Token 上传 multipart file
→ Users Router 有界读取文件
→ AvatarService 校验、纠正方向、缩放并重新编码
→ LocalAvatarStorage 原子写入新文件
→ UserRepository 更新 avatar_url 并提交事务
→ 成功后尽力清理旧的受管头像
```

- Router 只负责认证、multipart 解析和限制读取长度；图片规则及事务补偿由 `AvatarService` 编排。
- 图片内容会重新解码，JPEG、PNG、WebP 输入统一输出为最长边 512 px 的 JPEG；不会保留 EXIF 等客户端元数据，也不接受 SVG 或动画图片。
- MVP 使用 `app/integrations/storage/` 下的本地磁盘适配器，文件名由服务端随机生成，并通过只读 `/media` 路径提供访问。数据库提交失败时删除新文件，提交成功后再清理旧的受管文件，避免把 User 指向未提交或已删除的资源。
- 本地适配器要求可持久化、可备份的磁盘。多实例或无持久磁盘部署应替换为对象存储适配器和 HTTPS CDN 地址，不能依赖单实例本地目录。

## 第三方链接规划（未实现）

Proposal 使用通用的 `external_platform`、`external_url`、`external_data` 表达来源。平台识别、分享文本解析、metadata 获取和小程序跳转能力应进入 `app/integrations/` 下的平台适配器。只有确认存在且获准使用的公开 API 才能接入；不编写爬虫，不逆向私有 API。
