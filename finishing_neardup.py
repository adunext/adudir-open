"""最后一公里 · 「跨片段近重复检测(Near-Duplicate Clips)」确定性核心。

现状:dHash 视觉相似度只用在**单条视频内相邻帧**的"去无聊静态段"检测。本模块补的是另一根轴 —— **跨 clip**:把时间线上每个 clip
取一个代表帧 dHash,按 Hamming 距离聚类,找出"明明是两个不同 clipId、画面却近乎
一样"的重复镜头(误拖两次的素材、反复用的同一段空镜)。

纯确定性:输入 {clipId, dhash},输出近重复簇。Hamming = popcount(a ^ b)。
取帧/算 dHash 的重副作用在 route 层(复用既有 visual_similarity service),本模块
只做聚类决策,可无头单测。

聚类用并查集(union-find)做**传递闭包**:A≈B 且 B≈C 则 A/B/C 同簇,即便 A、C
本身距离略超阈值 —— 符合"同一镜头的渐变副本"直觉。簇内/簇间顺序按输入顺序稳定,
保证输出确定可断言。
"""

from __future__ import annotations

from typing import TypedDict


class ClipHash(TypedDict):
    clipId: str
    dhash: int


class DupCluster(TypedDict):
    clipIds: list[str]      # 同一近重复簇的 clip(按输入顺序),size ≥ 2
    size: int
    maxDistance: int        # 簇内任意两两 Hamming 的最大值(越小越像)


def hamming(a: int, b: int) -> int:
    """两个 dHash 的 Hamming 距离 = 异或后的 1 位数。0 = 完全相同。"""
    return (a ^ b).bit_count()


def cluster_near_duplicates(
    clips: list[ClipHash],
    max_distance: int = 5,
) -> list[DupCluster]:
    """按 dHash Hamming ≤ max_distance 把 clip 聚成近重复簇(传递闭包)。

    只返回 size ≥ 2 的簇(单独的 clip 不是"重复")。顺序稳定:簇按其首个成员的
    输入下标排序,簇内 clipId 保持输入顺序。
    """
    n = len(clips)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)  # 偏向小下标当根,顺序稳定

    for i in range(n):
        for j in range(i + 1, n):
            if hamming(clips[i]["dhash"], clips[j]["dhash"]) <= max_distance:
                union(i, j)

    # 按根聚合,根的出现顺序 = 首成员输入顺序
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    out: list[DupCluster] = []
    for root in sorted(groups.keys()):
        members = groups[root]
        if len(members) < 2:
            continue
        max_d = 0
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                d = hamming(clips[members[a]]["dhash"], clips[members[b]]["dhash"])
                max_d = max(max_d, d)
        out.append({
            "clipIds": [clips[m]["clipId"] for m in members],
            "size": len(members),
            "maxDistance": max_d,
        })
    return out
