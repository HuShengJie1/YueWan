# 开发指南

## 环境要求

- Python 3.12 或 3.13；推荐使用 uv 管理虚拟环境。
- MySQL 8.0.16 或更高版本；使用 InnoDB 与 `utf8mb4`。
- Node.js 20 或更高版本及 npm。
- 微信开发者工具稳定版。

## 后端安装和运行

```bash
cd apps/backend
cp .env.example .env
uv sync --extra dev
uv run uvicorn app.main:app --reload
```

如果本机没有 Python 3.12，uv 会在允许联网时安装项目指定的 Python。也可以使用已有 Python 3.12：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
uvicorn app.main:app --reload
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/health
```

OpenAPI 文档位于 <http://127.0.0.1:8000/api/v1/docs>。

## MySQL 配置

本地创建数据库，开发账号的创建和授权方式随本机 MySQL 的认证方式调整：

```sql
CREATE DATABASE meetup_vote
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

复制 `.env.example` 后设置：

```dotenv
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=meetup_vote
DB_PASSWORD=<仅写入本地 .env 或云托管环境变量>
DB_NAME=meetup_vote
```

数据库账号密码只写入未跟踪的 `.env`，不要修改并提交 `.env.example`。应用使用 SQLAlchemy
`URL.create()` 生成连接 URL，因此密码中的 `@`、`/` 等字符无需手工百分号编码。应用启动和健康检查
不会主动连接数据库，第一次数据库操作或 Alembic upgrade 才需要可用的 MySQL。

初次准备好空库后，在启动 API 前执行：

```bash
cd apps/backend
uv run alembic upgrade head
uv run alembic current
```

连接池默认每个容器保留 3 个连接，并允许 2 个临时溢出连接。部署时需保证
`(DB_POOL_SIZE + DB_MAX_OVERFLOW) × 最大容器实例数` 明显低于数据库最大连接数；其他连接池参数见
`.env.example`。生产云托管只使用 MySQL 内网地址，并通过服务环境变量注入连接信息。

### 云托管部署检查

- `yuewan-api` 使用 `apps/backend` 作为构建目录、使用目录内的 `Dockerfile`，
  容器端口为 `8000`。云托管注入 `PORT` 后，镜像启动命令会自动使用它。
- 服务必须启用与 MySQL 一致的 VPC 和子网，`DB_HOST` 只填内网地址；
  生产数据库不开启外网地址。
- `DB_PASSWORD`、`WECHAT_APP_SECRET` 和 `JWT_SECRET` 只配置在云托管服务版本的
  环境变量中，不放入 Git、Dockerfile 或代码包。
- 首次部署时先不切换业务流量，暂时保持 1 个实例以便进入 WebShell，在 `/app`
  执行 `.venv/bin/alembic upgrade head` 和 `.venv/bin/alembic current`。确认为
  `20260815_0001 (head)` 后再做 API 冒烟测试和流量切换。

## 本地认证配置

微信登录端点需要在未跟踪的 `.env` 设置：

```dotenv
WECHAT_APP_ID=<小程序 AppID>
WECHAT_APP_SECRET=<小程序 AppSecret>
JWT_SECRET=<至少 32 字节的独立随机密钥>
JWT_ISSUER=meetup-vote-api
JWT_AUDIENCE=meetup-vote-miniprogram
ACCESS_TOKEN_TTL_SECONDS=7200
```

可使用 `openssl rand -hex 32` 为本地生成 JWT 密钥。JWT 密钥不得复用微信 AppSecret，二者都不得提交。未配置认证凭据时健康检查仍可用，但登录端点会返回 `50302`。

## 本地头像存储

默认 `AVATAR_STORAGE_BACKEND=local`，会把清洗后的头像写入被 Git 忽略的
`apps/backend/var/media/avatars/`，并由 FastAPI 在 `/media` 下提供访问。可在 `.env` 覆盖：

```dotenv
AVATAR_STORAGE_BACKEND=local
MEDIA_ROOT=var/media
MEDIA_URL_PATH=/media
MEDIA_PUBLIC_BASE_URL=http://127.0.0.1:8000/media
AVATAR_MAX_UPLOAD_BYTES=5242880
AVATAR_MAX_DIMENSION=512
AVATAR_MAX_SOURCE_PIXELS=20000000
AVATAR_JPEG_QUALITY=85
```

登录取得 access token 后，可以本地验证上传：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/users/me/avatar \
  -H 'Authorization: Bearer <access_token>' \
  -F 'file=@/absolute/path/avatar.png'
