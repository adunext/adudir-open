"""最后一公里 · 声音「统一响度(Loudness Match)」确定性核心。

配乐与声音收口:把各片段响度归一到统一目标 + 真峰限制防爆音。
实际响度测量是纯 DSP(ffmpeg loudnorm 双 pass measured_I,不挂 AI),本模块做
其上的**确定性决策**:按音轨角色选目标 LUFS、算增益、判真峰是否超限。

D2 机械闸门明确澄清:**按 clip 自身音轨角色分档是合法的**(对白 vs 配音 vs BGM 垫轨
用不同响度目标——对白 -18 / 配音 -16 / BGM -23 是 vlog 链路里的正确工程);
禁的只是按工程类型/内容来源/片长形态分叉。本模块只认 role 这个音轨事实。
"""

from __future__ import annotations

from typing import Literal, TypedDict

# 音轨角色 → 目标 LUFS(综合响度)。来自 vlog_render_rough_cut 实测分档。
TrackRole = Literal["dialogue", "dub", "bgm", "default"]

_TARGET_LUFS: dict[str, float] = {
    "dialogue": -18.0,
    "dub": -16.0,
    "bgm": -23.0,
    "default": -16.0,
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


def target_lufs_for_role(role: str) -> float:
    """按音轨角色取目标 LUFS;未知角色回退 default。"""
    return _TARGET_LUFS.get(role, _TARGET_LUFS["default"])


def plan_gain(
    measured_lufs: float,
    measured_true_peak_dbtp: float,
    role: str = "default",
) -> GainPlan:
    """给一条音轨算归一增益 + 真峰判定。纯确定性,无 AI。"""
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
    }
