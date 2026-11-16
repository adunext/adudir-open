# 辅助算法

仓库第一级的几个 `.py` 文件，是阿杜导演里一组小的辅助算法，从 2026 年 4 月起陆续写成，提交历史和时间都保留了。它们是纯函数：输入测量结果，输出判断或建议。它们依赖主程序里的其它模块，拿来读思路，不能单独运行。

| 文件 | 解决什么问题 |
|---|---|
| `bgm_format.py` | 判断一首音乐的格式能不能播放，自动配乐只会选到能用的曲子。 |
| `sfx_recommender.py` | 按动作描述（「门砰地关上」）给音效库里的音效打分推荐，不用大模型，几乎没有延迟。 |
| `quality_detector.py` | 找出素材里的黑屏、模糊、静止画面，以及被重复拖进来的同一段素材。 |
| `finishing_loudness.py` | 按音轨角色（对白、配音、配乐）定响度目标，算出增益，防止爆音。 |
| `finishing_neardup.py` | 找出画面几乎一样的不同片段（误拖两次的素材、反复用的空镜）。 |

`git log --follow -- <文件>` 可以看到每个算法是怎么一步步长出来的。

---

## English

The top-level `.py` files are a few small helper algorithms from ADu Director, written from April 2026 on with their
history kept. They are pure functions over measurements; they depend on the rest of the app and are meant to be read,
not run on their own: music format support (`bgm_format`), sound-effect matching (`sfx_recommender`), footage quality
checks (`quality_detector`), loudness targets (`finishing_loudness`) and near-duplicate shots (`finishing_neardup`).
