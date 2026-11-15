"""
Phase 2 测试：domain.scoring 纯函数（term 抽取、FTS 子句、融合排序、
要素提及识别、分析 prompt/解析、注入文本拼装）。
"""

import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from conftest import load_plugin_modules  # noqa: E402

mods = load_plugin_modules(["domain.scoring", "domain.models"])
scoring = mods["memora.domain.scoring"]
models = mods["memora.domain.models"]


def _mem(mid, content, created_at=None, strength=1.0):
    now = time.time()
    return models.Memory(
        id=mid, scope_id="s", content=content,
        created_at=created_at if created_at is not None else now,
        last_accessed=now, strength=strength,
    )


class TestExtractTerms:
    def test_cjk_and_ascii(self):
        assert scoring.extract_terms("你好abc世界123") == ["你好", "abc", "世界", "123"]

    def test_long_cjk_chunked_by_12(self):
        terms = scoring.extract_terms("一二三四五六七八九十一二三四五六")
        assert terms == ["一二三四五六七八九十一二", "三四五六"]

    def test_empty(self):
        assert scoring.extract_terms("") == []
        assert scoring.extract_terms(None) == []


class TestFtsClause:
    def test_only_terms_len_ge_3(self):
        clause = scoring.fts_match_clause("吃火锅 看电影 啊 ab")
        # 2 字及以下的 term 不进 FTS（走 LIKE 兜底）；连续中文串不切分
        assert '"吃火锅"' in clause and '"看电影"' in clause
        assert '"啊"' not in clause and '"ab"' not in clause
        assert " OR " in clause

    def test_quote_escaping_and_cap(self):
        clause = scoring.fts_match_clause("火锅店")
        assert clause == '"火锅店"'
        many = scoring.fts_match_clause("火锅店 奶茶店 蛋糕店 图书馆 游乐园 便利店 玩具店")
        assert many.count(" OR ") == 5  # max_terms=6，取前 6 个 term

    def test_long_run_expands_to_grams(self):
        # 整句 query 展开为 3-gram OR 查询，任一 gram 命中即可召回
        terms = scoring.fts_terms("火锅店那次真开心")
        assert "火锅店" in terms and "真开心" in terms
        assert all(len(t) == 3 for t in terms)
        clause = scoring.fts_match_clause("火锅店那次真开心")
        assert clause.count(" OR ") == len(terms) - 1

    def test_short_terms_still_excluded(self):
        assert scoring.fts_terms("吃 火 a") == []
        assert scoring.fts_terms("ab cd") == []


class TestShortTerms:
    def test_filters(self):
        assert scoring.short_terms("ab 我 go 吃") == ["ab", "我", "go", "吃"]
        assert scoring.short_terms("火锅店") == []


class TestKwOverlap:
    def test_basic(self):
        assert scoring.kw_overlap(["火锅", "电影"], "吃了火锅没看电影") == 1.0
        assert scoring.kw_overlap(["火锅", "游戏"], "吃了火锅没看电影") == 0.5
        assert scoring.kw_overlap([], "任意") == 0.0


class TestRecency:
    def test_half_life_halving(self):
        now = time.time()
        assert scoring.recency_factor(now, now, 24) == 1.0
        # 半衰期 24h：24h 前 → 0.5
        assert math.isclose(
            scoring.recency_factor(now, now - 86400, 24), 0.5, rel_tol=1e-3
        )
        # floor：极旧记忆不会到 0
        assert scoring.recency_factor(now, now - 365 * 86400, 1) == 0.1


