# -*- coding: utf-8 -*-
"""
手机长图生成器 v4：把 markdown 直接排成「可无缝拼接的手机阅读图」。

和 v3 的区别（v3 是贴吧卡片：每张顶部一块紫渐变大标题 + 页脚）：
  1) 默认不带任何横幅/页脚，正文从图片第一行开始、最后一行结束，按内容边界精确裁切；
     多张图粘在一起就是一篇连续的文章，中间没有重复书名和空白。
  2) 只在第 1 张放一行小标题（书名 + 副标题），`--head none` 可以完全去掉。
  3) 表格按手机宽度重排：≥4 列的大表转成「一条一卡」（标题标签 + 字段分段），
     3 列以内仍用圆角表格；不再出现被压成一条缝的 4 列挤字。
  4) 分页用真实排版位置计算（相邻块 top/bottom 差），不再靠 0.88 的经验系数，
     每张图都尽量填满到 max-height，张数更少。
  5) 会把标题从页面末尾挪到下一页开头（避免"孤行标题"）。

用法:
  python render_tieba_cards.py --book 都市猎人 --out ./手机图 \
      --md 都市猎人_情节速览报告.md [--md 都市猎人_人物卡.md ...]

常用参数:
  --width 1080        逻辑宽度（手机竖屏标准，输出 = width × --scale）
  --scale 1.5         输出倍率（1.5 → 1620px 宽，清晰且体积可控）
  --max-height 2600   单张最大逻辑高度
  --head slim|none    首图是否带一行小标题
  --dense             字号/行距收紧约 12%，长文档能少出几张
  --per-folder 20     每 20 张一个子目录（贴吧单楼层 20 张上限）
  --page-no           在图右下角标 "3 / 12"
  --merge             额外拼成一张无缝隙的全文长图
"""
import argparse
import html
import os
import re

MAX_BYTES = 5 * 1024 * 1024
MAX_PX_H = 5680

CSS_TPL = """
*{margin:0;padding:0;box-sizing:border-box}
html{background:#fff}
body{width:__W__px;background:#fff;color:#151922;font-size:34px;line-height:1.86;
     font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",-apple-system,"Segoe UI",sans-serif;
     -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}

/* 首图小标题：一行书名，一行灰色副题，不用色块 */
.head{padding:46px 48px 26px}
.head h1{font-size:46px;line-height:1.3;font-weight:800;letter-spacing:.5px;color:#0f1319}
.head .sub{font-size:23px;line-height:1.5;color:#8b94a3;letter-spacing:3px;margin-top:10px}
.head .rule{width:64px;height:6px;border-radius:3px;background:#2f5af0;margin-top:22px}

/* 正文：只有左右内边距，上下贴边，便于图片无缝相接 */
#content{padding:0 48px}
#content > .blk:first-child > *:first-child{margin-top:0}
#content > .blk:last-child > *:last-child{margin-bottom:0}

h2{--accent:#2f5af0;font-size:39px;line-height:1.45;font-weight:800;letter-spacing:.3px;
   margin:52px 0 22px;color:#10141b}
h2::before{content:"";display:block;width:54px;height:7px;border-radius:4px;
           background:var(--accent);margin-bottom:16px}
h3{--accent:#2f5af0;font-size:33px;line-height:1.5;font-weight:700;margin:42px 0 14px;color:#1a2130}
h3::before{content:"";display:inline-block;width:9px;height:26px;border-radius:4px;
           background:var(--accent);margin-right:14px;vertical-align:-3px}
h2.red,h3.red{--accent:#c0392b}
h2.amber,h3.amber{--accent:#b26a00}
h2.green,h3.green{--accent:#14794a}

p,li,td,th{font-size:34px;line-height:1.86}
p{margin:0 0 31px;text-align:justify;word-break:break-word}
ul,ol{padding-left:44px;margin:6px 0 26px}
li{margin:11px 0;text-align:justify}
li::marker{color:#a7b0bf}
strong{font-weight:800;color:#000}
em{font-style:normal;color:#2f5af0}

blockquote{margin:28px 0;padding:22px 26px;background:#f6f8fc;border-left:7px solid #d3dcf4;
           border-radius:0 14px 14px 0;color:#4d5766;font-size:30px;line-height:1.8}
blockquote p{font-size:30px;margin:0;text-align:left}
blockquote strong{color:#1b2330}

code{background:#eef1f7;color:#33405a;border-radius:8px;padding:2px 10px;font-size:30px;
     white-space:nowrap;font-family:"SF Mono",Consolas,monospace}
hr{border:none;border-top:1px solid #eceff4;margin:30px 0}

/* 同一段落被切成多块时的续块：抵消段间距，接回去看不出断点 */
#content > .blk.cont:not(:first-child) > p{margin-top:-26px}
body.dense #content > .blk.cont:not(:first-child) > p{margin-top:-22px}

/* 3 列以内：圆角表格 + 斑马纹 */
table{width:100%;border-collapse:separate;border-spacing:0;margin:24px 0;font-size:28px;
      border:1px solid #e8ecf3;border-radius:16px;overflow:hidden}
th{background:#f7f9fc;font-weight:700;color:#333c4d;text-align:left;padding:16px 18px;
   border-bottom:1px solid #e8ecf3;font-size:28px}
td{padding:16px 18px;border-bottom:1px solid #f1f3f7;vertical-align:top;font-size:28px;line-height:1.7}
tr:last-child td{border-bottom:none}
tr:nth-child(even) td{background:#fbfcfe}

/* ≥4 列的大表：拆成一条一卡，手机上不再挤压 */
.tcards{margin:24px 0}
.tcard{background:#fbfcfe;border:1px solid #edf0f6;border-radius:18px;padding:22px 24px;margin:18px 0}
.tcard .hd{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:6px}
.tcard .tag{background:#eef2ff;color:#2f5af0;font-size:24px;font-weight:700;
            padding:5px 16px;border-radius:999px;letter-spacing:.5px}
.tcard .tag.g{background:#f2f4f8;color:#5c6675}
.tcard .ttl{font-size:32px;font-weight:700;line-height:1.55;color:#151922;margin-bottom:4px}
.tcard .row{margin-top:14px}
.tcard .row .k{display:block;font-size:21px;letter-spacing:2px;color:#98a1b0;margin-bottom:3px}
.tcard .row .v{font-size:30px;line-height:1.75;color:#242c3a;text-align:justify}

.pno{font-size:22px;color:#b9c0cc;text-align:right;padding:18px 0 22px}

/* 紧凑模式 */
body.dense{font-size:30px}
body.dense h2{font-size:35px;margin:44px 0 18px}
body.dense h3{font-size:30px;margin:36px 0 12px}
body.dense p,body.dense li,body.dense td,body.dense th{font-size:30px;line-height:1.72}
body.dense p{margin-bottom:26px}
body.dense blockquote{font-size:27px;margin:24px 0;padding:18px 22px}
body.dense blockquote p{font-size:27px}
body.dense .tcard .row .v{font-size:27px}
body.dense table{font-size:25px}
body.dense th,body.dense td{font-size:25px;padding:13px 15px}
"""


