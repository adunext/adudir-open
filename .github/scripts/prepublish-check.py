#!/usr/bin/env python3
"""Pre-publication self-check for this repository.

usage: python3 .github/scripts/prepublish-check.py [--source-repo PATH] [--report FILE]

Checks
  1. Tracked files (and every path in history) live only under docs/, brand/, .github/, are top-level README* /
     LICENSE* files, or are one of the descriptive files of the template structure example (TEMPLATE_KEEP).
     No code files (.py .js .mjs .ts .html .css ...) anywhere outside .github/, in the tree or in history.
  2. No commit id of the source repository appears in this history: not as a commit id, and not as a
     10+ character hex token in any commit message or file of any commit (needs --source-repo).
  3. No other path of the source repository appears in history (backend/, electron/, packages/, frontend/, ...).
  4. Secret scan of the working tree and the full history with gitleaks: zero findings.
  5. A word list scan (personal paths, internal hosts, credential markers) over the working tree and history.
  6. Banned names: zero.
  7. Content comparison with the source repository (needs --source-repo with full objects): no file of any
     commit has the same content as any object of the source repository, except image/font/video media and
     standard MIT / OFL license texts.
Exit code 0 only when every check passes.
"""
import argparse, base64, json, os, re, shutil, subprocess, sys, tempfile

ALLOWED_DIRS = ("docs/", ".github/", "brand/")
ALLOWED_TOP = re.compile(r"^(README|LICENSE)[^/]*$")
TEMPLATE_KEEP = re.compile(r"^templates/paper-perspective-talking-head/("
                           r"motion\.json|README\.md|guide\.json|params\.schema\.json|native\.params\.schema\.json"
                           r"|media-input-keys\.json|presets/[^/]+\.json|previews/[^/]+\.jpg"
                           r"|brand/[^/]+\.(webm|gif)|assets/fonts/[^/]+\.woff2|assets/font-provenance\.json"
                           r"|licenses/[^/]+\.(txt|json))$")
CODE_EXT = re.compile(r"\.(py|pyc|js|mjs|cjs|jsx|ts|tsx|html?|css|sh|bash|zsh|ps1|bat|cmd|go|rs|java|kt|swift|c|cc|cpp|h|hpp|m|mm|rb|php|lua|wasm|node)$", re.I)
LICENSE_TEXT = re.compile(r"(^LICENSE$|(^|/)licenses/[^/]*(OFL|LICENSE)[^/]*\.txt$)")
MEDIA_EXT = re.compile(r"\.(png|jpe?g|gif|webp|webm|mp4|mov|woff2?|ttf|otf|ico|icns)$", re.I)
FOREIGN_PREFIXES = ("backend/", "electron/", "packages/", "frontend/", "apps/", "scripts/", "deep-agent/",
                    "tools/", "server/", "src/", "mobile/", "admin-panel/")
WORDS = r"(/Users/[a-z]|/Volumes/|/home/[a-z]|C:\\Users\\|BEGIN [A-Z ]*PRIVATE KEY|sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,})"
FORBIDDEN_NAMES = re.compile(r"(^|/)(personal/|motiongit\.key\.json$|receipt\.json$|signature\.json$|\.env$|id_rsa|.*\.pem$|.*\.p12$)")
# Names that must never come back. Kept encoded so the list itself does not publish them; decoded at run time.
# Matching is case-sensitive on purpose.
BANNED = base64.b64decode("KFxiRGVzY3JpcHRcYnxcYkthcHdpbmdcYnxcYlJlY3V0XGJ8RGFWaW5jaXxcYlJlc29sdmUoPz0gPyjnrYl8U3R1ZGlvfOWPr3znm7TmjqUpKXxcYk9USU9cYnxcYm90aW9cYnxPcGVuVGltZWxpbmVJT3xvcGVudGltZWxpbmVpb3xcYkVETFxifEFwcGxlLWxpa2Up").decode("utf-8")
SELF = ".github/scripts/prepublish-check.py"


def git(*args, cwd=None, ok=(0,)):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    if r.returncode not in ok:
        raise SystemExit(f"git {' '.join(args[:3])} failed: {r.stderr.decode('utf-8', 'replace')}")
    return r.stdout.decode("utf-8", "replace")


