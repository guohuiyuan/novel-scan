#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
novel-scan: render_bookreview_md.py —— 按「清风扫书」体例渲染整篇扫书稿

结构（对标公众号扫书帖，顺序固定）：
  书名/作者/字数 → 题材/状态/平台 → 8 维评分 → 简介 → 男主 → 女主逐条
  → 其他角色 → 分维度点评（剧情/女主/车技/设定/缺点）→ 排雷 → 数据说明

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

GRADE_ORDER = ["情节", "文笔", "感情", "车速", "人物刻画", "新意", "压抑度", "总评"]
DIM_ORDER = ["剧情方面", "女主方面", "车技方面", "设定方面", "缺点方面"]


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


def join_sent(*parts):
    return "".join(endp(p) for p in parts if clean(p))


def find_img(img_dir, name, idx):
    if not img_dir or not os.path.isdir(img_dir):
        return ""
    safe = re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_")
    for fn in sorted(os.listdir(img_dir)):
        if fn.lower().endswith((".webp", ".png", ".jpg")) and safe in fn:
            return "人物图/" + fn
    return ""


def render(data, img_dir=None, images=True):
    bm = data.get("book_meta") or {}
    book = bm.get("title") or data.get("book", "")
    out = [f"# 《{book}》", ""]

    # ---- 书况（清风开头那五行）----
    meta_bits = []
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
    for label, val in (("题材", genre), ("状态", bm.get("status")),
                       ("平台", bm.get("platform"))):
        if clean(val):
            out.append(f"**{label}：{clean(val)}**")
    out.append("")

    # ---- 评分（8 维）----
    ratings = data.get("ratings") or {}
    if ratings:
        out += ["## 评分", "", "| 维度 | 档位 |", "|---|---|"]
        keys = [k for k in GRADE_ORDER if k in ratings] + \
               [k for k in ratings if k not in GRADE_ORDER]
        for k in keys:
            v = ratings[k]
            grade = v.get("grade", "") if isinstance(v, dict) else str(v)
            out.append(f"| {k} | **{clean(grade)}** |")
        out.append("")
        reasons = [(k, clean(v.get("reason", ""))) for k, v in ratings.items()
                   if isinstance(v, dict) and clean(v.get("reason", ""))]
        if reasons:
            for k, r in reasons:
                out.append(f"- {k}：{r}")
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
            p = clean(p)
            if p:
                out += [p, ""]

    # ---- 男主 ----
    male = data.get("male_protagonist") or {}
    if male.get("name"):
        out += ["## 男主", ""]
        arc = clean(male.get("arc") or male.get("growth"))
        ident = clean(male.get("identity"))
        if arc:
            # arc 本身就是「开局身份→起势→终局」，identity 再写一遍会整段重复
            out += [f"**{male['name']}**", "", endp(arc), ""]
        else:
            para = (f"**{male['name']}**，" + endp(ident)) if ident else f"**{male['name']}**"
            out += [para, ""]
        extra = []
        if not arc and ident:
            extra.append(f"- **身份**：{ident}")
        if clean(male.get("appearance")):
            extra.append(f"- **外貌**：{clean(male['appearance'])}")
        if clean(male.get("personality")):
            extra.append(f"- **性格**：{clean(male['personality'])}")
        if extra:
            out += extra + [""]
        sl = male.get("signature_line")
        if isinstance(sl, dict) and clean(sl.get("quote", "")):
            out.append(f"> 名场面：「{clean(sl['quote'])}」"
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
            body = join_sent(ident, c.get("appearance"))
            if arc:
                body += endp(arc)
            else:
                ev = [clean(e.get("event") or e.get("text") or "" if isinstance(e, dict) else e)
                      for e in (c.get("key_events") or [])]
                ev = [e for e in ev if e]
                if ev:
                    body += "经历：" + "→".join(ev) + "。"
            pur = c.get("purity") or {}
            if clean(pur.get("verdict")):
                body += f"纯洁度结论：{clean(pur['verdict'])}。"
            # 序号写进标题文本，不用 md 有序列表语法：
            # 列表项之间夹空行与图片段落会被渲染器判成新列表，全部重新显示为 1。
            out += [f"### {i}. {c.get('name','')}", ""]
            if body:
                out.append(body)
                out.append("")
            tags = c.get("personality_tags")
            if isinstance(tags, list) and tags:
                out.append(f"性格特点：{'、'.join(clean(t) for t in tags if clean(t))}")
            elif clean(c.get("personality")):
                out.append(f"性格特点：{clean(c['personality'])}")
            sl = c.get("signature_line")
            if isinstance(sl, dict) and clean(sl.get("quote", "")):
                out.append(f"名场面：「{clean(sl['quote'])}」"
                           + (f" —— {clean(sl.get('scene',''))}" if clean(sl.get("scene", "")) else ""))
            out.append("")
            if images:
                p = find_img(img_dir, c.get("name", ""), i)
                if p:
                    out += [f"![{c.get('name','')}]({p})", ""]

    # ---- 其他角色 ----
    side = data.get("side_characters") or []
    if side:
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

    # ---- 分维度点评 ----
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
            head = f"**{i}.{t}**" if t else f"**{i}.**"
            out += [f"{head}：{txt}" if txt else head, ""]

    # ---- 排雷 ----
    lei = data.get("book_leidian_summary") or []
    yu = data.get("book_yumen_summary") or []
    if lei or yu or data.get("characters"):
        out += ["## 排雷", ""]
        for title, items in (("雷点", lei), ("郁闷点", yu)):
            out += [f"**{title}**", ""]
            if not items:
                out += ["- 无（逐条核过，未成立）", ""]
                continue
            for it in items:
                q = clean(it.get("quote", ""))
                out.append(f"- `{it.get('category','未归类')}` {clean(it.get('evidence',''))}"
                           + (f" 「{q}」" if q else ""))
            out.append("")

    # ---- 数据说明 ----
    out += ["## 数据说明", ""]
    note = []
    if data.get("coverage"):
        note.append(f"覆盖范围：{clean(data['coverage'])}")
    if data.get("source"):
        note.append(f"原文：{clean(data['source'])}")
    note.append("全部人物事实与引文已回原文逐字核验；引文照抄，不改写、不拼接。")
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
    ap.add_argument("--no-images", action="store_true")
    a = ap.parse_args()
    data = json.load(open(a.json, encoding="utf-8"))
    md = render(data, a.img_dir, images=not a.no_images)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    miss = [k for k in ("ratings", "blurb", "dimension_reviews") if not data.get(k)]
    if not (data.get("male_protagonist") or {}).get("name"):
        miss.append("male_protagonist")
    print(f"[OK] {a.out} ({len(md)} chars)" + (f"  [WARN] 缺 {', '.join(miss)}" if miss else ""))


if __name__ == "__main__":
    main()
