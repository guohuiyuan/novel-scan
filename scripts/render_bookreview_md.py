#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
novel-scan: render_bookreview_md.py —— 按「清风扫书」体例渲染整篇扫书稿

结构（对标公众号扫书帖，顺序固定）：
  书名/作者/字数 → 题材/状态/平台 → 8 维评分 → 简介 → 雷点与郁闷点概况 → 男主
  → 女主逐条（每条内含该角色的雷点/郁闷点明细）→ 其他角色 → 分维度点评 → 数据说明

雷点为什么拆两处：概况放在简介后、男主前，是给读者的「接受度闸门」——先知道这本书踩了
哪些线再决定读不读；明细放进各自角色条目，是因为一条雷点离开人物就说不清（谁对谁做了什么）。
早年明细只在文末汇总，全是「她随身带着电话……」这种代词，读者判断不了是谁。

与 render_characters_md.py 的分工：
  - 这个脚本产出「能直接发出去的扫书稿」（<书名>_书评.md）；
  - 那个产出「结构化人物卡」（<书名>_人物卡.md，详细字段备查）。
  两者数据同源（同一份人物数据 JSON），不各写一套事实。

用法：
  python render_bookreview_md.py --json <书名>_人物数据.json --out <书名>_书评.md \
      [--img-dir <输出目录>/人物图] [--no-images]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textfmt import named_evidence  # noqa: E402

GRADE_ORDER = ["情节", "文笔", "感情", "车速", "人物刻画", "新意", "压抑度", "总评"]
DIM_ORDER = ["剧情方面", "女主方面", "车技方面", "设定方面", "缺点方面"]

# 纯洁度四维：书评里必须逐项列出，不能只写「全初」——读者要知道初在哪里
PURITY_KEYS = [("chu", "处"), ("jingshen_chu", "精神初"), ("hunyin", "初婚"), ("chumo", "初摸")]
PURITY_ICON = {"非处": "❌", "精神初": "✅", "非初": "❌", "有婚史婚约": "❌", "被非男主触碰": "❌",
               "处": "✅", "初婚": "✅", "初摸": "✅", "初": "✅", "不适用": "➖", "未知": "❓"}

# 总评档位 → 扫书帖的"粮草"结算词（清风体系：神作 > 仙草 > 粮草 > 干粮 > 毒草）
SETTLE_WORD = {"S": "神作", "S-": "神作", "A+": "仙草", "A": "仙草", "A-": "仙草",
               "B+": "粮草", "B": "粮草", "B-": "粮草",
               "C+": "干粮", "C": "干粮", "C-": "干粮", "D": "毒草"}


def grade_of(ratings, key="总评"):
    v = (ratings or {}).get(key)
    if isinstance(v, dict):
        return clean(v.get("grade", ""))
    return clean(v) if v else ""


def settle_word(ratings, status):
    """`完结仙草` / `在更粮草` / `仙草`：状态 + 档位结算词。"""
    g = grade_of(ratings)
    word = SETTLE_WORD.get(g.upper(), "")
    if not word:
        return ""
    st = clean(status)
    if st.startswith("完结"):
        return "完结" + word
    if "连载" in st or "在更" in st:
        return "在更" + word
    return word


def short_count(word_count):
    """`约 111 万字` → `111万字`（标题里不留空格与"约"）。"""
    s = clean(word_count).replace(" ", "")
    s = s.replace("约", "").replace("大约", "")
    if not s:
        return ""
    if s[-1] in "字部":
        return s.rstrip("部") + "字" if s[-1] == "部" else s
    return s + "字"


def headline_of(data):
    """扫书帖标题：`完结仙草：都市后宫 扮猪吃虎 圣门圣女 姐妹让爱 111万字`

    优先用 book_meta.headline（C2 阶段整句写死）；
    否则用「结算词：题材 四字卖点×N 字数」拼，缺哪段就跳哪段。
    """
    bm = data.get("book_meta") or {}
    if clean(bm.get("headline")):
        return clean(bm["headline"])
    ratings = data.get("ratings") or {}
    head = settle_word(ratings, bm.get("status"))
    genre = bm.get("genre")
    if isinstance(genre, list):
        genre = [clean(g) for g in genre if clean(g)]
        main = genre[0] if genre else ""
        tail = "后宫" if "后宫" in genre else ""
        genre_s = main + (tail if tail and main != tail else "")
    else:
        genre_s = clean(genre)
    tags = [clean(t) for t in (bm.get("headline_tags") or []) if clean(t)]
    parts = [p for p in ([head] if head else []) + ([genre_s] if genre_s else []) + tags
             + ([short_count(bm.get("word_count"))] if short_count(bm.get("word_count")) else []) if p]
    if not parts:
        return f"《{bm.get('title') or data.get('book') or ''}》"
    return (parts[0] + "：" + " ".join(parts[1:])) if len(parts) > 1 else parts[0]


