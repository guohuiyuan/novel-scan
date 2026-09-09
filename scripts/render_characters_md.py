# -*- coding: utf-8 -*-
"""
novel-scan skill: render_characters_md.py
把人物数据 JSON 渲染成人物卡片 Markdown（无行号、不显示剔除别名、置信度只显示等级）。

用法:
  python render_characters_md.py --json <书名>_人物数据.json --out <书名>_人物卡.md
"""
import argparse
import json
import re

PURITY_KEYS = [("chu", "处"), ("jingshen_chu", "精神初"), ("hunyin", "初婚"), ("chumo", "初摸")]
ICON = {"处": "✅", "非处": "❌", "初": "✅", "非初": "❌", "初婚": "✅", "有婚史婚约": "❌",
        "初摸": "✅", "被非男主触碰": "❌", "不适用": "➖", "未知": "❓"}
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
    verdict = pur.get("verdict", "")
    line = " ｜ ".join(parts)
    return f"- **纯洁度**：{line}" + (f" —— **{clean(verdict)}**" if verdict else "")


def render(data):
    out = [f"# {data.get('book','')} · 人物卡", ""]
    chars = data.get("characters", [])
    n_lei = sum(len(c.get("leidian", [])) for c in chars)
    n_yu = sum(len(c.get("yumen", [])) for c in chars)
    out.append(f"> 来源：{data.get('source','')} ｜ 生成：{data.get('generated_at','')} ｜ "
               f"{len(chars)} 角色 ｜ 雷点 {n_lei} 条 ｜ 郁闷点 {n_yu} 条 ｜ 全部事实经原文核验")
    out.append("")

    male = data.get("male_protagonist", {})
    if male:
        out.append(f"## 男主：{male.get('name','')}")
        if male.get("identity"):
            out.append(f"- **身份**：{clean(male['identity'])}")
        if male.get("personality"):
            out.append(f"- **性格**：{clean(male['personality'])}")
        if male.get("arc"):
            out.append(f"- **成长线**：{clean(male['arc'])}")
        out.append("")

    for title, items in (("全书雷点汇总", data.get("book_leidian_summary", [])),
                         ("全书郁闷点汇总", data.get("book_yumen_summary", []))):
        if not items:
            continue
        out.append(f"## {title}")
        for it in items:
            q = clean(it.get("quote", ""))
            out.append(f"- `{it.get('category','')}` {clean(it.get('evidence',''))}"
                       + (f" 「{q}」" if q else ""))
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
    args = ap.parse_args()
    data = json.load(open(args.json, encoding="utf-8"))
    md = render(data)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[OK] {args.out} ({len(md)} chars)")


if __name__ == "__main__":
    main()