class TestFuseCandidates:
    def _cand(self, mid, kw=0.0, emb=0.0, graph=0.0, strength=1.0, created=None):
        return scoring.RecallCandidate(
            memory=_mem(mid, f"c{mid}", created_at=created, strength=strength),
            kw_score=kw, emb_score=emb, graph_score=graph,
        )

    def test_weight_normalization_and_order(self):
        now = time.time()
        cands = {
            "a": self._cand("a", kw=1.0),
            "b": self._cand("b", kw=0.5, emb=0.5),
        }
        out = scoring.fuse_candidates(cands, {"kw": 1.0, "emb": 1.0, "graph": 0.0},
                                      now, 24, 0.0, 5)
        # a: 1.0*0.5=0.5；b: 0.25+0.25=0.5 → 并列，但顺序稳定输出两条
        assert len(out) == 2
        assert all(math.isclose(c.adapter_score, 0.5) for c in out)

    def test_strength_and_recency_multiply(self):
        now = time.time()
        strong_new = self._cand("s", kw=1.0, strength=1.0, created=now - 3600)
        weak_old = self._cand("o", kw=1.0, strength=0.2, created=now - 86400 * 30)
        out = scoring.fuse_candidates(
            {"s": strong_new, "o": weak_old}, {"kw": 1.0}, now, 24, 0.0, 5
        )
        assert out[0].memory_id == "s"

    def test_threshold_and_limit(self):
        now = time.time()
        cands = {f"m{i}": self._cand(f"m{i}", kw=0.1 * (5 - i)) for i in range(6)}
        out = scoring.fuse_candidates(cands, {"kw": 1.0}, now, 2400, 0.3, 3)
        assert len(out) == 3
        assert all(c.adapter_score >= 0.3 for c in out)

    def test_zero_total_weights_fallback(self):
        now = time.time()
        out = scoring.fuse_candidates(
            {"a": self._cand("a", kw=1.0)}, {"kw": 0.0, "emb": 0.0, "graph": 0.0},
            now, 24, 0.0, 5,
        )
        # 权重全 0 时按 1 归一，不炸不出空
        assert len(out) == 1


class TestFindMentioned:
    def test_exact_and_partial(self):
        assert scoring.find_mentioned_elements(
            "我更喜欢小明了", [("e1", "小明"), ("e2", "火锅")]
        ) == ["e1"]
        # 3 字名称的 2-gram 简称命中
        assert scoring.find_mentioned_elements(
            "奥特曼打怪兽", [("e1", "奥特曼")]
        ) == ["e1"]

    def test_no_hit_and_short_name_skip(self):
        assert scoring.find_mentioned_elements("无关内容", [("e1", "小明")]) == []
        assert scoring.find_mentioned_elements("小明", [("e1", "明")]) == []


class TestParseAnalysis:
    def test_clean_and_wrapped(self):
        data = {"sessions": []}
        import json

        raw = json.dumps(data, ensure_ascii=False)
        assert scoring.parse_analysis(raw) == data
        assert scoring.parse_analysis(f"好的，如下：\n{raw}\n以上") == data

    def test_trailing_comma_and_invalid(self):
        raw = '{"sessions": [{"topic": "t",}]}'
        assert scoring.parse_analysis(raw)["sessions"][0]["topic"] == "t"
        assert scoring.parse_analysis("完全不是 JSON") is None
        assert scoring.parse_analysis("") is None


class TestPromptAndInjection:
    def test_prompt_contains_context(self):
        prompt = scoring.build_analysis_prompt(
            known_elements={"人物": ["张三"]},
            active_sessions=[{"id": "s1", "topic": "旅行", "rounds": 2, "summary": "计划中"}],
            completed_summaries=["上周聊了工作"],
            messages=[{"seq": 1, "sender_name": "张三", "sender_id": "u1", "content": "周末去爬山"}],
            persona_text="傲娇猫娘",
        )
        assert "傲娇猫娘" in prompt
        assert "张三" in prompt and "周末去爬山" in prompt
        assert "旅行" in prompt
        assert '"sessions"' in prompt

    def test_injection_blocks(self):
        cand = scoring.RecallCandidate(memory=_mem("m1", "一起吃火锅", created_at=time.time()))
        text = scoring.build_injection_text(
            [cand], "【人物印象】张三：靠谱", "旅行计划", "周末去哪？", "张三"
        )
        assert "【人物印象】" in text
        assert "【当前话题】旅行计划" in text
        assert "【待回应】周末去哪？" in text
        assert "【相关记忆】" in text
        # 发送者在 participants 中时带"我记得："前缀
        cand2 = scoring.RecallCandidate(
            memory=models.Memory(id="m2", scope_id="s", content="x",
                                 participants=["张三"], created_at=time.time())
        )
        text2 = scoring.build_injection_text([cand2], "", "", "", "张三")
        assert "我记得：" in text2

    def test_injection_caps_at_5(self):
        cands = [scoring.RecallCandidate(memory=_mem(f"m{i}", f"记忆{i}")) for i in range(8)]
        text = scoring.build_injection_text(cands, "", "", "", "")
        assert "记忆4" in text and "记忆5" not in text