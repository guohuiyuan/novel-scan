# -*- coding: utf-8 -*-
"""
novel-scan skill: render_characters_md.py
把人物数据 JSON 渲染成人物卡片 Markdown（无行号、不显示剔除别名、置信度只显示等级）。

用法:
  python render_characters_md.py --json <书名>_人物数据.json --out <书名>_人物卡.md
"""
import argparse
import json
import os
import re

PURITY_KEYS = [("chu", "处"), ("jingshen_chu", "精神初"), ("hunyin", "初婚"), ("chumo", "初摸")]
ICON = {"非处": "❌", "精神初": "✅", "非初": "❌", "有婚史婚约": "❌", "被非男主触碰": "❌",
        "处": "✅", "初婚": "✅", "初摸": "✅", "初": "✅", "不适用": "➖", "未知": "❓"}
CONF_MAP = {"high": "高", "高": "高", "medium-high": "中高", "中高": "中高",
            "medium": "中", "中": "中", "low": "低", "低": "低"}


def clean(text):
    """去掉展示文本中的行号与含行号的括号注记。"""
    if not text:
        return ""
    s = str(text)
    s = re.sub(r"（[^（）]*L\d+[^（）]*）", "", s)
    s = re.sub(r"\([^()]*L\d+[^()]*\)", "", s)
    s = re.sub(r"L\d+(?:[/-]\d+)*", "", s)
    s = re.sub(r"[、;；]\s*([)）\]])", r"\1", s)
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"（\s*）|\(\s*\)", "", s)
    return s.strip(" 　、;；，。")


def conf_level(val):
    m = re.match(r"\s*(medium-high|high|medium|low|高|中高|中|低)", str(val or ""), re.I)
    return CONF_MAP[m.group(1).lower()] if m else ""


def purity_line(pur):
    parts = []
    for k, label in PURITY_KEYS:
        v = str(pur.get(k, "未知"))
        icon = next((ICON[key] for key in ICON if v.startswith(key)), "❓")
        parts.append(f"{label} {icon}")
    verdict = clean(pur.get("verdict", ""))
    note = clean(pur.get("note", ""))
    # 四维全未知时补一句"为什么未知"（未成年角色按规范不判定，不是作者没写）
    if all(str(pur.get(k, "未知")).startswith("未知") for k, _ in PURITY_KEYS):
        four = "未知（%s）" % note if note else "未知"
        return f"- **纯洁度**：{four}"
    line = " ｜ ".join(parts)
    return f"- **纯洁度**：{line}" + (f" —— **{verdict}**" if verdict else "")


