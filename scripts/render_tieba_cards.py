# -*- coding: utf-8 -*-
"""
贴吧连图生成器 v3：直接渲染 markdown 原文（不重写内容），并**按高度自动分页**。
保证每张图都不超过 --max-height（手机端友好），超长章节自动切成多张「（续 N）」卡。

用法:
  python render_tieba_cards.py --book <书名> --out <图片输出目录> \
      --md <报告.md> [--md <人物卡.md> ...] [--max-height 1700]

切分规则:
  1) '#' 主标题与首个 '##' 之前的内容 = 第 1 张（封面卡）
  2) '## ' 二级标题 = 章节；'### ' 三级标题（人物卡每个角色）= 独立章节
  3) 章节内按空行切块（markdown 表格因无空行天然成块）；无头浏览器实测每块渲染高度，
     贪婪装箱：外壳高 + 块高之和 <= max_height 才放进同一张
  4) 单块自身超高（如超长表格）→ 按表格行再拆、重复表头，拆到能放下为止
"""
import argparse
import html
import os
import re

W = 750
SCALE = 2
# 贴吧实测限制：单楼层最多 20 张图、单张 ≤5MB、格式 JPG/PNG/GIF；长图本身可很长
# （历史经验值 550×5685 仍不被压缩）。默认取 CSS 高 2560 → 实际 1500×5120px：
# 既远低于 5685 经验上限，又能把张数压进 20 张以内（封面与首个章节共页）。
DEFAULT_MAX_H = 2560
MAX_PX_H = 5680
MAX_BYTES = 5 * 1024 * 1024

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
.blk{padding:0}
"""

FOOTER = "AI 辅助生成 · 全部事实经原文核验 · novel-scan"


def classify(title):
    for kw, cls in (("雷点", "red"), ("郁闷", "amber"), ("排雷", "green"), ("纯洁度", "green")):
        if kw in title:
            return cls
    return ""


def esc(s):
    return html.escape(str(s or ""))


def md2html(md_text):
    try:
        import markdown
        return markdown.markdown(md_text, extensions=["tables", "nl2br"])
    except ImportError:
        out = html.escape(md_text)
        out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
        out = re.sub(r"^&gt; (.+)$", r"<blockquote>\1</blockquote>", out, flags=re.M)
        out = re.sub(r"^- (.+)$", r"<li>\1</li>", out, flags=re.M)
        out = re.sub(r"(<li>.*</li>)", r"<ul>\1</ul>", out, flags=re.S)
        out = re.sub(r"\n{2,}", "<br><br>", out)
        return out


def split_md(text, h3_split=True):
    lines = text.splitlines()
    main_title, start = "", 0
    for i, l in enumerate(lines):
        if l.startswith("# ") and not l.startswith("## "):
            main_title, start = l[2:].strip(), i + 1
            break
    secs, cur = [], None
    for l in lines[start:]:
        m2 = re.match(r"^## (.+)$", l)
        m3 = re.match(r"^### (.+)$", l) if h3_split else None
        if m2:
            cur = (m2.group(1).strip(), []); secs.append(cur)
        elif m3:
            cur = (m3.group(1).strip(), []); secs.append(cur)
        else:
            if cur is None:
                cur = ("卷首", []); secs.append(cur)
            cur[1].append(l)
    lead = ""
    if secs and secs[0][0] == "卷首":
        lead = "\n".join(secs[0][1]).strip(); secs = secs[1:]
    return main_title, lead, secs


def split_blocks(md):
    """按空行切块；丢掉纯分隔线（---/***/___）与空块——卡片自带页眉，无需 hr；
    并把「**避雷提醒**：」这类独立小标签并入紧随其后的块，避免被单独挤成一页。"""
    raw = [b.strip() for b in re.split(r"\n\s*\n", md.strip()) if b.strip()]
    out = []
    for b in raw:
        if re.fullmatch(r"[-*_]{3,}(\s*[-*_]{3,})*", b):
            continue
        keep = [l for l in b.splitlines() if not re.fullmatch(r"\s*[-*_]{3,}\s*", l)]
        b2 = "\n".join(keep).strip()
        if b2:
            out.append(b2)
    merged = []
    for b in out:
        if merged and re.fullmatch(r"\*{0,2}[^*\n]{2,14}\*{0,2}[：:]?", merged[-1]):
            merged[-1] = merged[-1] + "\n\n" + b
        else:
            merged.append(b)
    return merged


def split_table(block, max_rows):
    """超长表格按行拆成多个带重复表头的小表；非表格原样返回。"""
    lines = block.splitlines()
    if len(lines) < 3 or not lines[0].lstrip().startswith("|"):
        return [block]
    head, sep, rows = lines[0], lines[1], lines[2:]
    if len(rows) <= max_rows:
        return [block]
    return ["\n".join([head, sep] + rows[i:i + max_rows]) for i in range(0, len(rows), max_rows)]


BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def split_list(block, max_items):
    """超长列表按条目拆分（自动识别续行，并把开头的非条目小标签留在首段）；非列表原样返回。"""
    lines = [l for l in block.splitlines() if l.strip()]
    if not lines:
        return [block]
    lead, i = [], 0
    while i < len(lines) and not BULLET.match(lines[i]):
        lead.append(lines[i]); i += 1
    if i >= len(lines) or not BULLET.match(lines[i]):
        return [block]
    items, cur = [], None
    for l in lines[i:]:
        if BULLET.match(l):
            if cur is not None:
                items.append(cur)
            cur = [l]
        else:
            if cur is None:
                return [block]
            cur.append(l)
    if cur:
        items.append(cur)
    if len(items) <= max_items:
        return [block]
    out = []
    for j in range(0, len(items), max_items):
        body = "\n".join(x for it in items[j:j + max_items] for x in it)
        out.append(("\n\n".join(lead) + "\n\n" + body) if j == 0 and lead else body)
    return out


def split_oversized(block):
    """把过高的一块拆小：先按表格行，再按列表条目；都拆不动就原样返回。"""
    for fn, arg in ((split_table, 4), (split_list, 4), (split_table, 2), (split_list, 2), (split_list, 1)):
        subs = fn(block, arg)
        if len(subs) > 1:
            return subs
    return [block]


def shell(title, inner):
    return (f'<div class="card"><div class="top"><div class="k">x</div>'
            f'<h1>{esc(title)}</h1><div class="sub">y</div></div>'
            f'<div class="body">{inner}</div><div class="footer">{FOOTER}</div></div>')


def measure(pg, book, probes):
    """probes: [(subtitle, inner_html)] → 返回每张卡的渲染总高度（含外壳）。"""
    doc = ['<!DOCTYPE html><html><head><meta charset="utf-8"><style>%s</style></head><body>' % CSS]
    for st, inner in probes:
        doc.append(f'<div class="card"><div class="top"><div class="k">00/00</div>'
                   f'<h1>{esc(book)}</h1><div class="sub">{esc(st)}</div></div>'
                   f'<div class="body">{inner}</div><div class="footer">{FOOTER}</div></div>')
    doc.append("</body></html>")
    pg.set_content("".join(doc))
    pg.wait_for_timeout(150)
    return pg.evaluate("Array.from(document.querySelectorAll('.card')).map(e=>e.offsetHeight)")


def render_page(pg, book, subtitle, blocks, cls, no, total, out_path):
    inner = "".join(f'<div class="blk">{md2html(x)}</div>' for x in blocks)
    st = f' class="{cls}"' if cls else ""
    doc = ('<!DOCTYPE html><html><head><meta charset="utf-8"><style>%s</style></head><body>'
           '<div class="card"><div class="top"><div class="k">扫书报告 · %02d/%02d</div>'
           '<h1>%s</h1><div class="sub">%s</div></div><div class="body">%s</div>'
           '<div class="footer">%s</div></div></body></html>'
           % (CSS, no, total, esc(book), esc(subtitle), inner, FOOTER))
    f = os.path.join(os.path.dirname(out_path), "_html", f"card_{no:02d}.html")
    os.makedirs(os.path.dirname(f), exist_ok=True)
    open(f, "w", encoding="utf-8").write(doc)
    pg.goto("file:///" + f.replace("\\", "/"))
    pg.wait_for_timeout(80)
    pg.screenshot(path=out_path, full_page=True)
    return pg.evaluate("document.body.scrollHeight")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--md", action="append", required=True)
    ap.add_argument("--skip", default="角色卡片")
    ap.add_argument("--max-height", type=int, default=DEFAULT_MAX_H)
    args = ap.parse_args()
    MAXH = args.max_height

    # ---- 1) 解析章节（把封面块并入第一个章节，省一张图以满足贴吧单楼层 20 张上限）----
    sections, cover = [], None
    for md_path in args.md:
        text = open(md_path, encoding="utf-8").read()
        main_title, lead, secs = split_md(text)
        if lead and cover is None:
            cover = split_blocks(lead)
        for title, chunk in secs:
            if title.strip() == args.skip:
                continue
            sections.append((title, classify(title), split_blocks("\n".join(chunk))))
    if cover and sections:
        t, c, bl = sections[0]
        sections[0] = (t, c, list(cover) + bl)
        cover = None

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": 200}, device_scale_factor=SCALE)

        # ---- 2) 实测：外壳高 + 每块高 ----
        probes = [(s[0], "") for s in sections]
        for title, cls, blocks in sections:
            for blk in blocks:
                probes.append((title, f'<div class="blk">{md2html(blk)}</div>'))
        h = measure(pg, args.book, probes)
        chrome = {sections[i][0]: h[i] for i in range(len(sections))}
        ptr = len(sections)
        blkh = {}
        for title, cls, blocks in sections:
            for blk in blocks:
                blkh[(title, blk)] = h[ptr]; ptr += 1

        # ---- 3) 单块超高 → 预拆（表格按行 / 列表按条目）并实测子块 ----
        submap = {}
        need = []
        for title, cls, blocks in sections:
            for blk in blocks:
                if chrome[title] + blkh[(title, blk)] <= MAXH - 40:
                    continue
                subs = split_oversized(blk)
                submap[(title, blk)] = subs
                for s in subs:
                    if (title, s) not in blkh:
                        need.append((title, s))
        if need:
            hh = measure(pg, args.book, [(t, f'<div class="blk">{md2html(s)}</div>') for t, s in need])
            for (t, s), hh1 in zip(need, hh):
                blkh[(t, s)] = hh1 - chrome[t]

        def pieces_of(title, blk):
            return submap.get((title, blk), [blk])

        # ---- 4) 贪婪装箱（BUDGET 留安全余量：多块叠加时的块间距会略高于单块实测）----
        BUDGET = MAXH - 40
        pages = []  # (subtitle, cls, [blocks])
        for title, cls, blocks in sections:
            ch = chrome[title]
            cur, cur_h, part = [], ch, 0

            def flush():
                nonlocal cur, cur_h, part
                if cur:
                    pages.append((title + ("" if part == 0 else f"（续{part}）"), cls, cur))
                    part += 1
                    cur, cur_h = [], ch

            for blk in blocks:
                bh = blkh[(title, blk)]
                if cur and cur_h + bh > BUDGET:
                    flush()
                if cur_h + bh > BUDGET:        # 单块仍超高 → 用预拆好的子块
                    subs = pieces_of(title, blk)
                    if len(subs) > 1:
                        for s in subs:
                            sbh = blkh.get((title, s), bh)
                            if cur and cur_h + sbh > BUDGET:
                                flush()
                            cur.append(s); cur_h += sbh
                        continue
                cur.append(blk); cur_h += bh
            flush()

        # ---- 5) 出图 ----
        total = len(pages)
        os.makedirs(args.out, exist_ok=True)
        os.makedirs(os.path.join(args.out, "_html"), exist_ok=True)
        outs = []
        for i, (sub, cls, blocks) in enumerate(pages, 1):
            dst = os.path.join(args.out, f"{args.book}扫书_{i:02d}.png")
            render_page(pg, args.book, sub, blocks, cls, i, total, dst)
            outs.append(dst)
        b.close()

    # ---- 6) 平台限制自检（贴吧：≤20 张 / 单张 ≤5MB；像素高建议 ≤5000）----
    def png_size(p):
        with open(p, "rb") as f:
            head = f.read(24)
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            return (0, 0)
        w = int.from_bytes(head[16:20], "big")
        h = int.from_bytes(head[20:24], "big")
        return (w, h)

    print(f"[OK] {total} 张 → {args.out}")
    over_h, over_mb = [], []
    for p in outs:
        w, h = png_size(p)
        mb = os.path.getsize(p) / 1024 / 1024
        if h > MAX_PX_H:
            over_h.append((os.path.basename(p), h))
        if mb > MAX_BYTES / 1024 / 1024:
            over_mb.append((os.path.basename(p), round(mb, 2)))
        print(f"   {os.path.basename(p)}  {w}×{h}px  {mb:.2f}MB")
    print(f"[自检] 张数 {total}" + ("  ✅ ≤20" if total <= 20 else "  ⚠️ 超过 20 张，贴吧单贴可能传不完"))
    print(f"[自检] 像素高上限 {MAX_PX_H} → " + (f"⚠️ 超出 {over_h}" if over_h else "✅ 全部合规"))
    print(f"[自检] 单张 5MB 上限 → " + (f"⚠️ 超出 {over_mb}" if over_mb else "✅ 全部合规"))


if __name__ == "__main__":
    main()
