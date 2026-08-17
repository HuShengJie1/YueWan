# 数据库规范

## 基础选择

- MySQL 8.0.16+ 是唯一业务数据库，表使用 InnoDB。
- 数据库和业务表使用 `utf8mb4` 与 `utf8mb4_0900_ai_ci`。
- SQLAlchemy 2.x async + asyncmy 负责访问，默认隔离级别为 `READ COMMITTED`。
- Schema 变更只通过 Alembic migration，不在模型导入或应用启动时自动建表。
- 连接信息从 `DB_HOST`、`DB_PORT`、`DB_USER`、`DB_PASSWORD` 和 `DB_NAME`
  读取，密码不得写入仓库。

## ID

公开业务实体继续使用应用生成的 **UUIDv4**，不暴露自增整数。MySQL 中通过
SQLAlchemy `Uuid(native_uuid=False)` 存为 `CHAR(32)`，API 仍使用标准带连字符 UUID
文本，因此对外契约不变。

UUIDv7 有更好的时间局部性，但 Python 3.12 标准库不原生生成；当前 MVP 数据量不值得
引入额外实现。若未来有可证实的索引写入瓶颈，再通过架构决策记录评估。

## 时间

- MySQL 时间列使用 `DATETIME(6)`，不依赖数据库会话时区做转换。
- 应用只接受带时区的 datetime，写入前转换为 UTC 并移除 tzinfo；读取时恢复为 UTC
  aware datetime。新连接同时执行 `SET SESSION time_zone='+00:00'`。
- API 返回带时区的 ISO 8601，例如 `2026-08-15T11:00:00Z`，前端再按用户时区显示。
- “周六晚上”可以是展示标签，但不能替代可计算的 datetime。
- 业务表通常包含 `created_at` 和 `updated_at`，默认保留 6 位微秒精度。

## 字符串、枚举与 JSON

- 文本列必须根据 API 契约设置明确长度，避免 MySQL 不允许无长度 `VARCHAR`的问题。
- `wechat_openid` 和 `wechat_unionid` 使用 `utf8mb4_0900_bin` 排序规则，确保身份比较区分大小写。
- 持久化枚举使用 `VARCHAR + CHECK`，不使用 MySQL 原生 ENUM，以便后续 migration
  清晰处理值集变化。
- `proposals.external_data` 使用 MySQL 原生 `JSON`。当前没有已确认的 JSON 查询路径，
  因此不建生成列或索引；出现稳定过滤需求后再通过 migration 添加。

## 软删除

当前不建立全局软删除基类。是否软删除按实体的产品语义决定：例如成员关系使用退出状态，
审计敏感记录可能需要保留；无保留需求的数据可硬删除。

## MVP 数据模型

| 表 | 作用 | 关键规则 |
| --- | --- | --- |
| `users` | 微信身份、账号状态和基础展示资料 | `wechat_openid` 唯一且非空；可选 `wechat_unionid` 也唯一 |
| `groups` | 朋友群组 | 记录创建者，名称不可为空白 |
| `group_members` | 用户与群组的成员关系 | `(group_id, user_id)` 唯一；角色为 `owner/member`；状态为 `active/left` |
| `hangouts` | 一次约玩决策 | 属于一个群组；状态为 `draft/voting/confirmed/cancelled/finished` |
| `proposals` | 候选活动或地点 | 属于 Hangout；外部来源使用通用平台、URL 和 JSON 元数据 |
| `proposal_votes` | 对活动候选的态度 | 每个用户对每个 Proposal 最多一票；取值为 `LIKE/OK/DISLIKE` |
| `time_options` | 明确的候选时间段 | 属于 Hangout；结束时间为空或晚于开始时间 |
| `time_votes` | 用户可用时间选择 | 每个用户对每个 TimeOption 最多选择一次，允许选择多个不同选项 |
| `events` | 确认后的正式活动 | 每个 Hangout 最多一个 Event；保存最终标题、地点和时间快照 |

`Event.proposal_id` 和 `Event.time_option_id` 保留最终结果对应的候选项引用，同时 Event
自身保存快照。候选项被删除时引用置空，快照仍保留。

### User 认证字段

- `wechat_openid`：当前小程序内的稳定登录身份，非空且唯一。
- `wechat_unionid`：小程序绑定微信开放平台时可能返回，可空且唯一。
- `is_active`：账号是否可登录；这是禁用状态，不表示软删除。
- `last_login_at`：最近一次成功微信身份换码的 UTC 时间。
- `profile_completed`：用户是否已明确保存昵称；新微信用户默认为 `false`。
- `display_name` / `avatar_url`：内部展示资料，API 将 `display_name` 映射为 `nickname`。

微信 `session_key` 不属于当前持久化模型，不入库、不记录日志。

## 完整性与索引

- 所有外键都由唯一约束、主键或显式索引以外键列作为最左列覆盖。
- 聚合内部数据使用级联删除；指向 User 的业务记录使用 `RESTRICT`。
- Hangout 跨状态列表使用 `(group_id, created_at, id)` 索引；按状态过滤使用
  `(group_id, status, created_at, id)`。候选列表索引同样包含稳定排序列及 UUID。
- 数据库约束负责唯一性、非空白文本和时间区间等局部不变量；跨表业务规则由
  Service 在事务中校验。

## Migration 规范

1. 先修改 SQLAlchemy metadata，再生成 Alembic revision。
2. 审阅自动生成内容、MySQL 类型、约束名称、索引、upgrade 和 downgrade。
3. migration 文件一旦进入共享分支，不改写历史；用新 migration 修正。
4. 数据迁移需考虑锁、回滚、校验和生产切换，不与结构 baseline 混为一步。
5. 提交前至少运行 `alembic heads` 和 `alembic check`；在独立测试库验证
   `alembic upgrade head`。

MySQL 活动 migration 目录为 `apps/backend/alembic/mysql_versions/`，当前 head 是
`20260815_0001`。`apps/backend/alembic/versions/` 保留旧 PostgreSQL migration 用于审计，
但不在 Alembic 活动 `version_locations` 内，不得对 MySQL 单独执行。

当前 baseline 只负责从空 MySQL 建立结构。如果旧 PostgreSQL 已有业务数据，必须另行实施
一次性导出、字段转换、行数/校验和切换，不能假定 baseline 会复制数据。