def find_cover(out_path, img_dir=None):
    """封面放在输出目录根（封面.webp / cover.jpg …），也认 --img-dir 上一层。"""
    dirs = []
    if out_path:
        dirs.append(os.path.dirname(os.path.abspath(out_path)))
    if img_dir:
        dirs.append(os.path.dirname(os.path.abspath(img_dir)))
    for d in dict.fromkeys(dirs):
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            stem, ext = os.path.splitext(fn)
            if stem in ("封面", "cover") and ext.lower() in (".webp", ".png", ".jpg", ".jpeg"):
                return fn
    return ""


def clean(text):
    if text is None:
        return ""
    s = str(text)
    s = re.sub(r"（[^（）]*L\d+[^（）]*）", "", s)
    s = re.sub(r"\([^()]*L\d+[^()]*\)", "", s)
    s = re.sub(r"L\d+(?:[/-]\d+)*", "", s)
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"（\s*）|\(\s*\)", "", s)
    return s.strip()


def endp(s):
    """补一个句末标点，避免拼接出「……了曾柔是」这种粘连。"""
    s = clean(s)
    if not s:
        return ""
    return s if s[-1] in "。！？…”』」" else s + "。"


def first_sent(s):
    """取第一句（有 arc 时 identity 只留身份定位，关系线交给 arc，避免同一件事说两遍）。"""
    s = clean(s)
    if not s:
        return ""
    parts = [p for p in re.split(r"(?<=[。！？])", s) if p.strip()]
    return parts[0].strip() if parts else s


def purity_line(pur):
    """纯洁度四维逐项：处 ｜ 精神初 ｜ 初婚 ｜ 初摸 —— 总结论。

    只写「全初」等于把四维压成一维：读者看不出是处女、还是没精神出轨、还是没婚史。
    缺项一律记「未知」（不默认全初），全缺时返回空串，调用方退回只写结论。
    """
    if not any(str((pur or {}).get(k) or "").strip() for k, _ in PURITY_KEYS):
        return ""
    vals = [str(pur.get(k) or "未知").strip() for k, _ in PURITY_KEYS]
    if all(v.startswith("未知") for v in vals):
        return "未知"          # 四维全无证据，逐项列四个 ❓ 只是噪音
    parts = []
    for (k, label), v in zip(PURITY_KEYS, vals):
        icon = next((PURITY_ICON[key] for key in PURITY_ICON if v.startswith(key)), "❓")
        parts.append(f"{label} {icon}")
    verdict = clean(pur.get("verdict"))
    return " ｜ ".join(parts) + (f" —— **{verdict}**" if verdict else "")


def find_img(img_dir, name, idx):
    if not img_dir or not os.path.isdir(img_dir):
        return ""
    safe = re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_")
    for fn in sorted(os.listdir(img_dir)):
        if fn.lower().endswith((".webp", ".png", ".jpg")) and safe in fn:
            return "人物图/" + fn
    return ""


def split_paragraphs(text, target=170, hard=260):
    """把长段落按句末标点拆成几段，**一个字符都不增删**（只加空行）。

    为什么需要：identity/appearance/arc 拼起来常是 500 字一坨，手机上一屏全是字。
    拆段只在句号/问号/叹号后断，且只在超过 hard 字时才拆，短字段不动。
    """
    s = clean(text)
    if not s:
        return []
    if len(s) <= hard:
        return [s]
    sents = [p for p in re.split(r"(?<=[。！？])", s) if p.strip()]
    paras, cur = [], ""
    for sn in sents:
        if cur and len(cur) + len(sn) > target:
            paras.append(cur)
            cur = sn
        else:
            cur += sn
    if cur:
        paras.append(cur)
    return paras


def cell(s):
    """表格单元格：竖线会让表格塌掉，转义一下。"""
    return clean(s).replace("|", "\\|")


def emit_paras(out, text, label=None, target=170, hard=260):
    """输出若干段落；label 只加在第一段前，最后一段补句末标点（与原版拼接口径一致）。"""
    paras = split_paragraphs(text, target=target, hard=hard)
    for i, seg in enumerate(paras):
        if i == len(paras) - 1:
            seg = endp(seg)
        out += [f"**{label}**：{seg}" if (label and i == 0) else seg, ""]
    return out


