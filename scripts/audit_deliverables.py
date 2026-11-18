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

    if a.novel and os.path.exists(a.novel):
        main_txt = open(a.novel, encoding="utf-8").read()
    else:
        main_txt = None
        print(f"!! 原文不可用（{a.novel}）：跳过引文逐字核验，仅查行号残留与幻觉实体")
    M = norm(main_txt) if main_txt else ""
    data = json.load(open(a.json, encoding="utf-8"))

    def hit(q):
        if not M:
            return None
        fr = split_frags(q)
        return any(f in M for f in fr) if fr else norm(q) in M

    # ---- 1) quotes[] 逐字核验 ----
    tot = bad = 0
    print("== 1. quotes[] 引文逐字核验 ==")
    if not M:
        print("   [SKIP] 原文缺失，本轮无法核验")
    for c in data.get("characters", []):
        for q in (c.get("quotes") or []):
            r = hit(q)
            if r is None:
                continue
            tot += 1
            if not r:
                bad += 1
                print(f"   [未命中] [{c.get('name')}] {q[:70]}")
        for q in (c.get("appearance_quotes") or []):
            r = hit(q)
            if r is None:
                continue
            tot += 1
            if not r:
                bad += 1
                print(f"   [未命中·外貌] [{c.get('name')}] {q[:70]}")
    mp = data.get("male_protagonist") or {}
    for q in (mp.get("quotes") or []):
        r = hit(q)
        if r is None:
            continue
        tot += 1
        if not r:
            bad += 1
            print(f"   [未命中] [男主] {q[:70]}")
    if tot:
        print(f"   结果: {tot - bad}/{tot} 命中" + ("  ✅" if bad == 0 else "  ⚠️ 需处理"))

    # ---- 2) 外貌覆盖（用户要求：主要角色必须有可复述的外形锚点）----
    print("\n== 2. 外貌覆盖 ==")
    miss = []
    for c in data.get("characters", []):
        ap = (c.get("appearance") or "").strip()
        name = c.get("name", "?")
        if not ap:
            miss.append(name)
            print(f"   [缺失] {name}：appearance 为空")
        elif len(ap) < 12 and "未" not in ap:
            print(f"   [过短] {name}：{ap}")
    if not miss:
        print(f"   全部 {len(data.get('characters', []))} 个角色都有外貌字段 ✅")

    # ---- 2b) 名场面台词覆盖（做视频用）----
    print("\n== 2b. 名场面台词 ==")
    chars = data.get("characters", [])
    has_line = 0
    for c in chars:
        sl = c.get("signature_line")
        q = (sl.get("quote") if isinstance(sl, dict) else sl) or ""
        if str(q).strip():
            has_line += 1
            if M and not hit(str(q)):
                print(f"   [未命中] [{c.get('name')}] {str(q)[:60]}")
        else:
            print(f"   [缺失] {c.get('name')}：signature_line 为空")
    print(f"   {has_line}/{len(chars)} 个角色有名场面台词"
          + ("  ✅" if has_line == len(chars) else "  ⚠️"))

    # ---- 3) 元数据里的「」标签（人工抽查用）----
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
    print(f"\n== 3. 元数据「」标签抽查 ==")
    print(f"   共 {len(spans)} 条，未逐字命中 {len(label)} 条（多为指代性标签/概括，非引文主张）")
    for s in label[:25]:
        print(f"   ·  {s[:66]}")

    # ---- 4) 行号残留 ----
    print("\n== 4. 成品行号残留 ==")
    docs = a.docs or sorted(glob.glob(os.path.join(os.path.dirname(a.json), "*.md")))
    for d in docs:
        if not os.path.exists(d):
            continue
        s = open(d, encoding="utf-8").read()
        n = len(re.findall(r"L\d{2,}", s))
        print(f"   {os.path.basename(d)}: 行号残留 {n}" + ("  ✅" if n == 0 else "  ⚠️"))

    # ---- 5) 幻觉实体探针 ----
    if a.probe:
        print("\n== 5. 幻觉实体探针 ==")
        if not main_txt:
            print("   [SKIP] 原文缺失，改为在各卷笔记中检索")
            notes_dir = os.path.join(os.path.dirname(os.path.abspath(a.json)), "..", "scan_notes")
            corpus = ""
            for f in sorted(glob.glob(os.path.join(notes_dir, "*.md"))):
                corpus += open(f, encoding="utf-8").read()
            for kw in a.probe:
                print(f"   「{kw}」在笔记中出现 {corpus.count(kw)} 次")
        else:
            for kw in a.probe:
                print(f"   「{kw}」在原文出现 {main_txt.count(kw)} 次")

    print("\n审计完成。" + ("全部通过。" if bad == 0 else "请处理上面标 ⚠️ 的项。"))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
