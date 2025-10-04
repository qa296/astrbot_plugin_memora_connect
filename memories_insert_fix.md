# 修复：memories 表插入占位符数量不匹配

出现报错：`12 values for 13 columns`，定位到在保存记忆时向 `memories` 表执行插入语句，列有 13 项，但 `VALUES` 仅提供了 12 个占位符，缺少 `group_id` 的占位符，导致运行时异常。

- 受影响位置：保存记忆的 SQL 插入（`INSERT OR REPLACE INTO memories (...) VALUES (...)`）
- 根因：`memories` 表包含 13 列（含 `group_id`），但插入语句仅 12 个 `?`
- 解决：在 `VALUES` 处补齐第 13 个 `?`，与列数一致

修复后的插入语句示例（关键点）：

```sql
INSERT OR REPLACE INTO memories (
    id, concept_id, content, details, participants, location,
    emotion, tags, created_at, last_accessed, access_count, strength, group_id
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
```

若代码结构不同（例如数据库写入逻辑不在 `main.py`），可在对应的持久化模块中针对 `memories` 表插入语句进行同样修复。该变更不影响表结构与数据约束，仅修复运行时的占位符数量。

建议：
- 运行一次保存流程，确认不再出现占位符数量错误
- 在 CI 或测试中加入一个覆盖 `memories` 表写入的用例，避免回归

PR 中将包含此说明，便于维护者定位并验证修复。