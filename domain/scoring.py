"""
领域层打分与提示词纯函数。零 IO。

关键词检索免分词库：候选集由 FTS5 trigram（或 LIKE 降级）给出，
term 抽取是确定性的中文连续串 + ASCII 词切分。
"""

from __future__ import annotations

import json
import math
import re
import time
from dataclasses import dataclass

from .models import CATEGORY_NAMES

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]+|[a-zA-Z0-9_]+")


def extract_terms(text: str) -> list[str]:
    """把文本切成检索 term：连续中文串与 ASCII 词。

    中文串按 12 字符切片（子串匹配交给 trigram/LIKE），
    避免超长 phrase 与检索窗口错配。
    """
    terms: list[str] = []
    for raw in _TOKEN_RE.findall(text or ""):
        if re.fullmatch(r"[\u4e00-\u9fff]+", raw):
            terms.extend(raw[i : i + 12] for i in range(0, len(raw), 12))
        else:
            terms.append(raw)
    return [t for t in terms if t]


def fts_terms(query: str, max_terms: int = 6) -> list[str]:
    """FTS 检索 term：≥3 字的 term 展开为 3-gram 滑窗（免分词库的轻量方案）。

    trigram 分词器按 3 字窗口建索引，整句 phrase 难以命中；
    展开成 3-gram OR 查询后，任一 gram 命中即可召回。长串步长取 2 控制数量。
    """
    out: list[str] = []
    for raw in _TOKEN_RE.findall(query or ""):
        if len(raw) < 3:
            continue
        if len(raw) == 3:
            out.append(raw)
        else:
            grams = [raw[i : i + 3] for i in range(len(raw) - 2)]
            if len(grams) > 6:
                grams = grams[::2]
            for g in grams:
                if g not in out:
                    out.append(g)
        if len(out) >= max_terms:
            break
    return out[:max_terms]


def fts_match_clause(query: str, max_terms: int = 6) -> str:
    """为 FTS5 trigram 构造 OR 短语查询；过短 term 由调用方 LIKE 兜底。"""
    return " OR ".join(
        '"' + t.replace('"', '""') + '"' for t in fts_terms(query, max_terms)
    )


def short_terms(query: str) -> list[str]:
    """短于 3 字符、超出 trigram 窗口的 term，供 LIKE 兜底。"""
    return [t for t in extract_terms(query) if 0 < len(t) < 3]


def kw_overlap(terms: list[str], content: str) -> float:
    """query term 命中记忆内容比例（0~1）。"""
    if not terms:
        return 0.0
    hit = sum(1 for t in terms if t and t in content)
    return hit / len(terms)


def recency_factor(now: float, created_at: float, half_life_hours: float,
                   floor: float = 0.1) -> float:
    """exp(-Δt/half_life)，下限 floor（旧记忆权重保底趋近该值）。"""
    half = max(1.0, float(half_life_hours)) * 3600.0
    delta = max(0.0, now - created_at)
    return max(floor, math.exp(-(delta / half) * math.log(2)))


@dataclass
class RecallCandidate:
    """融合排序的候选：策略命中的记忆 + 各策略原始得分。"""

    memory: object  # domain.models.Memory
    kw_score: float = 0.0
    emb_score: float = 0.0
    graph_score: float = 0.0

    @property
    def memory_id(self) -> str:
        return self.memory.id


def fuse_candidates(
    candidates: dict[str, RecallCandidate],
    weights: dict[str, float],
    now: float,
    half_life_hours: float,
    threshold: float,
    limit: int = 5,
) -> list[RecallCandidate]:
    """加权融合 + recency/strength 乘性因子 + 阈值过滤 + 截断。

    权重自动归一化：仅统计启用策略的有效权重，防止配置和为 0 时全零。
    """
    if not candidates:
        return []
    weights_in = {
        "kw": float(weights.get("kw", 0.0)),
        "emb": float(weights.get("emb", 0.0)),
        "graph": float(weights.get("graph", 0.0)),
    }
    # 策略只要被任意候选命中就参与归一化（未命中的策略权重置 0）
    active_w = {
        key: w if any(getattr(c, f"{key}_score") > 0.0 for c in candidates.values()) else 0.0
        for key, w in weights_in.items()
    }
    total = sum(active_w.values())
    if total <= 0.0:
        total = 1.0
    kw_w, emb_w, graph_w = (active_w["kw"] / total, active_w["emb"] / total,
                            active_w["graph"] / total)

    scored: list[RecallCandidate] = []
    for cand in candidates.values():
        base = (kw_w * cand.kw_score + emb_w * cand.emb_score +
                graph_w * cand.graph_score)
        strength = max(0.05, min(1.0, float(getattr(cand.memory, "strength", 1.0) or 1.0)))
        score = base * recency_factor(now, cand.memory.created_at, half_life_hours) * strength
        if score >= threshold:
            cand.adapter_score = score  # type: ignore[attr-defined]
            scored.append(cand)
    scored.sort(key=lambda c: getattr(c, "adapter_score", 0.0), reverse=True)
    return scored[: max(0, limit)]