def path_ok(p):
    return (p.startswith(ALLOWED_DIRS) or ("/" not in p and ALLOWED_TOP.match(p) is not None)
            or TEMPLATE_KEEP.match(p) is not None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-repo", help="local clone of the source repository (all refs are compared)")
    ap.add_argument("--report", help="write a Markdown report here")
    ap.add_argument("--extra-words", help="file with one extra regex per line (kept outside the repo, e.g. internal hosts and names)")
    a = ap.parse_args()
    root = git("rev-parse", "--show-toplevel").strip()
    os.chdir(root)
    results = []

    def record(name, ok, detail):
        results.append((name, ok, detail))

    # 1 + 3. paths in the tree and in history
    tracked = [p for p in git("ls-files", "-z").split("\0") if p]
    bad_tree = [p for p in tracked if not path_ok(p)]
    record("1. 工作区文件只在允许的位置 / tracked files in allowed locations", not bad_tree,
           f"{len(tracked)} files checked; outside: {bad_tree[:10]}")
    hist_paths = set(p for p in git("log", "--all", "--format=", "--name-only").split("\n") if p)
    bad_hist = sorted(p for p in hist_paths if not path_ok(p))
    foreign = sorted(p for p in hist_paths if p.startswith(FOREIGN_PREFIXES))
    record("1b. 历史中的路径都在允许的位置 / every path in history in allowed locations", not bad_hist,
           f"{len(hist_paths)} distinct paths; outside: {bad_hist[:10]}")
    record("3. 历史中没有其它源仓库路径 / no other source-repo paths", not foreign,
           f"foreign paths: {foreign[:10]}")
    code = sorted(p for p in hist_paths if CODE_EXT.search(p) and not p.startswith(".github/"))
    record("1c. 树和历史里没有代码文件 / no code files in tree or history (outside .github/)", not code,
           f"code paths: {code[:10]}")
    named = sorted(p for p in hist_paths if FORBIDDEN_NAMES.search(p))
    record("3b. 历史中没有凭据、收据、签名类文件 / no credential, receipt or signature files in history", not named,
           f"hits: {named[:10]}")

    # 2. source commit ids
    commits = git("rev-list", "--all").split()
    if a.source_repo:
        src = set(git("rev-list", "--all", cwd=a.source_repo).split())
        same = sorted(set(commits) & src)
        prefixes = {h[:10] for h in src}
        hits = set()
        for c in commits:
            text = git("log", "-1", "--format=%B", c)
            text += git("grep", "-I", "-h", "-o", "-E", "[0-9a-f]{10,40}", c, "--", ok=(0, 1))
            for tok in re.findall(r"[0-9a-f]{10,40}", text):
                if tok[:10] in prefixes:
                    hits.add(tok)
        record("2. 历史中没有源仓库的提交编号 / no source-repo commit ids in history", not same and not hits,
               f"{len(commits)} commits vs {len(src)} source commits; equal ids: {len(same)}; hex tokens matching a source commit: {sorted(hits)[:10]}")
    else:
        record("2. 历史中没有源仓库的提交编号 / no source-repo commit ids in history", False, "skipped: pass --source-repo")

    # 4. gitleaks
    gl = shutil.which("gitleaks")
    if gl:
        with tempfile.TemporaryDirectory() as tmp:
            out = {}
            for mode, args in (("history", ["git", "--log-opts=--all"]), ("tree", ["dir", "."])):
                rep = os.path.join(tmp, mode + ".json")
                subprocess.run([gl, *args, "--config", os.path.join(root, ".github", "gitleaks.toml"), "--no-banner", "--redact", "--report-format", "json", "--report-path", rep, "--exit-code", "0"],
                               capture_output=True)
                out[mode] = json.load(open(rep)) if os.path.exists(rep) and os.path.getsize(rep) else []
        n = len(out["history"]) + len(out["tree"])
        record("4. 泄密扫描为零 / secret scan (gitleaks, tree + full history)", n == 0,
               f"history findings: {len(out['history'])}; tree findings: {len(out['tree'])}; "
               + "; ".join(f"{f.get('RuleID')} {f.get('File')}" for f in (out['history'] + out['tree'])[:10]))
    else:
        record("4. 泄密扫描为零 / secret scan (gitleaks, tree + full history)", False, "gitleaks not installed")

    # 5. word list over history and tree
    pattern = WORDS
    if a.extra_words:
        extra = [l.strip() for l in open(a.extra_words, encoding="utf-8") if l.strip() and not l.startswith("#")]
        pattern = "(" + "|".join([WORDS] + extra) + ")"
    rx = re.compile(pattern, re.I)
    wl = set()
    for c in commits:
        msg = git("log", "-1", "--format=%an %ae %cn %ce %B", c)
        for m in rx.finditer(msg): wl.add(("message " + c[:10], "<redacted>" if a.extra_words else m.group(0)))
    r = subprocess.run(["git", "grep", "-I", "-n", "-i", "-P", pattern, *commits, "--", ".", ":(exclude)" + SELF], capture_output=True)
    if r.returncode not in (0, 1):
        raise SystemExit("word-list git grep failed: " + r.stderr.decode("utf-8", "replace"))
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        wl.add(("content", line.split(":", 3)[1] + ":" + line.split(":", 3)[2] if line.count(":") >= 3 else line[:120]))
    bl = set()
    for c in commits:
        for m in re.finditer(BANNED, git("log", "-1", "--format=%B", c)): bl.add(("message " + c[:10], m.group(0)))
    r = subprocess.run(["git", "grep", "-I", "-n", "-o", "-P", BANNED, *commits, "--", ".", ":(exclude)" + SELF], capture_output=True)
    if r.returncode not in (0, 1):
        raise SystemExit("banned-name git grep failed: " + r.stderr.decode("utf-8", "replace"))
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split(":", 3)
        bl.add((parts[1] + ":" + parts[2] if len(parts) > 3 else line[:120], parts[-1]))
    record("6. 禁用名为零 / banned names",
           not bl, f"hits: {sorted(bl)[:10]}")
    record("5. 敏感词扫描为零 / word-list scan (personal paths, credential markers" + (", extra internal list" if a.extra_words else "") + ")",
           not wl, f"hits: {sorted(wl)[:10]}")

    # 7. content comparison with every object of the source repository
    if a.source_repo:
        blobs = {}
        for c in commits:
            for line in git("ls-tree", "-r", c).splitlines():
                meta, path = line.split("\t", 1)
                blobs.setdefault(meta.split()[2], set()).add(path)
        src_objs = set()
        r = subprocess.run(["git", "cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype)"],
                           cwd=a.source_repo, capture_output=True)
        for line in r.stdout.decode().splitlines():
            oid, typ = line.split()
            if typ == "blob":
                src_objs.add(oid)
        same = {oid: paths for oid, paths in blobs.items() if oid in src_objs}
        same_all = sorted(p for paths in same.values() for p in paths)
        same_media = [p for p in same_all if MEDIA_EXT.search(p)]
        same_license = [p for p in same_all if LICENSE_TEXT.search(p)]
        same_code = [p for p in same_all if p not in same_media and p not in same_license]
        record("7. 与源仓库内容零相同（图片、字体、视频和标准许可文本除外）/ no file content equal to any source-repo object (media and standard license texts excepted)",
               bool(src_objs) and not same_code,
               f"{len(blobs)} distinct file contents vs {len(src_objs)} source blobs; equal non-media files: {len(same_code)} {same_code[:10]}; "
               f"equal media files: {len(same_media)}; equal standard license texts (MIT / OFL): {len(same_license)} {same_license}")
    else:
        record("7. 与源仓库内容零相同（图片、字体、视频和标准许可文本除外）/ no file content equal to any source-repo object (media and standard license texts excepted)",
               False, "skipped: pass --source-repo")

    ok = all(r[1] for r in results)
    head = git("rev-parse", "HEAD").strip()
    lines = [f"# 发布前自检 / Pre-publication self-check", "", f"- HEAD: `{head}`", f"- commits: {len(commits)}",
             f"- result: **{'PASS' if ok else 'FAIL'}**", "", "| 检查 | 结果 | 说明 |", "|---|---|---|"]
    for name, passed, detail in results:
        lines.append(f"| {name} | {'通过 PASS' if passed else '未通过 FAIL'} | {detail.replace('|', '/')} |")
    report = "\n".join(lines) + "\n"
    print(report)
    if a.report:
        open(a.report, "w", encoding="utf-8").write(report)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
