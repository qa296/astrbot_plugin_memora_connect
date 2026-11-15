"""
召回管线：关键词 / 图联想 / 语义向量三路并行 → 融合 → 注入文本。

本模块与 astrbot 解耦；embed_fn 由 adapter 注入。
"""

from __future__ import annotations

import logging

from ..domain.models import CATEGORY_NAMES
from ..domain.scoring import (
    RecallCandidate,
    build_injection_text,
    find_mentioned_elements,
    fts_match_clause,
    fts_terms,
    fuse_candidates,
    kw_overlap,
    short_terms,
)
from ..storage.repository import MemoryRepository

logger = logging.getLogger("memora.recall")

_GRAPH_DIRECT_SCORE = 1.0
_GRAPH_NEIGHBOR_SCORE = 0.5
_EMBED_SCAN_LIMIT = 1000


class RecallService:
    def __init__(
        self,
        repo: MemoryRepository,
        *,
        weights: dict[str, float] | None = None,
        threshold: float = 0.3,
        max_injected: int = 5,
        half_life_hours: float = 72.0,
        enable_embedding: bool = False,
        embed_fn=None,
    ) -> None:
        self.repo = repo
        self.weights = {
            "kw": float((weights or {}).get("kw", 0.2)),
            "emb": float((weights or {}).get("emb", 0.6)),
            "graph": float((weights or {}).get("graph", 0.2)),
        }
        self.threshold = float(threshold)
        self.max_injected = max(1, int(max_injected))
        self.half_life_hours = max(1.0, float(half_life_hours))
        self.enable_embedding = bool(enable_embedding) and embed_fn is not None
        self.embed_fn = embed_fn

    async def recall(self, scope_id: str, query: str, now: float) -> list:
        query = (query or "").strip()
        if not query:
            return []
        candidates: dict[str, RecallCandidate] = {}

        self._collect_keyword(scope_id, query, candidates)
        self._collect_graph(scope_id, query, candidates)
        await self._collect_embedding(scope_id, query, candidates)

        fused = fuse_candidates(
            candidates, self.weights, now, self.half_life_hours,
            self.threshold, self.max_injected,
        )
        for cand in fused:
            self.repo.touch_memory(cand.memory.id, now)
        return fused

    def _collect_keyword(self, scope_id: str, query: str,
                         candidates: dict[str, RecallCandidate]) -> None:
        ids: list[str] = []
        clause = fts_match_clause(query)
        if clause:
            ids.extend(self.repo.ids_from_fts(clause, scope_id))
        short = short_terms(query)
        for term in short:
            ids.extend(m.id for m in self.repo.search_memories_by_like(scope_id, term))
        if not ids:
            return
        seen: set[str] = set()
        unique_ids = [i for i in ids if not (i in seen or seen.add(i))][:50]
        # 打分与检索用同一组 gram term，确保 FTS 命中的候选得分有效
        terms = fts_terms(query) + short
        for memory in self.repo.get_memories_by_ids(unique_ids):
            score = kw_overlap(terms, f"{memory.content} {memory.details}")
            if score <= 0.0:
                continue
            cand = candidates.get(memory.id)
            if cand is None:
                cand = RecallCandidate(memory=memory)
                candidates[memory.id] = cand
            cand.kw_score = max(cand.kw_score, score)

    def _collect_graph(self, scope_id: str, query: str,
                       candidates: dict[str, RecallCandidate]) -> None:
        elements = self.repo.list_elements(scope_id)
        if not elements:
            return
        mentioned = find_mentioned_elements(
            query, [(e.id, e.name) for e in elements]
        )
        if not mentioned:
            return
        seeds = set(mentioned)
        neighbors = self.repo.neighbor_elements(seeds)

        scores: dict[str, float] = {}
        for elem_id in seeds:
            for memory in self.repo.get_element_memories(elem_id, limit=20):
                scores[memory.id] = max(scores.get(memory.id, 0.0), _GRAPH_DIRECT_SCORE)
        for elem_id in neighbors:
            for memory in self.repo.get_element_memories(elem_id, limit=20):
                scores[memory.id] = max(
                    scores.get(memory.id, 0.0), _GRAPH_NEIGHBOR_SCORE
                )
        if not scores:
            return
        memories = self.repo.get_memories_by_ids(list(scores))
        for memory in memories:
            cand = candidates.get(memory.id)
            if cand is None:
                cand = RecallCandidate(memory=memory)
                candidates[memory.id] = cand
            cand.graph_score = max(cand.graph_score, scores[memory.id])

    async def _collect_embedding(self, scope_id: str, query: str,
                                 candidates: dict[str, RecallCandidate]) -> None:
        if not self.enable_embedding:
            return
        try:
            qvec = await self.embed_fn(query)
        except Exception:
            logger.warning("embedding 计算失败，跳过语义召回", exc_info=True)
            return
        if not qvec:
            return
        import numpy as np

        q = np.asarray(qvec, dtype=np.float32)
        qnorm = float(np.linalg.norm(q))
        if qnorm <= 0.0:
            return
        memories = self.repo.list_memories(scope_id, limit=_EMBED_SCAN_LIMIT)
        for memory in memories:
            if not memory.embedding:
                continue
            try:
                vec = np.frombuffer(memory.embedding, dtype=np.float32)
            except ValueError:
                continue
            denom = qnorm * float(np.linalg.norm(vec))
            if denom <= 0.0:
                continue
            cos = float(np.dot(q, vec) / denom)
            score = (cos + 1.0) / 2.0  # [-1,1] → [0,1]
            if score <= 0.0:
                continue
            cand = candidates.get(memory.id)
            if cand is None:
                cand = RecallCandidate(memory=memory)
                candidates[memory.id] = cand
            cand.emb_score = max(cand.emb_score, score)

    def impression_block(self, scope_id: str, top_n: int = 5) -> str:
        """【人物印象】块：name: summary (好感度: verbal)。"""
        from ..domain.models import score_verbal

        imps = self.repo.list_impressions(scope_id)[:top_n]
        if not imps:
            return ""
        lines = ["【人物印象】"]
        for imp in imps:
            summary = imp.summary or "暂无详细印象"
            lines.append(f"{imp.subject}: {summary} (好感度: {score_verbal(imp.score)})")
        return "\n".join(lines)

    async def build_injection(self, scope_id: str, query: str, sender_name: str,
                              now: float) -> str:
        fused = await self.recall(scope_id, query, now)
        ongoing = [
            s.topic for s in self.repo.list_sessions(scope_id, status="ongoing", limit=3)
            if s.topic
        ]
        open_qs = [
            s.topic for s in self.repo.list_sessions(
                scope_id, status="open_question", limit=3
            )
            if s.topic
        ]
        return build_injection_text(
            fused,
            self.impression_block(scope_id),
            "、".join(ongoing),
            "、".join(open_qs),
            sender_name,
        )