"""
消息接收：过滤 → 写 raw 缓冲；按条数阈值或沉默超时提示触发 flush。
"""

from __future__ import annotations

import time


class IngestService:
    def __init__(
        self,
        repo,
        *,
        exclude_keywords: list[str] | None = None,
        flush_threshold: int = 20,
        idle_seconds: float = 60.0,
    ) -> None:
        self.repo = repo
        self.exclude_keywords = [k for k in (exclude_keywords or []) if k]
        self.flush_threshold = max(1, int(flush_threshold))
        self.idle_seconds = max(1.0, float(idle_seconds))
        # 内存态；重启后由下一条消息重建
        self._last_activity: dict[str, float] = {}

    def is_blocked(self, text: str) -> bool:
        """exclude_keywords 命中（子串匹配）则跳过记录。"""
        if not self.exclude_keywords:
            return False
        t = text or ""
        return any(k and k in t for k in self.exclude_keywords)

    def accept(
        self,
        scope_id: str,
        content: str,
        sender_id: str,
        sender_name: str,
        ts: float | None = None,
    ) -> bool:
        """写入环形缓冲；返回是否应立即触发 flush（达到条数阈值）。"""
        content = (content or "").strip()
        if not content:
            return False
        now = ts if ts is not None else time.time()
        self.repo.append_raw(scope_id, content, sender_id, sender_name, now)
        self._last_activity[scope_id] = now
        return self.repo.count_raw(scope_id) >= self.flush_threshold

    def pending_count(self, scope_id: str) -> int:
        return self.repo.count_raw(scope_id)

    def scopes_due_flush(self, now: float | None = None) -> list[str]:
        """沉默超时的 scope（有缓冲且距最后一条消息 ≥ idle_seconds）。"""
        now = now if now is not None else time.time()
        due: list[str] = []
        for scope, last_ts in list(self._last_activity.items()):
            if now - last_ts >= self.idle_seconds and self.repo.count_raw(scope) > 0:
                due.append(scope)
        return due

    def mark_flushed(self, scope_id: str, now: float | None = None) -> None:
        """flush 完成后由 formation 调用，避免空闲 sweeper 重复触发。"""
        self._last_activity[scope_id] = now if now is not None else time.time()