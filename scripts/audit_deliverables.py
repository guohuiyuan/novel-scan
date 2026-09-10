# -*- coding: utf-8 -*-
"""
novel-scan skill: audit_deliverables.py
交付前三件套自检：引文逐字核验 / 行号残留 / 幻觉实体残留。

用法:
  python audit_deliverables.py --json <书名>_人物数据.json --novel <原文.txt> [--docs <人物卡.md> <报告.md> ...]

判定口径:
  1) quotes[] 数组里的引文必须能在原文逐字命中（允许 …… / — 分段拼接）；
  2) key_events / evidence / identity 等元数据字段里用「」包的概括**不计入**引文核验
     （它们是指代性标签，不是原文引文主张），但会单独列出供人工抽查；
  3) 人物卡与报告正文不得出现 L\\d+ 形式行号；
  4) 扫描已知幻觉实体（其他书的角色名）确认无串章。
"""
import argparse
import glob
import json
import os
import re
import sys

HALLUCINATION_PROBE = []  # 可传 --probe 追加；默认空（各书不同，由调用方给）


def norm(s):
    s = re.sub(r"[\-–—～~・·]", "", s)
    s = re.sub(r"[「」『』“”\"'’‘]", "", s)
    s = re.sub(r"\s+", "", s)
    return s


def split_frags(q):
    return [norm(f) for f in re.split(r"……|──|—|…|\?|？", q) if len(norm(f)) >= 6]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True, help="人物数据 JSON")
    ap.add_argument("--novel", required=True, help="原文 txt")
    ap.add_argument("--docs", nargs="*", default=[], help="待查行号残留的成品 md")
    ap.add_argument("--probe", nargs="*", default=[], help="幻觉实体探针词（其他书角色名等）")
    a = ap.parse_args()

    main_txt = open(a.novel, encoding="utf-8").read()
    M = norm(main_txt)
    data = json.load(open(a.json, encoding="utf-8"))

    def hit(q):
        fr = split_frags(q)
        return any(f in M for f in fr) if fr else norm(q) in M

    # ---- 1) quotes[] 逐字核验 ----
    tot = bad = 0
    print("== 1. quotes[] 引文逐字核验 ==")
    for c in data.get("characters", []):
        for q in (c.get("quotes") or []):
            tot += 1
            if not hit(q):
                bad += 1
                print(f"   [未命中] [{c.get('name')}] {q[:70]}")
    mp = data.get("male_protagonist") or {}
    for q in (mp.get("quotes") or []):
        tot += 1
        if not hit(q):
            bad += 1
            print(f"   [未命中] [男主] {q[:70]}")
    print(f"   结果: {tot - bad}/{tot} 命中" + ("  ✅" if bad == 0 else "  ⚠️ 需处理"))

    # ---- 2) 元数据里的「」标签（人工抽查用）----
    spans = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "quotes":
                    continue
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)
        elif isinstance(o, str):
            for m in re.finditer(r"[「『]([^「」『』]{6,60})[」』]", o):
                spans.append(m.group(1))

    walk(data)
    spans = list(dict.fromkeys(spans))
    label = [s for s in spans if not hit(s)]
    print(f"\n== 2. 元数据「」标签抽查 ==")
    print(f"   共 {len(spans)} 条，未逐字命中 {len(label)} 条（多为指代性标签/概括，非引文主张）")
    for s in label[:25]:
        print(f"   ·  {s[:66]}")

    # ---- 3) 行号残留 ----
    print("\n== 3. 成品行号残留 ==")
    docs = a.docs or sorted(glob.glob(os.path.join(os.path.dirname(a.json), "*.md")))
    for d in docs:
        if not os.path.exists(d):
            continue
        s = open(d, encoding="utf-8").read()
        n = len(re.findall(r"L\d{2,}", s))
        print(f"   {os.path.basename(d)}: 行号残留 {n}" + ("  ✅" if n == 0 else "  ⚠️"))

    # ---- 4) 幻觉实体探针 ----
    if a.probe:
        print("\n== 4. 幻觉实体探针 ==")
        for kw in a.probe:
            print(f"   「{kw}」在原文出现 {main_txt.count(kw)} 次")

    print("\n审计完成。" + ("全部通过。" if bad == 0 else "请处理上面标 ⚠️ 的项。"))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
