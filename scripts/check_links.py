# -*- coding: utf-8 -*-
"""
novel-scan: check_links.py —— 检查仓库内 Markdown 的相对链接/图片是否指得实

为什么要这个：`examples/README.md` 放错了一层（写在 `examples/` 根下，却按 `examples/<书名>/`
的视角写 `人物图/01_某某.webp`），GitHub 上点开就是 404，本地渲染却看不出来。
每次加示例、挪目录、改图片文件名跑一遍，比人工点强。

只管相对链接：
  - `http(s)://`、`mailto:`、`#锚点`、`/绝对路径` 一律跳过（外链不联网校验）
  - `%E4%BA%BA` 这类 percent-encoded 路径先解码再判存在
  - `path#锚点` 只校 path；目录链接也认（示例目录常用）
  - fenced code block 与行内代码里的 `![](人物图/xx.webp)` 只是讲解语法，不算链接

用法：
  python scripts/check_links.py                  # 检查仓库根（默认当前目录）
  python scripts/check_links.py --root . --quiet  # 只报错
退出码：有缺失 = 1，全通过 = 0（可直接挂进 CI 或交付前自检）。
"""
import argparse
import os
import re
import sys
import urllib.parse

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".workbuddy",
             "novel-scan-results", "_prescan", "scan_notes"}
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
EXTERNAL = ("http://", "https://", "mailto:", "tel:", "#", "//")
FENCE_RE = re.compile(r"```.*?```", re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def strip_code(text):
    """去掉代码块与行内代码：SKILL.md 里要讲「md 里的 ![](人物图/xx.webp) 会被内嵌」，
    那只是语法示例，不是真链接，不能算缺失。"""
    return INLINE_CODE_RE.sub("", FENCE_RE.sub("", text))


def md_files(root):
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.lower().endswith((".md", ".markdown")):
                yield os.path.join(dirpath, f)


def check(path, root):
    base = os.path.dirname(path)
    text = strip_code(open(path, encoding="utf-8").read())
    missing, total = [], 0
    for raw in LINK_RE.findall(text):
        if raw.startswith(EXTERNAL):
            continue
        target = raw.split("#", 1)[0].strip()
        if not target:
            continue
        total += 1
        rel = urllib.parse.unquote(target)
        hit = os.path.normpath(os.path.join(base, rel))
        if not os.path.exists(hit):
            missing.append((target, hit))
    return total, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--quiet", action="store_true", help="只报有问题的文件")
    a = ap.parse_args()

    root = os.path.abspath(a.root)
    bad = 0
    files = 0
    for p in sorted(md_files(root)):
        rel = os.path.relpath(p, root)
        total, missing = check(p, root)
        files += 1
        if missing:
            bad += len(missing)
            print(f"[FAIL] {rel}（{len(missing)}/{total} 条链接指不到）")
            for t, hit in missing:
                print(f"   -> {t}")
                print(f"      解析为 {os.path.relpath(hit, root)}，不存在")
        elif not a.quiet and total:
            print(f"[OK]   {rel}（{total} 条相对链接全部命中）")

    print(f"\n检查 {files} 个 md，缺失 {bad} 条")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