def find_mentioned_elements(
    query: str,
    element_names: list[tuple[str, str]],
) -> list[str]:
    """从 query 中找被提到的 element id。

    匹配规则：元素名作为子串出现在 query 中；或名称 ≥3 字时，
    名称的前两个 2-gram 窗口都在 query 中出现（名称被半简称时仍命中）。
    """
    q = query or ""
    q_compact = q.replace(" ", "")
    hits: list[str] = []
    for elem_id, name in element_names:
        n = (name or "").strip()
        if not n or len(n) < 2:
            continue
        n_compact = n.replace(" ", "")
        if n_compact in q_compact:
            hits.append(elem_id)
            continue
        if len(n_compact) >= 3 and all(
            n_compact[i : i + 2] in q_compact for i in range(2)
        ):
            hits.append(elem_id)
    return hits


def build_analysis_prompt(
    known_elements: dict[str, list[str]],
    active_sessions: list[dict],
    completed_summaries: list[str],
    messages: list[dict],
    persona_text: str,
) -> str:
    """构造记忆形成 LLM 的 prompt（JSON 输出契约见 formation.parse_analysis）。"""
    lines: list[str] = []
    lines.append(
        "你是记忆整理模块。阅读下面的新消息与已知上下文，整理话题会话并产出结构化记忆。"
    )
    if persona_text:
        lines.append(f"当前人格设定（用于语言风格和对“我”的行为理解）：{persona_text}")
    lines.append("已知要素（已存在的实体，优先复用同一名称，不要重复创建）：")
    for cat, names in known_elements.items():
        if names:
            lines.append(f"- {cat}: {', '.join(names[:40])}")
    if active_sessions:
        lines.append("进行中的会话：")
        for s in active_sessions:
            lines.append(
                f"- {s.get('id','')}: 话题「{s.get('topic','')}」（已 {s.get('rounds',0)} 轮）摘要：{s.get('summary','')}"
            )
    if completed_summaries:
        lines.append("最近已完成的会话摘要：")
        for s in completed_summaries[-5:]:
            lines.append(f"- {s}")
    lines.append("新消息（带索引）：")
    for m in messages:
        lines.append(f"[{m['seq']}] {m['sender_name']}({m['sender_id']}): {m['content']}")

    lines.append(
        """
输出：仅输出一个 JSON 对象，不要任何解释文字。JSON 格式：
{"sessions": [{
  "session_id": "沿用已有 id 或新建 s1",
  "topic": "话题简述",
  "status": "ongoing|completed",
  "new_message_indices": [上面消息的索引数字],
  "rounds": 本会话累计轮次(数字),
  "keywords": ["关键词"],
  "emotion": "情绪",
  "summary": "已完成会话才需要：一段摘要",
  "memory": {"confidence": 0-1, "strength": "high/normal/max",
             "details": "背景", "emotion": "情绪",
             "participants": ["人名"], "location": "地点",
             "tags": ["标签"], "content": "值得长期记住的内容",
             "user_opinion": "用户观点", "assistant_opinion": "助手观点"},
  "elements": [{"name": "实体名", "category": "person|object|place|action|trait",
                "role": "与记忆的角色关系"}],
  "relations": [{"from": "实体A", "to": "实体B", "relation": "关系短语"}],
  "impression": {"person": "人名", "summary": "对TA的新印象", "score_delta": -0.2~0.2}
}]}
规则：
- memory.content 必须是脱离当次对话也能看懂的一句话记忆。
- 只有 status=completed 的会话才生成 memory/summary。
- relations 只写你确认存在且值得记的关系；不要为了关联而编造。
- elements 的 category 从 person/object/place/action/trait 中选择。
"""
    )
    return "\n".join(lines)


def parse_analysis(raw: str) -> dict | None:
    """宽松解析 LLM 输出的 JSON（容忍前后缀/尾逗号），失败返回 None。"""
    if not raw:
        return None
    text = raw.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    candidate = text[start : end + 1]
    for attempt in (candidate, re.sub(r",\s*([}\]])", r"\1", candidate)):
        try:
            data = json.loads(attempt)
        except (TypeError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get("sessions"), list):
            return data
    return None


def build_injection_text(
    memories: list,
    impressions_summary: str,
    active_topics: str,
    open_questions: str,
    sender_name: str,
) -> str:
    """拼装注入块（【人物印象】/【当前话题】/【待回应】/【相关记忆】）。"""
    blocks: list[str] = []
    if impressions_summary:
        blocks.append(impressions_summary)
    if active_topics:
        blocks.append(f"【当前话题】{active_topics}")
    if open_questions:
        blocks.append(f"【待回应】{open_questions}")
    if memories:
        mem_lines = ["【相关记忆】"]
        for i, cand in enumerate(memories[:5], 1):
            mem = cand.memory if hasattr(cand, "memory") else cand
            time_str = ""
            ts = getattr(mem, "created_at", None)
            if ts:
                time_str = f"({time.strftime('%Y-%m-%d', time.localtime(ts))}) "
            content = getattr(mem, "content", "")
            participants = getattr(mem, "participants", []) or []
            if sender_name and sender_name in participants:
                mem_lines.append(f"{i}. {time_str}我记得：{content}")
            else:
                mem_lines.append(f"{i}. {time_str}{content}")
        blocks.append("\n".join(mem_lines))
    return "\n\n".join(blocks)


__all__ = [
    "RecallCandidate",
    "build_analysis_prompt",
    "build_injection_text",
    "extract_terms",
    "find_mentioned_elements",
    "fts_match_clause",
    "fts_terms",
    "fuse_candidates",
    "kw_overlap",
    "parse_analysis",
    "recency_factor",
    "short_terms",
]
