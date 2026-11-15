# 剪辑器怎样使用 .motion

剪辑器拿到一个 .motion 后，大致做四件事：

1. **打开**：读 `motion.json`，核对文件，把模板解到新的工作目录，新建一个工程。模板本身不改。
2. **预览**：剪辑器掌握时钟，按时间 t 请页面出帧，声音和画面对齐播放。
3. **修改**：从页面声明的参数、文字、图片和素材旁的字幕里，找出能改的地方，给出时间线、参数面板、画面上的编辑入口。所有修改都写进工程。
4. **导出**：逐帧画出动效，和拍摄素材合成，声音单独混音，输出成片。

用户可以亲手改，也可以让 AI 助手按 `guide.json` 来改，两者改的是同一份工程。

这四件事要遵守的约定，见 [motion-format.md](motion-format.md) 第 9 节「剪辑器与模板之间的协议」。

---

**In short:** an editor that receives a .motion file opens it (reads `motion.json`, checks the files, unpacks the
template into a fresh workspace and creates a project; the template stays untouched), previews it (the editor owns the
clock and asks pages for the frame at time t), edits it (exposes declared parameters, text, pictures and captions; all
changes go into the project), and exports it (pages drawn per frame, composited with footage, audio mixed separately).
People and AI assistants edit the same project. The rules are in [motion-format.md](motion-format.md), section 9.
