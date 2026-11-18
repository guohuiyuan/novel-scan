#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
novel-scan: assemble_json.py —— 把 json/ 下的单角色片段合并成 <书名>_人物数据.json

D 阶段用。它做三件确定性的事，不生成任何新事实：
  1. 收齐 json/*.json（单角色对象），按 importance_rank 排序（缺省排后）
  2. 从角色条目聚合全书级雷点/郁闷点汇总，按 (类别, 事实) 去重
  3. 补齐 book / generated_at / source 三个顶层字段

用法：
  python assemble_json.py --dir <输出目录>/json --book 书名 --out <输出目录>/<书名>_人物数据.json \
      [--source "原文文件名（423章）"] [--male 男主名] [--verify-note "…"]
"""
import argparse
import datetime
import glob
import json
import os
import sys


def load_chars(src_dir):
    chars = []
    for f in sorted(glob.glob(os.path.join(src_dir, "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception as e:
            print("[SKIP] %s：%s" % (os.path.basename(f), e))
            continue
        if not isinstance(d, dict) or not d.get("name"):
            print("[SKIP] %s：不是单角色对象" % os.path.basename(f))
            continue
        d.setdefault("importance_rank", 999)
        chars.append(d)
    return chars


def aggregate(chars, key):
    seen, out = set(), []
    for c in chars:
        for it in (c.get(key) or []):
            if not isinstance(it, dict):
                continue
            sig = (it.get("category", ""), (it.get("evidence") or "")[:40])
            if sig in seen:
                continue
            seen.add(sig)
            out.append({"category": it.get("category", ""),
                        "evidence": it.get("evidence", ""),
                        "quote": it.get("quote", "")})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="单角色 JSON 所在目录")
    ap.add_argument("--book", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--source", default="")
    ap.add_argument("--male", help="男主名（从角色里摘出来放到 male_protagonist）")
    ap.add_argument("--verify-note", default="")
    a = ap.parse_args()

    chars = load_chars(a.dir)
    if not chars:
        print("[ERROR] %s 下没有可用的角色 JSON" % a.dir)
        return 1

    male = {}
    if a.male:
        hit = [c for c in chars if c.get("name") == a.male]
        if hit:
            m = hit[0]
            male = {"name": m["name"], "aliases": m.get("aliases_verified", []),
                    "identity": m.get("identity", ""), "appearance": m.get("appearance", ""),
                    "personality": m.get("personality", ""), "arc": m.get("arc", ""),
                    "quotes": m.get("quotes", [])}
            chars = [c for c in chars if c.get("name") != a.male]

    chars.sort(key=lambda c: (c.get("importance_rank", 999), c.get("name", "")))
    for i, c in enumerate(chars, 1):
        c["importance_rank"] = i + (1 if male else 0)

    out = {
        "book": a.book,
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": a.source,
        "male_protagonist": male,
        "characters": chars,
        "book_leidian_summary": aggregate(chars, "leidian"),
        "book_yumen_summary": aggregate(chars, "yumen"),
    }
    if a.verify_note:
        out["verify_note"] = a.verify_note

    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    n_lei = len(out["book_leidian_summary"])
    n_yu = len(out["book_yumen_summary"])
    print("[OK] %s（%d 角色 ｜ 全书雷点 %d ｜ 郁闷点 %d）" %
          (a.out, len(chars) + (1 if male else 0), n_lei, n_yu))
    no_prompt = [c["name"] for c in chars if not (c.get("appearance_prompt") or "").strip()]
    if no_prompt:
        print("[WARN] 缺 appearance_prompt（出图会跳过）：%s" % "、".join(no_prompt))
    no_line = [c["name"] for c in chars
               if not (isinstance(c.get("signature_line"), dict) and
                       (c["signature_line"].get("quote") or "").strip())]
    if no_line:
        print("[WARN] 缺 signature_line（做视频会缺台词）：%s" % "、".join(no_line))
    return 0


if __name__ == "__main__":
    sys.exit(main())
