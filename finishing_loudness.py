"""最后一公里 · 声音「统一响度(Loudness Match)」确定性核心。

配乐与声音收口:把各片段响度归一到统一目标 + 真峰限制防爆音。
实际响度测量是纯 DSP(ffmpeg loudnorm 双 pass measured_I,不挂 AI),本模块做
其上的**确定性决策**:按音轨角色选目标 LUFS、算增益、判真峰是否超限。

D2 机械闸门明确澄清:**按 clip 自身音轨角色分档是合法的**(对白 vs 配音 vs BGM 垫轨
用不同响度目标——对白 -18 / 配音 -16 / BGM -23 是 vlog 链路里的正确工程);
禁的只是按工程类型/内容来源/片长形态分叉。本模块只认 role 这个音轨事实。
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

# 音轨角色 → 目标 LUFS(综合响度)。来自 vlog_render_rough_cut 实测分档。
TrackRole = Literal["dialogue", "dub", "bgm", "default"]

DynamicRangeFlag = Literal["ok", "too_wide", "too_compressed", "unknown"]

# 按 role 的健康 LRA(响度范围/动态范围,LU)窗口 [lo, hi]:
#   过大 = 忽大忽小(对白尤其忌);过小 = 过度压限/二压闷死、无呼吸。BGM 容忍更宽。
_LRA_WINDOW: dict[str, tuple[float, float]] = {
    "dialogue": (2.0, 9.0),
    "dub": (2.0, 8.0),
    "bgm": (3.0, 14.0),
    "default": (2.0, 11.0),
}

_TARGET_LUFS: dict[str, float] = {
    "dialogue": -18.0,
    "dub": -16.0,
    "bgm": -23.0,
    # 未知 role 回退档。原为 -16(=dub),会把身份不明的轨当配音处理、推得偏响,
    # 成片里最常见的"未标 role 的混合人声轨"被顶到 -16 反而盖过对白。改为
    # 更安全的对白档 -18:宁可略保守也不爆,符合"收尾不添乱"。
    "default": -18.0,
}

# 真峰上限(dBTP):超过则需限峰,防爆音。
TRUE_PEAK_CEILING_DBTP = -1.0


class GainPlan(TypedDict):
    role: str
    targetLufs: float
    measuredLufs: float
    gainDb: float           # 应施加的增益(目标 - 实测)
    truePeakAfterDbtp: float  # 施加增益后的预估真峰
    needsLimiting: bool      # 施加增益后是否超真峰上限 → 需限峰
    measuredLra: float | None   # 实测 LRA(动态范围),缺失=None
    dynamicRangeFlag: str       # ok / too_wide / too_compressed / unknown


def target_lufs_for_role(role: str) -> float:
    """按音轨角色取目标 LUFS;未知角色回退 default。"""
    return _TARGET_LUFS.get(role, _TARGET_LUFS["default"])


def classify_lra(measured_lra: float | None, role: str = "default") -> DynamicRangeFlag:
    """按 role 的健康窗口判动态范围:None→unknown,超上限→too_wide,低下限→too_compressed。"""
    if measured_lra is None:
        return "unknown"
    lo, hi = _LRA_WINDOW.get(role, _LRA_WINDOW["default"])
    if measured_lra > hi:
        return "too_wide"
    if measured_lra < lo:
        return "too_compressed"
    return "ok"


def plan_gain(
    measured_lufs: float,
    measured_true_peak_dbtp: float,
    role: str = "default",
    measured_lra: float | None = None,
) -> GainPlan:
    """给一条音轨算归一增益 + 真峰判定 + 动态范围(LRA)分类。纯确定性,无 AI。"""
    target = target_lufs_for_role(role)
    gain_db = target - measured_lufs
    tp_after = measured_true_peak_dbtp + gain_db
    return {
        "role": role,
        "targetLufs": target,
        "measuredLufs": measured_lufs,
        "gainDb": gain_db,
        "truePeakAfterDbtp": tp_after,
        "needsLimiting": tp_after > TRUE_PEAK_CEILING_DBTP + 1e-9,
        "measuredLra": measured_lra,
        "dynamicRangeFlag": classify_lra(measured_lra, role),
    }


class TrackLoudnessInput(TypedDict):
    """一条音轨的实测响度输入(由 ffmpeg loudnorm 测得,见
    services/loudness_measure_service)。"""
    trackIndex: int
    role: str
    measuredLufs: float
    measuredTruePeakDbtp: float
    measuredLra: NotRequired[float | None]


class TrackGainPlan(GainPlan):
    """plan_gain 结果 + 该计划属于哪条音轨。"""
    trackIndex: int


def plan_loudness_batch(tracks: list[TrackLoudnessInput]) -> list[TrackGainPlan]:
    """多轨统一响度:逐轨按 role 调 plan_gain,产出 per-track 增益计划。

    纯确定性、无 AI、无 IO —— 实测值由调用方(route)先用测量 service 拿好再传入,
    本函数只做"按 role 归一 + 真峰判定"的决策,便于单测锁住契约。
    """
    out: list[TrackGainPlan] = []
    for t in tracks:
        p = plan_gain(
            t["measuredLufs"],
            t["measuredTruePeakDbtp"],
            t.get("role", "default") or "default",
            t.get("measuredLra"),
        )
        out.append({**p, "trackIndex": t["trackIndex"]})
    return out
