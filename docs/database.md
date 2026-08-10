# 数据库规范

## 基础选择

- PostgreSQL 作为唯一业务数据库。
- SQLAlchemy 2.x async + asyncpg 负责访问。
- Schema 变更只通过 Alembic migration。
- 应用从 `DATABASE_URL` 读取连接地址，不在代码中保存密码。

## ID

公开业务实体使用 PostgreSQL 原生 `uuid` 列和 **UUIDv4**，不暴露自增整数。选择 UUIDv4 的理由是 Python 3.12 标准库和 SQLAlchemy/PostgreSQL 均原生支持，无需额外依赖或数据库扩展，最符合当前 MVP 的低维护目标。

UUIDv7 有更好的时间局部性，但 Python 3.12 标准库不原生生成；在当前数据规模下不值得引入第三方实现。若未来有可证实的索引写入瓶颈，再通过架构决策记录评估，不应静默更换 ID 类型。

## 时间

- 数据库时间列使用 PostgreSQL `timestamp with time zone`，应用写入 UTC。
- API 返回带时区的 ISO 8601，例如 `2026-08-15T11:00:00Z`。
- 前端按用户时区显示。
- “周六晚上”可以是展示标签，但不能替代可计算的 datetime。
- 业务表通常包含 `created_at` 和 `updated_at`；具体字段随模型 migration 明确。

## 软删除

当前不建立全局软删除基类。是否软删除按实体的产品语义决定：例如成员关系可使用退出状态，审计敏感记录可能需要保留；无保留需求的数据可硬删除。避免每张表机械加入 `deleted_at`。

## MVP 数据模型

首个业务 migration 建立以下表：

| 表 | 作用 | 关键规则 |
| --- | --- | --- |
| `users` | 微信身份、账号状态和基础展示资料 | `wechat_openid` 唯一且非空；可选 `wechat_unionid` 也唯一 |
| `groups` | 朋友群组 | 记录创建者，名称不可为空白 |
| `group_members` | 用户与群组的成员关系 | `(group_id, user_id)` 唯一；角色为 `owner/member`；状态为 `active/left` |
| `hangouts` | 一次约玩决策 | 属于一个群组；状态为 `draft/voting/confirmed/cancelled/finished` |
| `proposals` | 候选活动或地点 | 属于 Hangout；外部来源使用通用平台、URL 和 JSONB 元数据 |
| `proposal_votes` | 对活动候选的态度 | 每个用户对每个 Proposal 最多一票；取值为 `LIKE/OK/DISLIKE` |
| `time_options` | 明确的候选时间段 | 属于 Hangout；结束时间为空或晚于开始时间 |
| `time_votes` | 用户可用时间选择 | 每个用户对每个 TimeOption 最多选择一次，允许选择多个不同选项 |
| `events` | 确认后的正式活动 | 每个 Hangout 最多一个 Event；保存最终标题、地点和时间快照 |

`Event.proposal_id` 和 `Event.time_option_id` 保留最终结果对应的候选项引用，同时 Event 自身保存快照，避免候选内容变化影响已确认活动。候选项被删除时引用置空，快照仍保留。

### User 认证字段

- `wechat_openid`：当前小程序内的稳定登录身份，非空且唯一。
- `wechat_unionid`：小程序绑定微信开放平台时可能返回，可空且唯一。
- `is_active`：账号是否可登录；这是禁用状态，不表示软删除。
- `last_login_at`：最近一次成功微信身份换码的 UTC 时间。
- `profile_completed`：用户是否已明确保存昵称；新微信用户默认为 `false`。
- `display_name` / `avatar_url`：内部展示资料，API 将 `display_name` 映射为 `nickname`。`code2Session` 不提供这些信息，新用户先使用不对外暴露的中性占位值。
- `avatar_url` 只保存客户端可访问的头像 URL，不保存图片字节、临时文件路径或客户端原始文件名。头像文件生命周期由存储适配器和 `AvatarService` 管理；当前列已在初始 migration 中存在，因此新增上传接口不需要 schema migration。

微信 `session_key` 不属于当前持久化模型。若未来引入微信加密数据解密，需要单独设计短期密文存储和轮换策略，不应直接加入 User 响应。

## 完整性与索引

- 所有外键均由唯一约束、主键或显式索引以外键列作为最左列覆盖，支持关联查询和级联删除。
- 聚合内部数据使用级联删除，例如删除 Hangout 会删除其 Proposal、投票和时间选项；所有指向 User 的业务记录使用 `RESTRICT`，防止误删历史创建者或投票人。
- 群组 Hangout、候选活动和候选时间的列表索引包含稳定排序列及 UUID，可直接支持 `(created_at, id)` 或 `(starts_at, id)` 游标分页。
- `external_data` 使用 JSONB，但当前没有已确认的 JSON 查询路径，因此暂不建立 GIN 索引；出现稳定过滤需求后再通过新 migration 添加。
- 数据库约束负责唯一性、非空白文本和时间区间等局部不变量。用户是否为群组有效成员、Event 所选 Proposal/TimeOption 是否属于同一 Hangout 等跨表业务规则由 Service 在事务中校验。

## Migration 规范

1. 先修改 SQLAlchemy metadata，再生成 Alembic revision。
2. 审阅自动生成内容、约束名称、索引、upgrade 和 downgrade。
3. migration 文件一旦进入共享分支，不改写历史；用新 migration 修正。
4. 数据迁移需考虑锁、回滚和生产数据，不在模型导入时自动建表。
5. 提交前至少运行 `alembic heads`；需要数据库验证时再运行 `alembic upgrade head`。

当前 migration head 为 `20260809_0003`：`20260809_0001` 建立完整 MVP 业务 schema，`20260809_0002` 为 User 增加 `is_active` 和 `last_login_at`，`20260809_0003` 增加 `profile_completed`。升级到 `0003` 时已存在用户会标记为资料已完成，避免将旧用户重新导向资料页。
