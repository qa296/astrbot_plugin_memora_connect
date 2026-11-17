"""
记忆形成管线：组装 prompt → LLM 批量分析 → 解析重试 → 落库。

LLM 经 `ask` 回调注入，本模块与 astrbot 解耦。
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from ..domain.models import CATEGORIES, CATEGORY_NAMES, Memory, Session
from ..domain.scoring import build_analysis_prompt, parse_analysis
from ..storage.repository import MemoryRepository, new_id

logger = logging.getLogger("memora.formation")

# JSON "strength" 文案 → 显著度系数（memory.strength 回归本职，与好感度解耦）
_STRENGTH_MAP = {"max": 1.0, "high": 0.85, "normal": 0.65}

DEFAULT_CONFIDENCE = 0.8


def _clamp01(v, default: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return max(0.05, min(1.0, f))


class FormationService:
    def __init__(
        self,
        repo: MemoryRepository,
        ask: Callable[[str], Awaitable[str]],
        *,
        max_session_rounds: int = 5,
        recent_completed_count: int = 5,
        history_count: int = 24,
        persona_fn: Callable[[], str] | None = None,
    ) -> None:
        self.repo = repo
        self.ask = ask
        self.max_session_rounds = max(1, int(max_session_rounds))
        self.recent_completed_count = max(1, int(recent_completed_count))
        self.history_count = max(1, int(history_count))
        self.persona_fn = persona_fn

    async def flush_scope(self, scope_id: str, now: float) -> dict:
        """分析一个 scope 的缓冲并落库。返回统计供日志/指令展示。"""
        messages = self.repo.list_raw(scope_id, self.history_count)
        if not messages:
            return {"messages": 0}

        prompt = self._build_prompt(scope_id, messages)
        raw = await self._ask_with_retry(prompt)
        data = parse_analysis(raw)
        if data is None:
            logger.warning("形成分析解析失败（重试后仍失败），scope=%s", scope_id)
            return {"messages": len(messages), "error": "parse_failed"}

        stats = self._apply(data.get("sessions") or [], scope_id, now)
        stats["messages"] = len(messages)
        self.repo.clear_raw(scope_id)
        return stats

    def _build_prompt(self, scope_id: str, messages: list[dict]) -> str:
        known: dict[str, list[str]] = {}
        for elem in self.repo.list_elements(scope_id):
            known.setdefault(CATEGORY_NAMES.get(elem.category, elem.category), []).append(
                elem.name
            )
        active = [
            {"id": s.id, "topic": s.topic, "rounds": s.rounds, "summary": s.summary}
            for s in self.repo.list_sessions(scope_id)
            if s.status in ("ongoing", "open_question")
        ]
        completed = [
            s.summary
            for s in self.repo.list_sessions(
                scope_id, status="completed", limit=self.recent_completed_count
            )
            if s.summary
        ]
        persona_text = ""
        if self.persona_fn:
            try:
                persona_text = self.persona_fn() or ""
            except Exception:
                persona_text = ""
        return build_analysis_prompt(known, active, completed, messages, persona_text)

    async def _ask_with_retry(self, prompt: str) -> str:
        raw = await self.ask(prompt)
        if parse_analysis(raw) is None:
            raw = await self.ask(prompt)  # 解析失败重试 1 次
        return raw

    def _apply(self, sessions: list[dict], scope_id: str, now: float) -> dict:
        stats = {"sessions": 0, "memories": 0, "elements": 0, "relations": 0,
                 "impressions": 0}
        name_index = self._name_index(scope_id)
        for item in sessions:
            if not isinstance(item, dict):
                continue
            stats["sessions"] += 1
            self._apply_session(item, scope_id, now)
            # 先确保要素存在并刷新索引，记忆挂接与关系解析都依赖它
            elem_map = self._ensure_elements(
                item.get("elements") or [], scope_id, now
            )
            stats["elements"] += len(elem_map)
            name_index.update({n: e for n, (e, _role) in elem_map.items()})
            memory = self._apply_memory(item, scope_id, now)
            if memory is not None:
                stats["memories"] += 1
                for name, (elem_id, role) in elem_map.items():
                    self.repo.link_memory_element(memory.id, elem_id, role)
                for p in memory.participants:
                    if p in elem_map:
                        continue  # 已有语义角色，participant 仅作补充
                    elem_id = name_index.get(p)
                    if elem_id:
                        self.repo.link_memory_element(memory.id, elem_id, "participant")
            stats["relations"] += self._apply_relations(
                item.get("relations") or [], scope_id, now, name_index
            )
            if self._apply_impression(item.get("impression"), scope_id, now):
                stats["impressions"] += 1
        return stats

    def _name_index(self, scope_id: str) -> dict[str, str]:
        """scope 内 name → element_id 索引（relations 解析用）。"""
        return {e.name: e.id for e in self.repo.list_elements(scope_id)}

    def _apply_session(self, item: dict, scope_id: str, now: float) -> Session | None:
        sid = str(item.get("session_id") or "").strip()
        existing = self.repo.get_session(sid) if sid else None
        if existing is not None and existing.scope_id != scope_id:
            existing = None  # 跨 scope 的 id 视为无效
        if existing is not None and existing.status == "completed":
            existing = None  # 已完成会话按新会话处理

        status = str(item.get("status") or "ongoing").strip()
        if status not in ("ongoing", "completed", "open_question"):
            status = "ongoing"
        try:
            rounds = max(0, int(item.get("rounds") or 0))
        except (TypeError, ValueError):
            rounds = 0
        if status == "ongoing" and rounds >= self.max_session_rounds:
            status = "completed"  # 超过最大轮次强制完成

        if existing is not None:
            existing.topic = str(item.get("topic") or existing.topic)
            existing.status = status
            existing.rounds = rounds
            existing.summary = str(item.get("summary") or existing.summary)
            existing.emotion = str(item.get("emotion") or existing.emotion)
            kws = item.get("keywords")
            if isinstance(kws, list) and kws:
                existing.keywords = [str(k) for k in kws][:8]
            existing.updated_at = now
            self.repo.upsert_session(existing)
            return existing

        session = Session(
            id=new_id("s"),
            scope_id=scope_id,
            topic=str(item.get("topic") or ""),
            status=status,
            rounds=rounds,
            summary=str(item.get("summary") or ""),
            keywords=[str(k) for k in (item.get("keywords") or [])][:8],
            emotion=str(item.get("emotion") or ""),
            created_at=now,
            updated_at=now,
        )
        self.repo.upsert_session(session)
        return session

    def _apply_memory(self, item: dict, scope_id: str, now: float) -> Memory | None:
        """只有 completed 会话才生成记忆。"""
        if str(item.get("status") or "") != "completed":
            return None
        mem_data = item.get("memory")
        if not isinstance(mem_data, dict):
            return None
        content = str(mem_data.get("content") or "").strip()
        if not content:
            return None

        participants = [
            str(p).strip()
            for p in (mem_data.get("participants") or [])
            if str(p).strip()
        ]
        confidence = _clamp01(mem_data.get("confidence"), DEFAULT_CONFIDENCE)
        strength = _STRENGTH_MAP.get(str(mem_data.get("strength") or ""), confidence)
        memory = Memory(
            id=new_id("mem"),
            scope_id=scope_id,
            content=content,
            details=str(mem_data.get("details") or ""),
            emotion=str(mem_data.get("emotion") or ""),
            participants=participants,
            strength=strength,
            created_at=now,
            last_accessed=now,
        )
        self.repo.upsert_memory(memory)
        return memory

    def _ensure_elements(self, raw_elements: list, scope_id: str,
                         now: float) -> dict[str, tuple[str, str]]:
        """创建/复用本会话提到的要素；返回 name → (element_id, role)。"""
        elem_map: dict[str, tuple[str, str]] = {}
        for el in raw_elements:
            if not isinstance(el, dict):
                continue
            name = str(el.get("name") or "").strip()
            if not name or name in elem_map:
                continue
            category = str(el.get("category") or "trait").strip()
            if category not in CATEGORIES:
                category = "trait"
            elem = self.repo.get_or_create_element(scope_id, name, category, now)
            elem_map[name] = (elem.id, str(el.get("role") or ""))
        return elem_map

    def _apply_relations(self, raw_relations: list, scope_id: str, now: float,
                         name_index: dict[str, str]) -> int:
        """关系两端必须能在 scope 内解析到要素，否则丢弃（仅限已解析到的实体）。"""
        count = 0
        for rel in raw_relations:
            if not isinstance(rel, dict):
                continue
            src = name_index.get(str(rel.get("from") or "").strip())
            dst = name_index.get(str(rel.get("to") or "").strip())
            relation = str(rel.get("relation") or "").strip()
            if not src or not dst or src == dst or not relation:
                continue
            self.repo.upsert_connection(src, dst, relation, now)
            count += 1
        return count

    def _apply_impression(self, imp: object, scope_id: str, now: float) -> bool:
        if not isinstance(imp, dict):
            return False
        person = str(imp.get("person") or "").strip()
        if not person:
            return False
        try:
            delta = float(imp.get("score_delta") or 0.0)
        except (TypeError, ValueError):
            delta = 0.0
        delta = max(-0.5, min(0.5, delta))
        score = self.repo.adjust_impression(scope_id, person, delta, now)
        summary = str(imp.get("summary") or "").strip()
        if summary:
            self.repo.upsert_impression(scope_id, person, score, summary, now)
        return True