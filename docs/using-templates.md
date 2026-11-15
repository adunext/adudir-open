# 在阿杜导演里用一个 .motion 模板

> 模板在阿杜导演里打开、修改、出片。本仓库的 [`templates/paper-perspective-talking-head/`](../templates/paper-perspective-talking-head/) 是一个模板的结构示例，用来对照 [motion-format.md](motion-format.md) 理解模板里有什么；它不含运行代码，出片由阿杜导演和 MotionGit 完成。

*English summary at the end.*

---

## 一、从打开到出片

1. **挑模板**：在阿杜导演的模板库里按类型（口播、Vlog、宣传片、知识……）挑一套，也可以在 [motiongit.com](https://motiongit.com) 上看模板的预览，或者直接打开一个 .motion 文件。打开就是新建一个工程，原模板不会被改。
2. **说清想法、交素材**：告诉阿杜这期想讲什么、给谁看、横屏还是竖屏，把口播视频、文稿或字幕、要用的图片和录屏交给它。已有的素材直接给，不用重复上传，也不用填技术表格。
3. **看方案**：阿杜先给出方案，不满意就直接说。
4. **阿杜动手**：按方案排画面、配声音、上字幕。
5. **一起修改**：说「开头再短一点」「这段换个样式」，或者自己动手：画面上直接改字，参数面板调颜色，拖一张图换掉样例图。哪一步不满意，就撤回哪一步。
6. **出片**：出片前会提醒还没换的样例图、放不下的文字；只是提醒，不拦着你。

---

## 二、模板里的哪些文件在起作用

| 文件 | 在阿杜导演里的作用 |
|---|---|
| `motion.json` | 认出这是一个模板，读出名字、版本、画幅和帧率 |
| `guide.json` | 交给阿杜的使用指南：需要哪些素材、适合什么内容、先对你说什么 |
| `params.schema.json` | 哪些内容可以改，每一项的类型和范围 |
| `presets/` | 示例参数，打开模板时用来展示效果 |
| `previews/` | 模板库里显示的封面 |
| `licenses/` | 模板和字体的许可 |

阿杜先读 `guide.json`，先理解你这期的内容和已有素材，再决定怎么用模板，不把示例内容当成你的内容。

---

## English summary

Templates are opened, edited and rendered in ADu Director. The folder
[`templates/paper-perspective-talking-head/`](../templates/paper-perspective-talking-head/) is a structure example to
read alongside [motion-format.md](motion-format.md); it holds no runtime code, and rendering is done in ADu Director and
MotionGit.

**Steps:** pick a template from the library (previews are also on [motiongit.com](https://motiongit.com)) or open a
.motion file, which creates a new project and leaves the template untouched; tell ADu what the video is about and hand
over narration, script or captions and media; review the plan; let ADu build it; revise by talking or by hand (edit
text on the canvas, tune parameters, drag in pictures, undo any single step); export, with sample media and clipped
text flagged as reminders, never blockers.

**Files that matter:** `motion.json` (identity, size, frame rate), `guide.json` (the guide ADu reads first),
`params.schema.json` (what can be changed), `presets/` (example parameters), `previews/` (covers), `licenses/`.
