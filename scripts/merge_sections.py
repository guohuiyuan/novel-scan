# -*- coding: utf-8 -*-
"""
novel-scan skill: merge_sections.py
把重写式清洗产出的章节文件合并为「书名_扫书_人物篇.md」：
- 剥离章节内残留的 `#` 一级书名行
- 章节标题统一为 `##`，节 `###`，目 `####`
- 生成 GitHub 风格锚点目录（空白->-、标点删除、CJK 保留）插入前言之后

用法:
  python merge_sections.py --sections <目录> --preamble <前言md> --out <成品md>
章节文件按文件名排序合并；前言中可包含 <!--TOC--> 占位符，无占位符则目录追加在前言末尾。
"""
import argparse
import os
import re
import sys
import unicodedata


def github_slug(title):
    t = title.strip().lower()
    out = []
    for ch in t:
        cat = unicodedata.category(ch)
        if ch.isspace():
            out.append("-")
        elif ch.isalnum() or ch == "-" or ch == "_" or "\u4e00" <= ch <= "\u9fff":
            out.append(ch)
        # 其他标点删除
    return "".join(out)


def normalize_section(text):
    lines = text.splitlines()
    kept = []
    for ln in lines:
        # 剥离一级标题行（书名残留）
        if re.match(r"^#\s+", ln):
            continue
        kept.append(ln)
    text = "\n".join(kept).strip()
    # 将正文中比 ## 更高的 ##/### 已天然满足；确保章节存在
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sections", required=True)
    ap.add_argument("--preamble", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    names = sorted(n for n in os.listdir(args.sections) if n.endswith(".md"))
    if not names:
        print("[ERROR] sections 目录为空"); return 1

    chapters = []
    for n in names:
        with open(os.path.join(args.sections, n), "r", encoding="utf-8") as f:
            body = normalize_section(f.read())
        # 找章节标题（## 开头的第一行）
        m = re.search(r"^## (.+)$", body, flags=re.M)
        title = m.group(1).strip() if m else os.path.splitext(n)[0]
        chapters.append((title, body))

    toc_lines = ["## 目录", ""]
    for title, _ in chapters:
        slug = github_slug(title)
        anchor = title if False else slug
        toc_lines.append(f"- [{title}](#{anchor})")
    toc_lines.append("")
    toc = "\n".join(toc_lines)

    with open(args.preamble, "r", encoding="utf-8") as f:
        preamble = f.read().strip()

    if "<!--TOC-->" in preamble:
        preamble = preamble.replace("<!--TOC-->", toc)
    else:
        preamble = preamble + "\n\n" + toc

    parts = [preamble] + [body for _, body in chapters]
    final = "\n\n---\n\n".join(parts) + "\n"
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(final)
    print(f"[OK] {args.out} ({len(final)} chars, {len(chapters)} 章)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