def leiyu_items(data):
    """取「雷点 / 郁闷点」，每条都带 name。

    优先用 assemble_json 汇总的书级列表（它已写入 name 并把开头代词换成角色名）；
    老数据/手工拼的 JSON 没有 name 时，现场从 characters 里聚合兜底。
    """
    def take(book_key, char_key):
        items = [i for i in (data.get(book_key) or []) if isinstance(i, dict)]
        if items and any(clean(i.get("name")) for i in items):
            return [{"name": clean(i.get("name")) or "—",
                     "category": clean(i.get("category")) or "未归类",
                     "evidence": clean(i.get("evidence")),
                     "quote": clean(i.get("quote"))} for i in items]
        out = []
        for c in data.get("characters") or []:
            nm = clean(c.get("name"))
            for i in (c.get(char_key) or []):
                if isinstance(i, dict):
                    out.append({"name": nm, "category": clean(i.get("category")) or "未归类",
                                "evidence": clean(named_evidence(i.get("evidence"), nm)),
                                "quote": clean(i.get("quote"))})
        return out
    return take("book_leidian_summary", "leidian"), take("book_yumen_summary", "yumen")


def emit_leiyu_overview(out, lei, yu):
    """简介之后的「开读前先看」：只做索引，逐条细节留在各角色条目里。"""
    if not (lei or yu):
        return
    out += ["## 雷点与郁闷点（开读前先看）", ""]
    bits = []
    if lei:
        bits.append(f"**{len(lei)} 处雷点**")
    if yu:
        bits.append(f"**{len(yu)} 处郁闷点**")
    out.append("> 全书 " + "、".join(bits) + "。"
               "雷点＝容易直接弃书的踩线项（背叛、绿帽、神雕、死女、漏女一类）；"
               "郁闷点＝膈应但未必弃书（拒女、虐心、擦边、百合、拉皮条、虐主一类）。"
               "**按自己的接受度决定要不要读**——下面只列索引，具体情节与原文引文见各角色条目。")
    out.append("")
    if lei:
        out += ["**雷点**", ""]
        for it in lei:
            out.append(f"- **{it['name']} · {it['category']}**：{it['evidence']}")
        out.append("")
    if yu:
        order, bucket = [], {}
        for it in yu:
            k = it["category"]
            if k not in bucket:
                bucket[k] = []
                order.append(k)
            bucket[k].append(it["name"])
        order.sort(key=lambda k: (-len(bucket[k]), k))
        out += ["**郁闷点分布**", "",
                "| 类别 | 次数 | 涉及角色 |", "|:---|:--:|:---|"]
        for k in order:
            counts = {}
            for n in bucket[k]:
                counts[n] = counts.get(n, 0) + 1
            who = "、".join(f"{n}（{c} 次）" if c > 1 else n for n, c in counts.items())
            out.append(f"| **{cell(k)}** | {len(bucket[k])} | {cell(who)} |")
        out.append("")


