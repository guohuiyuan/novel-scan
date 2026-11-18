#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
novel-scan: assemble_json.py —— 把 json/ 下的单角色片段 + book_info.json 合并成 <书名>_人物数据.json

D 阶段用。它做四件确定性的事，不生成任何新事实：
  1. 收齐 json/*.json（单角色对象），按 importance_rank 排序（缺省排后）
  2. 从角色条目聚合全书级雷点/郁闷点汇总，按 (类别, 事实) 去重
  3. 并入书级字段（book_meta / ratings / blurb / dimension_reviews / side_characters）
     与男主卡（male_protagonist）——来自 --meta 指定的 book_info.json
  4. 用 _prescan/state.json 自动补字数、章数、卷数（书级字段里没写的才补）

用法：
  python assemble_json.py --dir <输出目录>/json --book 书名 --out <输出目录>/<书名>_人物数据.json \
      [--meta <输出目录>/book_info.json] [--source "原文文件名（423章）"] \
      [--male 男主名] [--verify-note "…"]
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys

BOOK_KEYS = ("book_meta", "ratings", "blurb", "dimension_reviews",
             "side_characters", "heroine_overview", "coverage")


def guess_author(source):
    """从 `书名_作者_日期_时间.txt` 这类文件名里猜作者（猜不到返回空）。"""
    base = os.path.splitext(os.path.basename(source or ""))[0]
    parts = [p for p in base.split("_") if p]
    if len(parts) >= 2 and not re.fullmatch(r"\d{6,8}", parts[1]):
        return parts[1]
    return ""


def prescan_facts(out_path):
    """从 <out>/_prescan/state.json 取字数/行数/章数/卷数。"""
    p = os.path.join(os.path.dirname(os.path.abspath(out_path)), "_prescan", "state.json")
    if not os.path.exists(p):
        return {}
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}
    chars = d.get("chars") or 0
    return {"word_count": "%.1f 万字" % (chars / 1e4) if chars else "",
            "chapters": d.get("chapters") or 0,
            "volumes": d.get("volumes") or 0,
            "lines": d.get("lines") or 0,
            "dup_chapter_nums": d.get("dup_chapter_nums") or 0,
            "dup_text_overlap": d.get("dup_text_overlap") or 0,
            "chapters_dedup": d.get("chapters_dedup") or 0}


def load_meta(path):
    if not path:
        return {}
    if not os.path.exists(path):
        print("[WARN] 找不到书级字段文件：%s（跳过 book_meta/ratings/简介/男主）" % path)
        return {}
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception as e:
        print("[WARN] %s 解析失败：%s" % (path, e))
        return {}


def norm_male(m):
    """男主卡：允许只写 name/identity/arc，其余字段留空但不丢。"""
    if not isinstance(m, dict) or not m.get("name"):
        return {}
    out = {"name": m.get("name", ""), "aliases": m.get("aliases") or m.get("aliases_verified") or [],
           "identity": m.get("identity", ""), "appearance": m.get("appearance", ""),
           "appearance_quotes": m.get("appearance_quotes") or [],
           "appearance_prompt": m.get("appearance_prompt", ""),
           "personality": m.get("personality", ""), "arc": m.get("arc") or m.get("growth", ""),
           "relationship_to_mc": m.get("relationship_to_mc", ""),
           "key_events": m.get("key_events") or [], "quotes": m.get("quotes") or [],
           "signature_line": m.get("signature_line") or {},
           "confidence": m.get("confidence", "")}
    return {k: v for k, v in out.items() if v not in ("", [], {}, None)}


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


def _flat(v):
    """老产物里 evidence/quote 有写成 list 的，统一压成字符串（否则聚合时 unhashable）。"""
    if isinstance(v, list):
        return "；".join(str(x) for x in v if x)
    return "" if v is None else str(v)


def aggregate(chars, key):
    seen, out = set(), []
    for c in chars:
        for it in (c.get(key) or []):
            if not isinstance(it, dict):
                continue
            ev = _flat(it.get("evidence"))
            sig = (_flat(it.get("category")), ev[:40])
            if sig in seen:
                continue
            seen.add(sig)
            out.append({"category": _flat(it.get("category")), "evidence": ev,
                        "quote": _flat(it.get("quote"))})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="单角色 JSON 所在目录")
    ap.add_argument("--book", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--source", default="")
    ap.add_argument("--meta", help="书级字段文件 book_info.json（book_meta/ratings/blurb/"
                                   "dimension_reviews/side_characters/male_protagonist）")
    ap.add_argument("--male", help="男主名（从角色里摘出来放到 male_protagonist）")
    ap.add_argument("--verify-note", default="")
    a = ap.parse_args()

    chars = load_chars(a.dir)
    meta = load_meta(a.meta)
    if not chars and not meta:
        print("[ERROR] %s 下没有可用的角色 JSON，也没有书级字段" % a.dir)
        return 1

    # 男主：优先用 book_info.json 里的完整卡，其次从角色片段里摘
    male = norm_male(meta.get("male_protagonist"))
    if a.male:
        hit = [c for c in chars if c.get("name") == a.male]
        if hit:
            m = hit[0]
            if not male:
                male = norm_male({"name": m["name"], "aliases": m.get("aliases_verified", []),
                                  "identity": m.get("identity", ""),
                                  "appearance": m.get("appearance", ""),
                                  "personality": m.get("personality", ""),
                                  "arc": m.get("arc", ""), "quotes": m.get("quotes", [])})
            chars = [c for c in chars if c.get("name") != a.male]

    # 重新编号：女主从 1 起连续编号，男主固定占 0（出图是 00_男主.webp）。
    # 子代理各自填 importance_rank，必然出现重复值与空号（实测一次 2..12、缺 01），
    # 图片文件名跟着 rank 走，空号会让人以为漏了角色——所以这里强制压平。
    chars.sort(key=lambda c: (c.get("importance_rank", 999), c.get("name", "")))
    before = [c.get("importance_rank") for c in chars]
    for i, c in enumerate(chars, 1):
        c["importance_rank"] = i
    if before and before != list(range(1, len(before) + 1)):
        print(f"[assemble] 子代理给的 rank 有重复/空号（{before}），已压平为 1..{len(chars)}；"
              f"人物图文件名会跟着变，重新出图或改名后**必须重渲染文档**")

    out = {
        "book": a.book,
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": a.source,
        "male_protagonist": male,
        "characters": chars,
        "book_leidian_summary": aggregate(chars, "leidian"),
        "book_yumen_summary": aggregate(chars, "yumen"),
    }

    # 书级字段
    for k in BOOK_KEYS:
        if meta.get(k):
            out[k] = meta[k]
    bm = dict(meta.get("book_meta") or {})
    facts = prescan_facts(a.out)
    bm.setdefault("title", a.book)
    user_word = bm.get("word_count")
    for k in ("word_count", "chapters", "volumes"):
        if not bm.get(k) and facts.get(k):
            bm[k] = facts[k]
    if facts.get("dup_text_overlap", 0) >= 0.12 and not user_word:
        print("[WARN] 预扫检测到重复收录（后半本有 %.0f%% 正文与前半本重复，去重后约 %d 章），"
              "上面自动填的字数/章数偏高；请在 book_info.json 里写明真实字数与章数。"
              % (facts["dup_text_overlap"] * 100, facts.get("chapters_dedup", 0)))
    if not bm.get("author") and a.source:
        bm["author"] = guess_author(a.source)
    if not bm.get("status"):
        bm["status"] = "未知"
    out["book_meta"] = bm
    if a.verify_note:
        out["verify_note"] = a.verify_note

    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    n_lei = len(out["book_leidian_summary"])
    n_yu = len(out["book_yumen_summary"])
    print("[OK] %s（%d 角色 ｜ 全书雷点 %d ｜ 郁闷点 %d）" %
          (a.out, len(chars) + (1 if male else 0), n_lei, n_yu))

    # 缺件点名（这些会直接决定成品能不能发）
    miss = []
    if not male:
        miss.append("男主卡（male_protagonist）")
    if not out.get("ratings"):
        miss.append("8 维评分（ratings）")
    if not out.get("blurb"):
        miss.append("简介（blurb）")
    if not out.get("dimension_reviews"):
        miss.append("分维度点评（dimension_reviews）")
    if not bm.get("genre"):
        miss.append("题材（book_meta.genre）")
    if miss:
        print("[WARN] 书级字段缺：%s —— 补齐后书评报告会缺章节" % "、".join(miss))
    no_prompt = [c["name"] for c in chars if not (c.get("appearance_prompt") or "").strip()]
    if no_prompt:
        print("[WARN] 缺 appearance_prompt（出图会跳过）：%s" % "、".join(no_prompt))
    no_line = [c["name"] for c in chars + ([male] if male else [])
               if not (isinstance(c.get("signature_line"), dict) and
                       (c["signature_line"].get("quote") or "").strip())]
    if no_line:
        print("[WARN] 缺 signature_line（做视频会缺台词）：%s" % "、".join(no_line))
    return 0


if __name__ == "__main__":
    sys.exit(main())