def render(data, img_dir=None):
    out = [f"# {data.get('book','')} · 人物卡", ""]
    chars = data.get("characters", [])
    n_lei = sum(len(c.get("leidian", [])) for c in chars)
    n_yu = sum(len(c.get("yumen", [])) for c in chars)
    male_n = 1 if (data.get("male_protagonist") or {}).get("name") else 0
    out.append(f"> 来源：{data.get('source','')} ｜ 生成：{data.get('generated_at','')} ｜ "
               f"{len(chars) + male_n} 角色 ｜ 雷点 {n_lei} 条 ｜ 郁闷点 {n_yu} 条 ｜ "
               f"{data.get('verify_note') or '全部事实经原文核验'}")
    out.append("")

    male = data.get("male_protagonist", {})
    if male and male.get("name"):
        out.append(f"## 男主：{male.get('name','')}")
        aliases = [clean(a if isinstance(a, str) else str(a.get("alias", a)))
                   for a in (male.get("aliases") or male.get("aliases_verified") or [])]
        aliases = [a for a in aliases if a]
        if aliases:
            out.append(f"- **别名**：{'、'.join(aliases)}")
        for k, label in (("identity", "身份"), ("appearance", "外貌"),
                         ("personality", "性格"), ("arc", "成长线")):
            v = clean(male.get(k, ""))
            if v:
                out.append(f"- **{label}**：{v}")
        apq = [clean(q) for q in (male.get("appearance_quotes") or []) if clean(q)]
        if apq:
            out.append("  > 外貌依据：" + " / ".join(f"「{q}」" for q in apq))
        if img_dir and os.path.isdir(img_dir):
            for fn in sorted(os.listdir(img_dir)):
                if fn.lower().endswith((".webp", ".png", ".jpg")) and clean(male["name"]) in fn:
                    out += ["", f"![{male['name']}](人物图/{fn})"]
                    break
        sl = male.get("signature_line")
        if isinstance(sl, dict) and clean(sl.get("quote", "")):
            scene = clean(sl.get("scene", ""))
            out.append(f"- **名场面**：「{clean(sl['quote'])}」" + (f" —— {scene}" if scene else ""))
        events = [clean(e if isinstance(e, str) else e.get("event", ""))
                  for e in (male.get("key_events") or [])]
        events = [e for e in events if e]
        if events:
            out.append("- **关键事件**：")
            out.extend(f"  {idx}. {e}" for idx, e in enumerate(events, 1))
        quotes = [clean(q) for q in (male.get("quotes") or []) if clean(q)]
        if quotes:
            out.append("- **原文摘录**：")
            out.extend(f"  > 「{q}」" for q in quotes)
        out.append("")

    for title, items in (("全书雷点汇总", data.get("book_leidian_summary", [])),
                         ("全书郁闷点汇总", data.get("book_yumen_summary", []))):
        if not items:
            continue
        out.append(f"## {title}")
        for it in items:
            q = clean(it.get("quote", ""))
            # 必须带角色名：汇总里全是「她……」，读者判断不了是谁（老数据没 name 就留空）
            who = clean(it.get("name", ""))
            head = f"`{it.get('category','')}` " + (f"**{who}**：" if who else "")
            out.append(f"- {head}{clean(it.get('evidence',''))}" + (f" 「{q}」" if q else ""))
        out.append("")

    out.append("## 角色卡片")
    for i, c in enumerate(chars):
        out.append("")
        rank = c.get("importance_rank", i + 1)
        rel = clean(c.get("relationship_to_mc", ""))
        head = f"### #{rank} {c.get('name','')}" + (f" —— {rel}" if rel else "")
        out.append(head)
        aliases = [clean(a if isinstance(a, str) else str(a.get("alias", a))) for a in (c.get("aliases_verified") or [])]
        aliases = [a for a in aliases if a]
        if aliases:
            out.append(f"- **别名**：{'、'.join(aliases)}")
        for k, label in (("identity", "身份"), ("appearance", "外貌"), ("personality", "性格"), ("arc", "成长线")):
            v = clean(c.get(k, ""))
            if v:
                out.append(f"- **{label}**：{v}")
        apq = [clean(q) for q in (c.get("appearance_quotes") or []) if clean(q)]
        if apq:
            out.append("  > 外貌依据：" + " / ".join(f"「{q}」" for q in apq))
        tags = c.get("personality_tags")
        if isinstance(tags, list) and [t for t in tags if clean(t)]:
            out.append(f"- **性格标签**：{'、'.join(clean(t) for t in tags if clean(t))}")
        if img_dir:
            for fn in sorted(os.listdir(img_dir)) if os.path.isdir(img_dir) else []:
                if fn.lower().endswith((".webp", ".png", ".jpg")) and clean(c.get("name", "")) in fn:
                    out.append("")
                    out.append(f"![{c.get('name','')}](人物图/{fn})")
                    break
        sl = c.get("signature_line")
        if isinstance(sl, dict) and clean(sl.get("quote", "")):
            scene = clean(sl.get("scene", ""))
            out.append(f"- **名场面**：「{clean(sl['quote'])}」"
                       + (f" —— {scene}" if scene else ""))
        elif isinstance(sl, str) and clean(sl):
            out.append(f"- **名场面**：「{clean(sl)}」")
        out.append(purity_line(c.get("purity", {})))
        evs = [clean(e) for e in (c.get("purity", {}).get("evidence") or []) if clean(e)]
        if evs:
            out.append("  - 依据：" + "；".join(evs))
        for title2, key, in (("雷点", "leidian"), ("郁闷点", "yumen")):
            items = c.get(key, [])
            if not items:
                continue
            out.append(f"- **{title2}**：")
            for it in items:
                q = clean(it.get("quote", ""))
                out.append(f"  - `{it.get('category','未归类')}` {clean(it.get('evidence',''))}"
                           + (f" 「{q}」" if q else ""))
        events = []
        for e in (c.get("key_events") or []):
            if isinstance(e, dict):
                vol = clean(e.get("volume", ""))
                ev = clean(e.get("event") or e.get("text") or "")
                e = f"（{vol}）{ev}" if vol else ev
            e = clean(e)
            if e:
                events.append(e)
        if events:
            out.append("- **关键事件**：")
            out.extend(f"  {idx}. {e}" for idx, e in enumerate(events, 1))
        quotes = [clean(q) for q in (c.get("quotes") or []) if clean(q)]
        if quotes:
            out.append("- **原文摘录**：")
            out.extend(f"  > 「{q}」" for q in quotes)
        lv = conf_level(c.get("confidence"))
        if lv:
            out.append(f"- **置信度**：{lv}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--img-dir", help="人物图目录；给了就在卡片里嵌图")
    args = ap.parse_args()
    data = json.load(open(args.json, encoding="utf-8"))
    md = render(data, args.img_dir)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[OK] {args.out} ({len(md)} chars)")


if __name__ == "__main__":
    main()
