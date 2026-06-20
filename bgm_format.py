"""BGM 格式支持判定(纯函数)。

修"音乐库里有格式不支持的音乐,自动配乐选到它就失败"的根因:
预览/合成只支持浏览器<audio> 能解的格式。本模块把
"某条 BGM 能不能用"判成确定性纯函数,供 recommend-bgm 过滤推荐 + 标记目录,
让自动配乐永远只落到能播的曲子上。

支持集 = 浏览器原生可播 ∩ 库允许上传的格式。其余(.aiff/.wma/.opus 裸流/
非 PCM 的 .wav 变体由扩展名无法判时保守按支持,真解码失败前端再降级)视为不支持。
"""

from __future__ import annotations

import os

# 浏览器<audio> 可靠可播、且库允许的扩展名。
SUPPORTED_BGM_EXTS: frozenset[str] = frozenset({".mp3", ".m4a", ".aac", ".ogg", ".wav"})

# 明确不被 <audio> 可靠支持的常见音频扩展名(用于给用户清晰提示)。
KNOWN_UNSUPPORTED_EXTS: frozenset[str] = frozenset({
    ".wma", ".aiff", ".aif", ".alac", ".ape", ".opus", ".amr", ".mid", ".midi",
})


def bgm_ext(filename: str = "", remote_url: str = "") -> str:
    """取一条 BGM 的小写扩展名:优先本地 filename,回退 remote_url 末段(去 query)。"""
    src = filename or remote_url.split("?")[0].split("#")[0]
    return os.path.splitext(src)[1].lower()


def is_supported_bgm(filename: str = "", remote_url: str = "") -> bool:
    """该 BGM 是否为可播放格式。

    判定:扩展名在支持集 → True;在已知不支持集 → False;
    既不在支持也不在已知不支持(扩展名缺失/陌生)→ 保守 True
    (避免误杀;真正解码失败由前端 onerror 降级处理)。
    """
    ext = bgm_ext(filename, remote_url)
    if ext in SUPPORTED_BGM_EXTS:
        return True
    if ext in KNOWN_UNSUPPORTED_EXTS:
        return False
    return True  # 未知/无扩展名:保守放行


def unsupported_reason(filename: str = "", remote_url: str = "") -> str:
    """不支持时给一句人话原因(供 UI 标注);支持则空串。"""
    if is_supported_bgm(filename, remote_url):
        return ""
    ext = bgm_ext(filename, remote_url) or "(无扩展名)"
    return f"格式 {ext} 不支持预览/合成,请换 mp3 / m4a / wav / ogg"