def render(data, img_dir=None, images=True, cover=""):
    bm = data.get("book_meta") or {}
    book = bm.get("title") or data.get("book", "")
    out = [f"# {headline_of(data)}", ""]
    if cover and images:
        out += [f"![封面]({cover})", ""]

    # ---- 书况（清风开头那五行）----
    meta_bits = [f"《{book}》"] if book else []
    if bm.get("author"):
        meta_bits.append(f"作者：{bm['author']}")
    if bm.get("word_count"):
        meta_bits.append(f"字数：{bm['word_count']}")
    if isinstance(bm.get("chapters"), int) and bm["chapters"]:
        meta_bits.append(f"{bm['chapters']} 章")
    if isinstance(bm.get("volumes"), int) and bm["volumes"]:
        meta_bits.append(f"{bm['volumes']} 卷")
    if meta_bits:
        out += ["**" + " ｜ ".join(meta_bits) + "**", ""]

    genre = bm.get("genre")
    if isinstance(genre, list):
        genre = " ".join(str(g) for g in genre if g)
    # 三行挤成一行：md 里连续单换行会被并成一段，反而更乱；用 ｜ 分隔与上一行同版式
    tri = [f"**{label}：{clean(val)}**" for label, val in
           (("题材", genre), ("状态", bm.get("status")), ("平台", bm.get("platform")))
           if clean(val)]
    if tri:
        out.append(" ｜ ".join(tri))
    out.append("")

    # ---- 评分（8 维）：档位与依据同表，别让读者来回对照 ----
    ratings = data.get("ratings") or {}
    if ratings:
        def grade_of_one(v):
            return clean(v.get("grade", "")) if isinstance(v, dict) else str(v)

        def reason_of_one(v):
            return clean(v.get("reason", "")) if isinstance(v, dict) else ""

        out += ["## 评分", "", "| 维度 | 档位 | 依据 |", "|:---|:---:|---|"]
        keys = [k for k in GRADE_ORDER if k in ratings] + \
               [k for k in ratings if k not in GRADE_ORDER]
        for k in keys:
            v = ratings[k]
            out.append(f"| {k} | **{grade_of_one(v)}** | {cell(reason_of_one(v)) or '—'} |")
        out.append("")
        out.append("> 评分为阅读主观判断，非原文事实；事实性结论见下方排雷与人物依据。")
        out.append("")

    # ---- 简介 ----
    blurb = data.get("blurb")
    if blurb:
        out.append("## 简介")
        out.append("")
        if isinstance(blurb, str):
            blurb = [blurb]
        for p in blurb:
            for seg in split_paragraphs(p, target=220, hard=320):
                out += [seg, ""]

    # ---- 雷点与郁闷点概况（简介之后、男主之前：先让读者判断接受度）----
    lei_all, yu_all = leiyu_items(data)
    emit_leiyu_overview(out, lei_all, yu_all)

    # ---- 男主 ----
    male = data.get("male_protagonist") or {}
    if male.get("name"):
        out += ["## 男主", "", f"### {male['name']}", ""]
        arc = clean(male.get("arc") or male.get("growth"))
        ident = clean(male.get("identity"))
        if arc:
            # arc 本身就是「开局身份→起势→终局」，identity 再写一遍会整段重复
            emit_paras(out, arc)
        elif ident:
            emit_paras(out, ident)
        if not arc and ident:
            out += [f"**身份**：{endp(first_sent(ident))}", ""]
        if clean(male.get("appearance")):
            out += [f"**外貌**：{endp(male['appearance'])}", ""]
        if clean(male.get("personality")):
            out += [f"**性格**：{endp(male['personality'])}", ""]
        sl = male.get("signature_line")
        if isinstance(sl, dict) and clean(sl.get("quote", "")):
            out.append(f"> **名场面**：「{clean(sl['quote'])}」"
                       + (f" —— {clean(sl.get('scene',''))}" if clean(sl.get("scene", "")) else ""))
            out.append("")
        if images:
            p = find_img(img_dir, male["name"], 0)
            if p:
                out += [f"![{male['name']}]({p})", ""]

    # ---- 女主 ----
    chars = data.get("characters") or []
    if chars:
        out += ["## 女主", ""]
        for i, c in enumerate(chars, 1):
            arc = clean(c.get("arc"))
            ident = clean(c.get("identity"))
            if arc:
                ident = first_sent(ident)
            # 序号写进标题文本，不用 md 有序列表语法：
            # 列表项之间夹空行与图片段落会被渲染器判成新列表，全部重新显示为 1。
            out += [f"### {i}. {c.get('name','')}", ""]
            if ident:
                out += [f"**身份**：{endp(ident)}", ""]
            if clean(c.get("appearance")):
                out += [f"**外貌**：{endp(c['appearance'])}", ""]
            if arc:
                emit_paras(out, arc, label="经历")
            else:
                ev = [clean(e.get("event") or e.get("text") or "" if isinstance(e, dict) else e)
                      for e in (c.get("key_events") or [])]
                ev = [e for e in ev if e]
                if ev:
                    out += [f"**经历**：{'→'.join(ev)}。", ""]
            pur = c.get("purity") or {}
            pl = purity_line(pur)
            if pl:
                out += [f"**纯洁度**：{pl}", ""]
            elif clean(pur.get("verdict")):
                out += [f"**纯洁度结论**：{endp(pur['verdict'])}", ""]
            tags = c.get("personality_tags")
            if isinstance(tags, list) and tags:
                out += [f"**性格特点**：{'、'.join(clean(t) for t in tags if clean(t))}", ""]
            elif clean(c.get("personality")):
                out += [f"**性格特点**：{clean(c['personality'])}", ""]
            # 该角色的雷点/郁闷点明细放在这里：离开人物就说不清「谁对谁做了什么」
            for label, key in (("雷点", "leidian"), ("郁闷点", "yumen")):
                items = [it for it in (c.get(key) or []) if isinstance(it, dict)]
                if not items:
                    continue
                out += [f"**{label}**", ""]
                for it in items:
                    q = clean(it.get("quote"))
                    # 角色自己的条目里保留原代词：标题就是人名，「还关雅妮自由，她平静地……」这种
                    # 同一个名字出现两遍反而别扭；换名只在跨角色的汇总列表里做（见 leiyu_items）。
                    out.append(f"- **{clean(it.get('category')) or '未归类'}**："
                               f"{clean(it.get('evidence'))}")
                    if q:
                        out.append(f"  > 「{q}」")
                out.append("")
            sl = c.get("signature_line")
            if isinstance(sl, dict) and clean(sl.get("quote", "")):
                out.append(f"> **名场面**：「{clean(sl['quote'])}」"
                           + (f" —— {clean(sl.get('scene',''))}" if clean(sl.get("scene", "")) else ""))
                out.append("")
            if images:
                p = find_img(img_dir, c.get("name", ""), i)
                if p:
                    out += [f"![{c.get('name','')}]({p})", ""]

    # ---- 其他角色：成表的比一长串列表好扫 ----
    side = data.get("side_characters") or []
    if side and all(isinstance(s, dict) for s in side):
        out += ["## 其他角色", "", "| 角色 | 身份 | 一句话 |", "|:---|:---|:---|"]
        for s in side:
            out.append(f"| **{cell(s.get('name',''))}** | {cell(s.get('title','')) or '—'} "
                       f"| {cell(s.get('note','')) or '—'} |")
        out.append("")
    elif side:
        out += ["## 其他角色", ""]
        for s in side:
            if isinstance(s, str):
                out.append(f"- {clean(s)}")
                continue
            nm = clean(s.get("name", ""))
            tt = clean(s.get("title", ""))
            nt = clean(s.get("note", ""))
            head = f"**{nm}**" + (f"（{tt}）" if tt else "")
            out.append(f"- {head}：{nt}" if nt else f"- {head}")
        out.append("")

    # ---- 分维度点评：一段一标题，手机上一眼知道读到哪 ----
    dims = data.get("dimension_reviews") or []
    if dims:
        out += ["## 分维度点评", ""]
        norm = []
        for d in dims:
            if isinstance(d, dict):
                norm.append((clean(d.get("title", "")), clean(d.get("text", ""))))
            else:
                norm.append(("", clean(d)))
        norm.sort(key=lambda kv: DIM_ORDER.index(kv[0]) if kv[0] in DIM_ORDER else 99)
        for i, (t, txt) in enumerate(norm, 1):
            out += [f"### {i}. {t}" if t else f"### {i}", ""]
            emit_paras(out, txt, target=220, hard=320)

    # ---- 数据说明 ----
    out += ["## 数据说明", ""]
    note = []
    if data.get("coverage"):
        note.append(f"覆盖范围：{clean(data['coverage'])}")
    if data.get("source"):
        note.append(f"原文：{clean(data['source'])}")
    note.append("全部人物事实与引文已回原文逐字核验；引文照抄，不改写、不拼接。")
    if lei_all or yu_all:
        note.append("雷点与郁闷点的索引在开头「雷点与郁闷点」一节，逐条情节与引文写在对应角色条目内。")
    if data.get("verify_note"):
        note.append(clean(data["verify_note"]))
    if bm.get("status") == "未知":
        note.append("状态/平台未能核实（本地全本 txt 无法确认首发站与连载状态），按「未知」处理。")
    out += [f"- {n}" for n in note]
    out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--img-dir", help="人物图目录；给了就在人物段落下方插图")
    ap.add_argument("--cover", help="封面图（相对 --out 目录的路径优先）；不给就自动找 封面/cover.*")
    ap.add_argument("--no-images", action="store_true")
    a = ap.parse_args()
    data = json.load(open(a.json, encoding="utf-8"))
    cover = ""
    if not a.no_images:
        if a.cover:
            cover = a.cover
        else:
            cover = find_cover(a.out, a.img_dir)
    md = render(data, a.img_dir, images=not a.no_images, cover=cover)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    miss = [k for k in ("ratings", "blurb", "dimension_reviews") if not data.get(k)]
    if not (data.get("male_protagonist") or {}).get("name"):
        miss.append("male_protagonist")
    bm = data.get("book_meta") or {}
    if not bm.get("headline") and not bm.get("headline_tags"):
        miss.append("headline_tags（标题只剩结算词+题材，缺四字卖点）")
    print(f"[OK] {a.out} ({len(md)} chars)" + (f"  [WARN] 缺 {', '.join(miss)}" if miss else ""))
    print(f"     标题：{headline_of(data)}")
    print(f"     封面：{cover or '（无，可用 pick_cover.py 抽一张）'}")


if __name__ == "__main__":
    main()