def build_css(w, dense):
    css = CSS_TPL.replace("__W__", str(w))
    return css


# ---------- markdown → html ----------

def esc(s):
    return html.escape(str(s or ""))


def inline(s):
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`([^`]+?)`", r"<code>\1</code>", s)
    return s


def parse_table(md):
    lines = [l.strip() for l in md.splitlines() if l.strip()]
    if len(lines) < 3 or not lines[0].startswith("|"):
        return None
    if not re.fullmatch(r"\|?[\s:|-]+\|?", lines[1]):
        return None

    def cells(line):
        s = line.strip()
        if s.startswith("|"):
            s = s[1:]
        if s.endswith("|"):
            s = s[:-1]
        return [c.strip() for c in s.split("|")]

    head = cells(lines[0])
    rows = [cells(l) for l in lines[2:] if l.startswith("|")]
    if not head or not rows:
        return None
    n = len(head)
    rows = [r + [""] * (n - len(r)) if len(r) < n else r[:n] for r in rows]
    return head, rows


def table_cards(head, rows):
    """宽表转卡片：4 列以上 = 两枚标签 + 分字段；3 列 = 首列当小标题 + 分字段。"""
    out = ['<div class="tcards">']
    wide = len(head) >= 4
    ntitle = 2 if wide else 1
    for r in rows:
        out.append('<div class="tcard">')
        if wide:
            tags = []
            for i in range(ntitle):
                v = r[i].strip()
                if not v:
                    continue
                lab = head[i].strip()
                txt = f"{lab} {v}" if len(v) <= 10 and len(lab) <= 4 else v
                tags.append(f'<span class="tag{"" if i == 0 else " g"}">{inline(txt)}</span>')
            if tags:
                out.append('<div class="hd">' + "".join(tags) + "</div>")
        else:
            out.append(f'<div class="ttl">{inline(r[0])}</div>')
        for i in range(ntitle, len(head)):
            out.append(f'<div class="row"><span class="k">{inline(head[i])}</span>'
                       f'<div class="v">{inline(r[i])}</div></div>')
        out.append("</div>")
    out.append("</div>")
    return "".join(out)


def md2html(md):
    tb = parse_table(md)
    if tb:
        head, rows = tb
        if len(head) >= 3:
            return table_cards(head, rows)
    md = re.sub(r"^\s*[-*_]{3,}\s*$", "", md, flags=re.M)
    try:
        import markdown
        return markdown.markdown(md, extensions=["tables", "nl2br"])
    except ImportError:
        out = esc(md)
        out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
        out = re.sub(r"`([^`]+?)`", r"<code>\1</code>", out)
        out = re.sub(r"^&gt; (.+)$", r"<blockquote>\1</blockquote>", out, flags=re.M)
        out = re.sub(r"^- (.+)$", r"<li>\1</li>", out, flags=re.M)
        out = re.sub(r"(<li>.*</li>)", r"<ul>\1</ul>", out, flags=re.S)
        out = re.sub(r"\n{2,}", "<br><br>", out)
        return out


# ---------- markdown 结构切分 ----------

def classify(title):
    for kw, cls in (("雷点", "red"), ("郁闷", "amber"), ("排雷", "green"), ("纯洁度", "green")):
        if kw in title:
            return cls
    return ""


def split_md(text):
    lines = text.splitlines()
    main_title, start = "", 0
    for i, l in enumerate(lines):
        if l.startswith("# ") and not l.startswith("## "):
            main_title, start = l[2:].strip(), i + 1
            break
    secs, lead, cur = [], [], None
    for l in lines[start:]:
        m2 = re.match(r"^## (.+)$", l)
        m3 = re.match(r"^### (.+)$", l)
        if m2:
            cur = (m2.group(1).strip(), 2, []); secs.append(cur)
        elif m3:
            cur = (m3.group(1).strip(), 3, []); secs.append(cur)
        else:
            if cur is None:
                lead.append(l)
            else:
                cur[2].append(l)
    return main_title, lead, secs


def split_blocks(md):
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


BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def split_table(block, max_rows):
    lines = block.splitlines()
    if len(lines) < 3 or not lines[0].lstrip().startswith("|"):
        return [block]
    head, sep, rows = lines[0], lines[1], lines[2:]
    if len(rows) <= max_rows:
        return [block]
    return ["\n".join([head, sep] + rows[i:i + max_rows]) for i in range(0, len(rows), max_rows)]


def split_list(block, max_items):
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


def fit_subs(md):
    """把过大的块拆成更小的排版单元，让分页能填满（不是等到装不下才拆）。"""
    if md.lstrip().startswith("|"):
        for n in (3, 2, 1):
            subs = split_table(md, n)
            if len(subs) > 1:
                return subs
    items = sum(1 for l in md.splitlines() if BULLET.match(l))
    if items >= 3:
        for n in (2, 1):
            subs = split_list(md, n)
            if len(subs) > 1:
                return subs
    return [md]


def split_oversized(block):
    for fn, arg in ((split_table, 3), (split_table, 2), (split_table, 1),
                    (split_list, 4), (split_list, 2), (split_list, 1)):
        subs = fn(block, arg)
        if len(subs) > 1:
            return subs
    return [block]


# ---------- 排版测量 / 出图 ----------

class Atom:
    __slots__ = ("md", "kind", "cls", "cont")

    def __init__(self, md, kind, cls="", cont=False):
        self.md, self.kind, self.cls, self.cont = md, kind, cls, cont


def is_plain_para(md):
    lines = [l for l in md.splitlines() if l.strip()]
    if not lines:
        return False
    if md.lstrip().startswith("|") or md.lstrip().startswith("#"):
        return False
    if any(BULLET.match(l) for l in lines):
        return False
    return True


SENT = re.compile(r"(?<=[。！？!?；;”」』])")


def chunk_text(text, limit):
    """把超长段落按句号切成若干块（每块 ≤ limit 字），不改变文字。"""
    if len(text) <= limit:
        return [text]
    sents = [s for s in SENT.split(text) if s]
    out, cur = [], ""
    for s in sents:
        if cur and len(cur) + len(s) > limit:
            out.append(cur); cur = s
        else:
            cur += s
    if cur:
        out.append(cur)
    # 单句本身超长：退化为按长度硬切（在标点或逗号处优先）
    final = []
    for p in out:
        while len(p) > limit * 1.6:
            cut = max(p.rfind("，", 0, limit), p.rfind("、", 0, limit))
            cut = cut + 1 if cut > limit * 0.4 else limit
            final.append(p[:cut]); p = p[cut:]
        final.append(p)
    return final


def page_doc(css, head, atoms, dense, pno=None):
    body = "".join(
        f'<div class="blk{" cont" if a.cont else ""}">{md2html(a.md)}</div>' for a in atoms)
    if pno:
        body += f'<div class="pno">{pno}</div>'
    cls = ' class="dense"' if dense else ""
    return ('<!DOCTYPE html><html><head><meta charset="utf-8"><style>' + css + "</style></head>"
            f'<body{cls}><div id="page">{head}<div id="content">{body}</div></div></body></html>')


MEASURE_JS = """() => {
  const c = document.getElementById('content').getBoundingClientRect();
  return Array.from(document.querySelectorAll('#content > .blk')).map(e => {
    const r = e.getBoundingClientRect();
    return [r.top - c.top, r.bottom - c.top];
  });
}"""


def measure(pg, css, head, atoms, dense):
    pg.set_content(page_doc(css, head, atoms, dense))
    pg.wait_for_timeout(120)
    return pg.evaluate(MEASURE_JS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--md", action="append", required=True)
    ap.add_argument("--skip", default="")
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--scale", type=float, default=1.5)
    ap.add_argument("--max-height", type=int, default=2600)
    ap.add_argument("--head", choices=["slim", "none"], default="slim")
    ap.add_argument("--dense", action="store_true")
    ap.add_argument("--per-folder", type=int, default=0)
    ap.add_argument("--page-no", action="store_true")
    ap.add_argument("--merge", action="store_true", help="额外拼一张无缝隙全文长图")
    args = ap.parse_args()

    W, SCALE, MAXH = args.width, args.scale, args.max_height
    css = build_css(W, args.dense)

    # ---- 1) md → atoms（小节标题本身也作为正文 h2/h3 保留）----
    atoms, main_title, sub_title = [], "", ""
    lead_atoms = []
    for idx, md_path in enumerate(args.md):
        text = open(md_path, encoding="utf-8").read()
        title, lead, secs = split_md(text)
        if not main_title and title:
            parts = re.split(r"\s*[·｜|]\s*", title, maxsplit=1)
            main_title = parts[0].strip()
            sub_title = parts[1].strip() if len(parts) > 1 else ""
        if idx == 0 and lead:
            for b in split_blocks("\n".join(lead)):
                atoms.append(Atom(b, "b"))
        for stitle, level, chunk in secs:
            if args.skip and stitle.strip() == args.skip:
                continue
            marker = "#" * level
            atoms.append(Atom(f"{marker} {stitle}", "h", classify(stitle)))
            for b in split_blocks("\n".join(chunk)):
                atoms.append(Atom(b, "b", classify(stitle)))
    if not atoms:
        raise SystemExit("没有可渲染的内容")

    head = ""
    if args.head == "slim" and main_title:
        head = ('<div class="head"><h1>' + esc(main_title) + "</h1>"
                + (f'<div class="sub">{esc(sub_title)}</div>' if sub_title else "")
                + '<div class="rule"></div></div>')

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        pg = browser.new_page(viewport={"width": W, "height": 400}, device_scale_factor=SCALE)

        # ---- 2) 第一次测量：超高的块先处理 ----
        # 长段落（报告里"一人一段"的写法常见 1000+ 字）按句号切块，避免一页只装一段；
        # 表格/列表拆不动时再按行、按条目拆。
        font = 30 if args.dense else 34
        lh = 1.72 if args.dense else 1.86
        chars_per_line = max(10, int((W - 96) / font))
        lines_per_page = max(6, int(MAXH / (font * lh)))
        chunk_limit = max(200, int(chars_per_line * lines_per_page * 0.45))

        spans = measure(pg, css, head, atoms, args.dense)
        final = []
        for a, (top, bot) in zip(atoms, spans):
            h = bot - top
            if h > MAXH * 0.5:
                if is_plain_para(a.md) and len(a.md) > chunk_limit:
                    pieces = chunk_text(a.md, chunk_limit)
                    if len(pieces) > 1:
                        final.extend(Atom(p, a.kind, a.cls, cont=(i > 0))
                                     for i, p in enumerate(pieces))
                        continue
                subs = fit_subs(a.md)
                if len(subs) > 1:
                    final.extend(Atom(s, a.kind, a.cls) for s in subs)
                    continue
            if h <= MAXH:
                final.append(a)
                continue
            subs = split_oversized(a.md)
            if len(subs) == 1:
                final.append(a)                      # 拆不动，认了
            else:
                final.extend(Atom(s, a.kind, a.cls) for s in subs)

        # ---- 3) 第二次测量：拿到精确的 top/bottom 位置 ----
        spans = measure(pg, css, head, final, args.dense)

        # ---- 4) 按真实位置装箱（每张尽量填满，不留经验余量）----
        pages, cur = [], []
        for i, (top, bot) in enumerate(spans):
            if cur and bot - spans[cur[0]][0] > MAXH:
                pages.append(cur)
                cur = [i]
            else:
                cur.append(i)
        if cur:
            pages.append(cur)

        # 贪婪装箱会留下很矮的尾巴：能塞进上一页就合过去
        i = 0
        while i < len(pages) - 1:
            merged_h = spans[pages[i + 1][-1]][1] - spans[pages[i][0]][0]
            if merged_h <= MAXH * 1.01:
                pages[i] = pages[i] + pages.pop(i + 1)
            else:
                i += 1

        # 孤行标题：页面最后只剩一个 h2/h3 → 挪到下一页开头
        for i in range(len(pages) - 1):
            while len(pages[i]) > 1 and final[pages[i][-1]].kind == "h":
                pages[i + 1].insert(0, pages[i].pop())

        if os.environ.get("SCAN_DEBUG"):
            print("[dbg] atoms", len(final), "spans", len(spans), spans[:6])
            for n, idxs in enumerate(pages, 1):
                hh = spans[idxs[-1]][1] - spans[idxs[0]][0]
                print(f"[dbg] p{n:02d} {len(idxs):2d}块 {hh:6.0f}px | {final[idxs[0]].md[:28]!r}")

        # ---- 5) 出图 ----
        total = len(pages)
        os.makedirs(args.out, exist_ok=True)
        outs = []
        for no, idxs in enumerate(pages, 1):
            folder = args.out
            if args.per_folder:
                layer = (no - 1) // args.per_folder + 1
                folder = os.path.join(args.out, f"第{layer}楼")
                os.makedirs(folder, exist_ok=True)
            dst = os.path.join(folder, f"{args.book}_手机版_{no:02d}.png")
            pno = f"{no} / {total}" if args.page_no else None
            pg.set_content(page_doc(css, head if no == 1 else "", [final[i] for i in idxs],
                                    args.dense, pno))
            pg.wait_for_timeout(80)
            pg.query_selector("#page").screenshot(path=dst)
            outs.append(dst)
        browser.close()

    # ---- 6) 自检 ----
    def png_size(p):
        with open(p, "rb") as f:
            h = f.read(24)
        if h[:8] != b"\x89PNG\r\n\x1a\n":
            return (0, 0)
        return int.from_bytes(h[16:20], "big"), int.from_bytes(h[20:24], "big")

    print(f"[OK] {total} 张 → {args.out}（{W}×{SCALE} 输出，单张上限 {MAXH} 逻辑高）")
    over_h, over_mb = [], []
    for p in outs:
        w, h = png_size(p)
        mb = os.path.getsize(p) / 1024 / 1024
        if h > MAX_PX_H:
            over_h.append((os.path.basename(p), h))
        if mb > MAX_BYTES / 1024 / 1024:
            over_mb.append((os.path.basename(p), round(mb, 2)))
        print(f"   {os.path.basename(p)}  {w}×{h}px  {mb:.2f}MB")
    print(f"[自检] 张数 {total}" + ("  ✅ ≤20" if total <= 20 else "  ⚠️ 超过 20 张，按 --per-folder 20 分楼发"))
    print("[自检] 像素高 → " + (f"⚠️ 超出 {over_h}" if over_h else "✅ 全部合规"))
    print("[自检] 单张 5MB → " + (f"⚠️ 超出 {over_mb}" if over_mb else "✅ 全部合规"))

    # 顺序清单（按文件名排序即阅读顺序）
    with open(os.path.join(args.out, "_图片顺序.txt"), "w", encoding="utf-8") as f:
        for i, p in enumerate(outs, 1):
            f.write(f"{i:02d}  {os.path.relpath(p, args.out)}\n")

    # ---- 7) 可选：拼成一张无缝长图 ----
    if args.merge:
        try:
            from PIL import Image
            ims = [Image.open(p).convert("RGB") for p in outs]
            wt = max(i.width for i in ims)
            H = sum(i.height for i in ims)
            canvas = Image.new("RGB", (wt, H), "white")
            y = 0
            for im in ims:
                canvas.paste(im, (0, y))
                y += im.height
            mp = os.path.join(args.out, f"{args.book}_全文长图.png")
            canvas.save(mp, optimize=True)
            print(f"[合并] {mp}  {wt}×{H}px  {os.path.getsize(mp) / 1024 / 1024:.2f}MB")
        except ImportError:
            print("[合并] 跳过：未安装 Pillow")


if __name__ == "__main__":
    main()
