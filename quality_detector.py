"""AI 精剪 — 素材基本质量 / 清晰度 / 重复检测。

设计原则：纯逻辑层。读视频文件这件事在 ``services.video_quality_service``
里做（opencv），这里只负责把 ``VideoQualityReport`` + clip 元数据 →
用户可见的 ``QualityMark`` 列表，外加跨 clip 的重复素材检测。

四个维度：
  • black_frame      黑屏 / 曝光过低（开头结尾常见的死帧）
  • blurry           模糊 / 失焦（拉普拉斯方差过低）
  • static_frame     画面静止（连续相同帧 / 死帧）
  • duplicate_asset  同一 asset 的同一 trim 范围被多次拖到 timeline

三档敏感度对应不同的 ``QualityThresholds``。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from services.video_quality_service import (
    QualityThresholds,
    VideoQualityReport,
)

_logger = logging.getLogger(__name__)

QualityReason = Literal[
    "black_frame", "blurry", "static_frame", "duplicate_asset",
    # 纯 timeline 元数据维度(无需读源文件):
    "long_gap",       # 轨道上过长空白留白(节奏断裂)
    "flash_clip",     # 时长过短的碎片/闪帧(剪切残留)
    "isolated_clip",  # 叠加轨上远离同伴的孤立片段(常是误拖/忘删)
    # 节奏维度:
    "choppy_run",     # 连续 N+ 微切堆叠(机关枪剪)
    "marathon_clip",  # 远超中位时长的超长未切镜
    "track_overlap",  # 同轨片段意外重叠(拓扑异常)
]
Severity = Literal["low", "medium", "high"]
DetectionMode = Literal["aggressive", "temperate", "conservative"]
QualityAction = Literal["keep", "remove"]


@dataclass
class TimelineClipForQuality:
    """检测器需要的 clip 信息。media_path 缺失 → 跳过视觉检测。"""
    clip_id: str
    timeline_start_sec: float        # 在 timeline 上的起点
    duration_sec: float              # 在 timeline 上的时长（speed 归一后）
    asset_id: str | None             # 跨 clip 重复检测的 key
    trim_start_sec: float = 0.0      # 源文件起点
    trim_end_sec: float = 0.0        # 源文件尾部裁剪
    is_locked: bool = False
    has_audio_or_video: bool = True
    track_index: int = 0             # 所在轨(留白/孤立按轨判定)


@dataclass
class QualityMark:
    """一条质量问题/重复提示，前端按 schema 渲染建议层。"""
    id: str
    reason: QualityReason
    severity: Severity
    start_sec: float                 # timeline 绝对坐标
    end_sec: float
    description: str
    suggested_action: QualityAction = "remove"
    related_clip_ids: list[str] | None = None


# 三档敏感度 → 真实阈值。激进档更"挑剔"（更低的模糊容忍、更短的最小段
# 长度）；保守档只标显著问题。
_MODE_THRESHOLDS: dict[DetectionMode, QualityThresholds] = {
    "aggressive":   QualityThresholds(
        black_luminance_max=24.0,
        blur_laplacian_min=120.0,
        static_diff_max=2.0,
        min_segment_sec=0.25,
    ),
    "temperate":    QualityThresholds(
        black_luminance_max=16.0,
        blur_laplacian_min=80.0,
        static_diff_max=1.0,
        min_segment_sec=0.40,
    ),
    "conservative": QualityThresholds(
        black_luminance_max=10.0,
        blur_laplacian_min=40.0,
        static_diff_max=0.5,
        min_segment_sec=0.80,
    ),
}


def get_mode_thresholds(mode: DetectionMode) -> QualityThresholds:
    return _MODE_THRESHOLDS.get(mode, _MODE_THRESHOLDS["temperate"])


# 纯元数据维度的阈值(秒)。激进档更挑剔(更短的留白/更长的碎片就报)。
@dataclass
class MetadataThresholds:
    long_gap_sec: float       # 空白超过这个秒数 → long_gap
    flash_clip_sec: float     # 片段短于这个秒数 → flash_clip
    isolation_sec: float      # 到最近同轨片段距离超过 → isolated_clip


_METADATA_THRESHOLDS: dict[DetectionMode, MetadataThresholds] = {
    "aggressive":   MetadataThresholds(long_gap_sec=1.5, flash_clip_sec=0.50, isolation_sec=4.0),
    "temperate":    MetadataThresholds(long_gap_sec=2.5, flash_clip_sec=0.30, isolation_sec=6.0),
    "conservative": MetadataThresholds(long_gap_sec=4.0, flash_clip_sec=0.15, isolation_sec=10.0),
}


def get_metadata_thresholds(mode: DetectionMode) -> MetadataThresholds:
    return _METADATA_THRESHOLDS.get(mode, _METADATA_THRESHOLDS["temperate"])


# ── 1. video quality marks (per clip) ─────────────────────────────────


def report_to_marks(
    *,
    clip: TimelineClipForQuality,
    report: VideoQualityReport,
) -> list[QualityMark]:
    """单个 clip 的 ``VideoQualityReport`` → 一组 ``QualityMark``。

    报告里的区间是「相对 clip trim 后的时间」，要加上 clip 在 timeline
    上的 startTime 才是绝对坐标。
    """
    out: list[QualityMark] = []
    base = clip.timeline_start_sec

    for seg in report.black_segments:
        dur = seg.end_sec - seg.start_sec
        sev: Severity = _severity_from_score(seg.score, weight=1.2)
        out.append(QualityMark(
            id=f"black-{clip.clip_id}-{int(seg.start_sec * 1000)}",
            reason="black_frame",
            severity=sev,
            start_sec=base + seg.start_sec,
            end_sec=base + seg.end_sec,
            description=f"{dur:.1f}s 黑屏/曝光过低",
            suggested_action="remove",
            related_clip_ids=[clip.clip_id],
        ))

    for seg in report.blurry_segments:
        dur = seg.end_sec - seg.start_sec
        sev = _severity_from_score(seg.score, weight=0.8)
        out.append(QualityMark(
            id=f"blur-{clip.clip_id}-{int(seg.start_sec * 1000)}",
            reason="blurry",
            severity=sev,
            start_sec=base + seg.start_sec,
            end_sec=base + seg.end_sec,
            description=f"{dur:.1f}s 模糊/失焦",
            suggested_action="keep",  # 可能是艺术效果，让用户看一眼再决定
            related_clip_ids=[clip.clip_id],
        ))

    for seg in report.static_segments:
        dur = seg.end_sec - seg.start_sec
        sev = _severity_from_score(seg.score, weight=0.8)
        out.append(QualityMark(
            id=f"static-{clip.clip_id}-{int(seg.start_sec * 1000)}",
            reason="static_frame",
            severity=sev,
            start_sec=base + seg.start_sec,
            end_sec=base + seg.end_sec,
            description=f"{dur:.1f}s 画面静止",
            suggested_action="keep",  # 可能是刻意暂停
            related_clip_ids=[clip.clip_id],
        ))
    return out


def _severity_from_score(score: float, *, weight: float = 1.0) -> Severity:
    s = score * weight
    if s >= 0.7:
        return "high"
    if s >= 0.4:
        return "medium"
    return "low"


# ── 2. duplicate asset detection (cross clip, no media access) ────────


def detect_duplicate_assets(clips: list[TimelineClipForQuality]) -> list[QualityMark]:
    """同一 asset 的同一 trim 范围被多次拖到 timeline → 标记后者为重复。

    判定 key = (asset_id, round(trim_start_sec, 2), round(duration_sec, 2))
    —— round 到 0.01s 容忍前端浮点抖动。

    asset_id 缺失（importedUrl 临时素材）跳过 —— 没法可靠判定。
    """
    seen: dict[tuple[str, int, int], TimelineClipForQuality] = {}
    out: list[QualityMark] = []
    sorted_clips = sorted(clips, key=lambda c: c.timeline_start_sec)
    for c in sorted_clips:
        if c.is_locked or not c.has_audio_or_video or not c.asset_id:
            continue
        key = (
            c.asset_id,
            int(round(c.trim_start_sec * 100)),
            int(round(c.duration_sec * 100)),
        )
        first = seen.get(key)
        if first is None:
            seen[key] = c
            continue
        # 当前 clip 是 first 的副本
        out.append(QualityMark(
            id=f"dup-{c.clip_id}",
            reason="duplicate_asset",
            severity="medium",
            start_sec=c.timeline_start_sec,
            end_sec=c.timeline_start_sec + c.duration_sec,
            description=(
                f"重复素材 — 与 {first.timeline_start_sec:.1f}s 处的同名片段"
                f"同 asset、同 trim 范围"
            ),
            suggested_action="keep",  # 可能是刻意复用做切镜，默认让用户决定
            related_clip_ids=[c.clip_id, first.clip_id],
        ))
    return out


# ── 3. timeline 元数据维度(纯逻辑,零媒体访问)──────────────────────────


def _by_track(clips: list[TimelineClipForQuality]) -> dict[int, list[TimelineClipForQuality]]:
    out: dict[int, list[TimelineClipForQuality]] = {}
    for c in clips:
        out.setdefault(c.track_index, []).append(c)
    for arr in out.values():
        arr.sort(key=lambda c: c.timeline_start_sec)
    return out


def detect_long_gaps(
    clips: list[TimelineClipForQuality], *, min_gap_sec: float = 2.5,
) -> list[QualityMark]:
    """每条轨道上相邻片段间 > min_gap_sec 的空白留白 → long_gap 标记。

    诊断性质(非自动改):提示节奏断裂处,suggested_action='keep' 交用户决定
    是收紧还是有意留白。锁定轨跳过。"""
    out: list[QualityMark] = []
    for ti, arr in _by_track(clips).items():
        usable = [c for c in arr if not c.is_locked]
        for prev, cur in zip(usable, usable[1:]):
            prev_end = prev.timeline_start_sec + prev.duration_sec
            gap = cur.timeline_start_sec - prev_end
            if gap <= min_gap_sec:
                continue
            sev: Severity = (
                "high" if gap > min_gap_sec * 3
                else "medium" if gap > min_gap_sec * 1.8
                else "low"
            )
            out.append(QualityMark(
                id=f"gap-{ti}-{int(round(prev_end * 1000))}",
                reason="long_gap",
                severity=sev,
                start_sec=prev_end,
                end_sec=cur.timeline_start_sec,
                description=f"{gap:.1f}s 空白留白(轨 {ti + 1})",
                suggested_action="keep",
                related_clip_ids=[prev.clip_id, cur.clip_id],
            ))
    return out


def detect_flash_clips(
    clips: list[TimelineClipForQuality], *, max_clip_sec: float = 0.30,
) -> list[QualityMark]:
    """时长 < max_clip_sec 的碎片/闪帧(常是剪切残留,播放时一闪而过)→ flash_clip。

    suggested_action='remove'。锁定轨 / 非媒体 clip 跳过。"""
    out: list[QualityMark] = []
    for c in clips:
        if c.is_locked or not c.has_audio_or_video:
            continue
        if c.duration_sec >= max_clip_sec:
            continue
        sev: Severity = "high" if c.duration_sec < max_clip_sec * 0.5 else "medium"
        out.append(QualityMark(
            id=f"flash-{c.clip_id}",
            reason="flash_clip",
            severity=sev,
            start_sec=c.timeline_start_sec,
            end_sec=c.timeline_start_sec + c.duration_sec,
            description=f"{c.duration_sec:.2f}s 碎片/闪帧(剪切残留?)",
            suggested_action="remove",
            related_clip_ids=[c.clip_id],
        ))
    return out


def detect_isolated_clips(
    clips: list[TimelineClipForQuality], *,
    isolation_sec: float = 6.0,
    overlay_min_track: int = 1,
) -> list[QualityMark]:
    """叠加轨(track_index >= overlay_min_track)上、到最近同轨片段距离都
    > isolation_sec 的孤立片段(常是误拖/忘删)→ isolated_clip。

    只看叠加轨(主轨上片段间隔大很正常);该轨须 ≥2 片(单片轨不算"孤立于同伴")。
    severity low、suggested_action='keep'。锁定轨 / 非媒体跳过。"""
    out: list[QualityMark] = []
    for ti, arr in _by_track(clips).items():
        if ti < overlay_min_track:
            continue
        usable = [c for c in arr if not c.is_locked and c.has_audio_or_video]
        if len(usable) < 2:
            continue
        for i, c in enumerate(usable):
            prev_gap = (
                c.timeline_start_sec - (usable[i - 1].timeline_start_sec + usable[i - 1].duration_sec)
                if i > 0 else float("inf")
            )
            next_gap = (
                usable[i + 1].timeline_start_sec - (c.timeline_start_sec + c.duration_sec)
                if i + 1 < len(usable) else float("inf")
            )
            nearest = min(prev_gap, next_gap)
            if nearest <= isolation_sec:
                continue
            out.append(QualityMark(
                id=f"isolated-{c.clip_id}",
                reason="isolated_clip",
                severity="low",
                start_sec=c.timeline_start_sec,
                end_sec=c.timeline_start_sec + c.duration_sec,
                description=f"孤立片段(轨 {ti + 1},距最近片段 {nearest:.1f}s,可能误拖/忘删)",
                suggested_action="keep",
                related_clip_ids=[c.clip_id],
            ))
    return out
