# -*- coding: utf-8 -*-
"""
贴吧连图生成器 v2：直接渲染 markdown 原文（不重写内容）。
按标题切分成多张手机端卡片图，每张 = md 的一个自然章节，格式与 md 完全一致。

用法:
  python render_tieba_cards.py --book <书名> --out <图片输出目录> \
      --md <报告.md> [--md <人物卡.md> ...]
切分规则:
  - '#' 主标题与首个 '##' 之前的内容 = 第 1 张（封面卡）
  - '## ' 二级标题 = 一张卡
  - '### ' 三级标题（如人物卡的每个角色）= 独立一张卡
"""
import argparse
import glob
import html
import json
import os
import re

W = 750
SCALE = 2

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{width:750px;background:#fbfbfc;font-family:"Microsoft YaHei","PingFang SC",sans-serif;color:#22252a;-webkit-font-smoothing:antialiased}
.top{background:linear-gradient(135deg,#2f5af0,#7a3cf0);color:#fff;padding:32px 40px 24px}
.top .k{font-size:24px;opacity:.85;letter-spacing:2px}
.top h1{font-size:50px;margin:6px 0 8px}
.top .sub{font-size:27px;opacity:.95;font-weight:600}
.body{padding:28px 40px 34px}
h2{font-size:34px;margin:24px 0 14px;padding-left:16px;border-left:9px solid #2f5af0;line-height:1.35}
h3{font-size:31px;margin:20px 0 12px;color:#2f5af0}
h2.red,h3.red{border-color:#c5221f;color:#c5221f}
h2.amber,h3.amber{border-color:#a56300;color:#a56300}
h2.green,h3.green{border-color:#137333;color:#137333}
p,li,td,th{font-size:27px;line-height:1.75}
ul,ol{padding-left:34px;margin:8px 0}
li{margin:7px 0}
strong{color:#111}
blockquote{background:#f3f4f6;border-left:8px solid #c9cdd4;padding:14px 20px;margin:12px 0;color:#52565c;border-radius:0 12px 12px 0;font-size:26px}
blockquote p{font-size:26px;margin:4px 0}
table{width:100%;border-collapse:collapse;margin:12px 0}
td,th{border:1px solid #e2e4e8;padding:10px 12px;text-align:left;vertical-align:top;font-size:24px;line-height:1.6}
th{background:#f1f3f6;color:#333}
.footer{padding:18px 40px 32px;color:#9aa0a6;font-size:22px;text-align:center}
hr{border:none;border-top:1px dashed #d8dbe0;margin:16px 0}
code{background:#f1f3f6;border-radius:6px;padding:2px 8px;font-size:24px}
"""


def classify(title):
    for kw, cls in (("雷点", "red"), ("郁闷", "amber"), ("排雷", "green"), ("纯洁度", "green")):
        if kw in title:
            return cls
    return ""


def split_md(text, h3_split):
    """把 md 文本切成 [(title, md_chunk)]。"""
    lines = text.splitlines()
    # 找主标题
    main_title = ""
    start = 0
    for i, l in enumerate(lines):
        if l.startswith("# ") and not l.startswith("## "):
            main_title = l[2:].strip()
            start = i + 1
            break
    # 切节
    secs = []  # (level, title, [lines])
    cur = None
    for l in lines[start:]:
        m2 = re.match(r"^## (.+)$", l)
        m3 = re.match(r"^### (.+)$", l) if h3_split else None
        if m2:
            cur = (2, m2.group(1).strip(), [])
            secs.append(cur)
        elif m3:
            cur = (3, m3.group(1).strip(), [])
            secs.append(cur)
        else:
            if cur is None:
                cur = (0, "卷首", [])
                secs.append(cur)
            cur[2].append(l)
    # 顶层（卷首）内容
    lead = ""
    if secs and secs[0][0] == 0:
        lead = "\n".join(secs[0][2]).strip()
        secs = secs[1:]
    return main_title, lead, secs


def md2html(md_text):
    try:
        import markdown
        return markdown.markdown(md_text, extensions=["tables", "nl2br"])
    except ImportError:
        # 极简回退
        out = html.escape(md_text)
        out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
        out = re.sub(r"^&gt; (.+)$", r"<blockquote>\1</blockquote>", out, flags=re.M)
        out = re.sub(r"^- (.+)$", r"<li>\1</li>", out, flags=re.M)
        out = re.sub(r"(<li>.*</li>)", r"<ul>\1</ul>", out, flags=re.S)
        out = re.sub(r"\n{2,}", "<br><br>", out)
        return out


def render_section(sec_title, md_chunk, cls):
    body = md2html(md_chunk)
    st = f' class="{cls}"' if cls else ""
    return f"<h2{st}>{esc(sec_title)}</h2>\n{body}"


def esc(s):
    return html.escape(str(s or ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--md", action="append", required=True)
    ap.add_argument("--skip", default="角色卡片", help="跳过的纯目录型标题")
    args = ap.parse_args()

    cards = []  # (title, body_html)
    for md_path in args.md:
        text = open(md_path, encoding="utf-8").read()
        main_title, lead, secs = split_md(text, h3_split=True)
        if lead:
            cards.append((main_title, md2html(lead)))
        for lvl, title, chunk in secs:
            if title.strip() == args.skip:
                continue
            cls = classify(title)
            body = render_section(title, "\n".join(chunk).strip(), cls)
            cards.append((title, body))

    total = len(cards)
    os.makedirs(args.out, exist_ok=True)
    tmp = os.path.join(args.out, "_html")
    os.makedirs(tmp, exist_ok=True)
    paths = []
    for i, (title, body) in enumerate(cards, 1):
        doc = (f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>'
               f'<div class="top"><div class="k">扫书报告 · {i:02d}/{total:02d}</div>'
               f'<h1>{esc(args.book)}</h1><div class="sub">{esc(title)}</div></div>'
               f'<div class="body">{body}</div>'
               f'<div class="footer">AI 辅助生成 · 全部事实经原文核验 · novel-scan</div></body></html>')
        p = os.path.join(tmp, f"card_{i:02d}.html")
        open(p, "w", encoding="utf-8").write(doc)
        paths.append((p, os.path.join(args.out, f"{args.book}扫书_{i:02d}.png")))
    print(f"[OK] {total} cards")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": 1200}, device_scale_factor=SCALE)
        for src, dst in paths:
            pg.goto("file:///" + src.replace("\\", "/"))
            pg.wait_for_timeout(100)
            pg.screenshot(path=dst, full_page=True)
        b.close()
    print("[DONE]", args.out)


if __name__ == "__main__":
    main()