```

开发默认接受 JPEG、PNG、WebP 输入，单文件最大 5 MiB；输出统一为最长边不超过 512 px 的 JPEG。只有
继续使用 `local` 适配器做跨设备测试时，`MEDIA_PUBLIC_BASE_URL` 才需要指向手机可访问的地址，且
`MEDIA_ROOT` 必须位于持久化、可备份的磁盘。微信云托管生产环境使用下述 `cloudbase` 适配器。

微信云托管生产环境使用同一环境的对象存储，不开启服务公网访问。服务版本需要配置以下非秘密变量：

```dotenv
AVATAR_STORAGE_BACKEND=cloudbase
CLOUDBASE_ENV_ID=prod-d6guq5h1yaf1568bd
CLOUDBASE_STORAGE_PUBLIC_BASE_URL=https://7072-prod-d6guq5h1yaf1568bd-1465494842.tcb.qcloud.la
```

小程序校验 JPEG/PNG、文件大小和源像素；JPEG 会压缩到最长边 512 px。随后通过
`wx.cloud.uploadFile` 直接写入 `avatars/<user-id>/<timestamp>-<random>.jpg|png`，再通过
`callContainer` 提交 file ID。后端验证环境、当前用户目录和受管文件名后，自行拼接 CDN URL 并保存。
这条链路不需要 `X-CloudBase-*` 请求头、CloudBase API Key 或腾讯云 CAM 密钥。

对象存储保持“所有用户可读，仅创建者可读写”，使最终随机头像 URL 可由小程序直接显示；服务端始终拥有对象
引用验证权，但不会代表客户端读取或删除对象。小程序会在 API 失败时删除新对象，并在成功后尽力删除上一张
符合当前命名规则的头像。

## Alembic

MySQL 活动 migration 链位于 `alembic/mysql_versions/`，当前 head 为
`20260815_0001`，可从空 MySQL 直接建立全部 MVP schema。`alembic/versions/` 中的
`20260809_0001` 至 `20260810_0004` 是保留的 PostgreSQL 历史，不在 `alembic.ini`
的活动 `version_locations` 内，不会被应用到 MySQL。

在 `apps/backend` 中运行：

```bash
uv run alembic heads
uv run alembic revision --autogenerate -m "describe schema change"
uv run alembic upgrade head
uv run alembic check
uv run alembic downgrade -1
```

自动生成 migration 后必须人工审阅，并确认使用 MySQL 类型、约束和安全的 upgrade/downgrade。
旧 PostgreSQL 中如果已有业务数据，需要另外设计一次性导出、转换、校验和切换流程；
baseline 只建结构，不会自动复制旧库数据。

## 后端测试与 lint

```bash
cd apps/backend
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

健康测试不需要运行数据库。默认测试会跳过真实数据库的 Repository
集成测试。对一个已升级到 head 的独立 MySQL 测试库执行：

```bash
RUN_DATABASE_TESTS=1 uv run pytest \
  tests/test_user_repository_integration.py \
  tests/test_group_repository_integration.py \
  tests/test_hangout_repository_integration.py \
  tests/test_candidate_repository_integration.py \
  tests/test_vote_repository_integration.py \
  tests/test_event_repository_integration.py
```

这些测试使用外层事务或显式清理，不保留测试 User、Group、GroupMember、Hangout、Proposal、ProposalVote、TimeOption、TimeVote 或 Event。

## 小程序安装和检查

```bash
cd apps/miniprogram
npm install
npm run check
```

`npm run check` 依次运行 ESLint、TypeScript strict 类型检查和 Prettier 检查。业务请求必须通过 `miniprogram/services/`；开发模拟器默认 API 地址在 `miniprogram/constants/api.ts`。

## 微信开发者工具

1. 在开发者工具中导入 `apps/miniprogram`，不要只导入内部的 `miniprogram/`。
2. 初次安装依赖后选择“工具 → 构建 npm”，开发者工具会生成被 Git 忽略的 `miniprogram_npm/`。
3. 当前 `project.config.json` 使用开发者工具支持的 `touristappid` 测试方式，不伪造真实 AppID。
4. 获得真实 AppID 后，优先写入本机的 `project.private.config.json` 或由团队确认配置方式；不要提交秘密。
5. 本地 HTTP 和域名校验仅用于模拟器开发；真机和发布环境必须使用已备案并在微信后台配置的 HTTPS 域名。

当前阶段不要求 CLI 构建小程序，CI 只执行可靠的依赖安装、lint、格式和类型检查。
