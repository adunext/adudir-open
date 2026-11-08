"""SFX 关键词匹配推荐 — 简单 token 重合度评分，不调 LLM。

为什么不用 LLM：
  • SFX 匹配本质是"动作描述里的名词 → 库里 tag/title 命中"
  • 关键词匹配在中英文混合场景里都能跑（库里 tag 多用英文，title 中文）
  • 延迟近 0，LLM 调用反而是瓶颈

算法：
  1. 提取 query 里的有意义 token（去停用词，长度 ≥ 2）
  2. 对每个 catalog entry 算重合度：title + tags 都参与，tag 权重 ×2
  3. 同分按 duration 升序（短的优先，SFX 应该短促）
  4. 返回 top_k

接入点：
  • 剪辑器里任何"为某一段加音效"按钮
  • 输入 query 例："门砰地关上" / "玻璃碎了" / "scene change"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


# 简单的中英停用词集。query 通常是动作描述，去掉这些噪音 token 后剩下的就
# 是关键语义。中文按字符级别处理（jieba 是大依赖，简单场景不值得）。
_STOPWORDS_EN = frozenset({
    "the", "a", "an", "of", "to", "and", "or", "in", "on", "at", "for",
    "with", "from", "is", "are", "was", "were", "be", "been", "by", "as",
    "it", "this", "that", "his", "her", "him", "she", "he", "they", "them",
    "their", "we", "us", "you", "your", "my", "me", "i",
})

_STOPWORDS_ZH = frozenset({
    "的", "了", "在", "是", "和", "也", "都", "不", "就", "着", "把", "被",
    "让", "向", "向", "从", "到", "她", "他", "它", "你", "我", "我们",
    "你们", "他们", "这", "那", "这个", "那个", "这些", "那些",
})

# 中英文 token splitter — 英文按空格 / 标点，中文按字符
_TOKEN_RE = re.compile(r"[a-zA-Z]+|[一-鿿]+")


@dataclass
class SfxRecommendation:
    """单条 SFX 推荐 — entry + 匹配分 + 命中的 token。"""
    entry: Any                          # SfxLibraryEntry 鸭子类型；避免循环 import
    score: float                        # 0..1，越高越匹配
    matched_tokens: list[str]           # 命中的 token，给 UI 高亮 / 给用户看为什么推荐


def _tokenize(text: str) -> list[str]:
    """提取小写 token。中文整段保留（库里 tag 是英文，中文 query 走 title 匹配）。

    例：
      "门砰地关上" → ["门砰地关上"]（整段保留，由后续 substring 匹配处理）
      "Glass shatters loudly" → ["glass", "shatters", "loudly"]
      "door slam wood" → ["door", "slam", "wood"]
    """
    out: list[str] = []
    for match in _TOKEN_RE.finditer(text):
        tok = match.group(0).lower()
        # 太短的英文跳过 (a/i/ok 之类的)
        if len(tok) < 2 and not _is_chinese(tok):
            continue
        if tok in _STOPWORDS_EN or tok in _STOPWORDS_ZH:
            continue
        out.append(tok)
    return out


def _is_chinese(s: str) -> bool:
    return any("一" <= c <= "鿿" for c in s)


def _entry_match_score(
    entry: Any,
    query_tokens: list[str],
) -> tuple[float, list[str]]:
    """对单个 entry 算 query 匹配分。

    评分逻辑：
      • title 含完整 token：+1（每命中）
      • tag 完全相等：+2（tag 是结构化关键词，权重高）
      • category 命中：+1
      • title 的 substring 匹配中文 query：+1（中文 query 整段在 title 里出现）

    最终分数归一化到 0..1：score = hits / (query_tokens 长度 × 2)
    """
    title_lower = (
        (getattr(entry, "title", "") or "") + " " + (getattr(entry, "title_en", "") or "")
    ).lower()
    tags_lower = [t.lower() for t in (getattr(entry, "tags", []) or [])]
    category = (getattr(entry, "category", "") or "").lower()
    subcategory = (getattr(entry, "subcategory", "") or "").lower()
    # 内置库富标注：用途/描述作为弱信号（写的是画面里发生的事，如「卡片翻面」「数字跳动停下」）
    usage_lower = " ".join(
        [getattr(entry, "description", "") or ""] + list(getattr(entry, "use_for", []) or [])
    ).lower()

    hits = 0.0
    matched: list[str] = []

    for tok in query_tokens:
        # tag 完全等 — 最强信号
        if tok in tags_lower:
            hits += 2.0
            matched.append(tok)
            continue
        # 中文 query 部分匹配 tag — "门砰" 命中 tag "门" 或 "砰" 都算
        # （之前用户报"门砰" 0 结果就是因为 tag 是单字 "门"/"砰"，token 整段对不上）
        if _is_chinese(tok):
            chinese_tag_match = False
            for tag in tags_lower:
                if _is_chinese(tag) and (tag in tok or tok in tag):
                    hits += 2.0
                    matched.append(tag)
                    chinese_tag_match = True
                    break
            if chinese_tag_match:
                continue
        # category 命中 — 仅当 query 提到分类名（如 "whoosh"/"impact"）
        if tok == category or (subcategory and tok in subcategory):
            hits += 1.0
            matched.append(tok)
            continue
        # title 包含 — 中英文都走 substring 匹配
        if tok in title_lower:
            hits += 1.0
            matched.append(tok)
            continue
        # 用途/描述包含 — 中文 query 整段或其 2 字片段命中都算
        if usage_lower and (tok in usage_lower or (
            _is_chinese(tok) and len(tok) >= 4
            and sum(tok[i:i + 2] in usage_lower for i in range(len(tok) - 1)) >= max(2, (len(tok) - 1) // 2)
        )):
            hits += 0.75
            matched.append(tok)
            continue

    # 归一化：上限是"每个 query token 都拿到 tag 满分"
    max_score = max(1.0, len(query_tokens) * 2.0)
    return hits / max_score, matched


def recommend_sfx_by_query(
    query: str,
    catalog: list[Any],
    *,
    top_k: int = 5,
    category_filter: str | None = None,
) -> list[SfxRecommendation]:
    """SFX 推荐主入口。

    Args:
      query: 动作描述文本，例 "门砰地关上" 或 "glass break"
      catalog: SfxLibraryEntry 列表（来自 SfxLibraryService.list_entries()）
      top_k: 返回数量，默认 5
      category_filter: 限定 category（如 "impact" / "whoosh"），None 不限

    Returns:
      按分数降序的推荐列表。query 为空或无命中时返回空 list。
    """
    tokens = _tokenize(query)
    if not tokens:
        return []

    # 过滤 category（如果指定）
    candidates = [
        e for e in catalog
        if not category_filter or getattr(e, "category", "") == category_filter
    ]
    if not candidates:
        return []

    scored: list[SfxRecommendation] = []
    for entry in candidates:
        score, matched = _entry_match_score(entry, tokens)
        if score <= 0:
            continue
        scored.append(SfxRecommendation(
            entry=entry,
            score=score,
            matched_tokens=matched,
        ))

    # 按分数降序 → 同分先取标注质量高的（未评=0 排后）→ 再按时长升序（短的优先）
    scored.sort(
        key=lambda r: (
            -r.score,
            -(getattr(r.entry, "quality", 0) or 0),
            getattr(r.entry, "duration_sec", 0.0) or 999.0,
        ),
    )
    # 同组变体（内置库 family）先各出一条，名额不够再补其余变体，避免前几名全是同一声音的 _000/_001
    seen_family: set[str] = set()
    first: list[SfxRecommendation] = []
    rest: list[SfxRecommendation] = []
    for r in scored:
        fam = getattr(r.entry, "family", "") or ""
        if fam and fam in seen_family:
            rest.append(r)
            continue
        if fam:
            seen_family.add(fam)
        first.append(r)
    return (first + rest)[:top_k]


__all__ = ["SfxRecommendation", "recommend_sfx_by_query"]
