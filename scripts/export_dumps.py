# -*- coding: utf-8 -*-
"""
novel-scan skill: export_dumps.py
从 novel-digest 四阶段产物导出「逐角色事实 dump」，供重写式清洗子代理使用。

用法:
  python export_dumps.py --project <novel-digest目录> --book <书名关键字> \
      --novel <原文txt路径> --out <dump输出目录> --chars <角色配置.json>

角色配置 JSON 格式:
[
  {"id":"00","name":"友崎文也","male":true},
  {"id":"01","name":"日南葵","aliases":["日南学姊","会长"],
   "fragments":[], "suspects":["日南绘里香","绀野绘里香"]}
]
- fragments: SPLIT-PAIR 碎片 key，其事实/别名全部并入本章 dump
- suspects : 疑似碎片或串章实体，只导出统计信息供子代理 grep 核实
"""
import argparse
import bisect
import json
import os
import sys


def read_text(path):
    for enc in ("utf-8", "gb18030"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"无法解码: {path}")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_latest(results, prefix):
    cands = [d for d in os.listdir(results) if d.startswith(prefix)]
    if not cands:
        raise FileNotFoundError(f"results 下找不到 {prefix}*")
    return os.path.join(results, sorted(cands)[-1])


def find_file(d, keyword):
    for name in sorted(os.listdir(d)):
        if keyword in name and name.endswith(".json"):
            return os.path.join(d, name)
    raise FileNotFoundError(f"{d} 下找不到 *{keyword}*.json")


def build_line_index(novel_path):
    """返回 (行起始字符偏移数组, 行列表)，用于 chunk 字符偏移 -> 行号。"""
    text = read_text(novel_path)
    lines = text.splitlines()
    offsets = []
    acc = 0
    for ln in lines:
        offsets.append(acc)
        acc += len(ln) + 1
    return offsets, lines


def offset_to_line(offsets, off):
    return bisect.bisect_right(offsets, off)


def fmt_fact(cat, e, idx):
    parts = [f"- [{cat}#{idx}] target={e.get('target', e.get('male', '?'))}"
             f" mutual={e.get('mutual', '-')}" ]
    det = (e.get("detail") or "").strip()
    if det:
        parts.append(f"  细节: {det[:300]}")
    ev = (e.get("evidence") or "").strip().replace("\n", " / ")
    if ev:
        parts.append(f"  证据: 「{ev[:400]}」(chunk {e.get('chunk_index')})")
    return "\n".join(parts)


def export_char(cfg, ctx):
    name = cfg["name"]
    names = {name} | set(cfg.get("aliases", [])) | set(cfg.get("fragments", []))
    out = []
    out.append(f"# DUMP · {cfg['id']} {name}")
    out.append(f"\n> 供重写式清洗使用。所有「chunk N」可换算为原文行号（见文末换算表线索）。事实条目只是线索，可能有幻觉/串章，必须逐条 grep 核对。")

    # 1) 统计画像 (all_female_characters)
    af = ctx["all_female"]
    stat_keys = [name] + cfg.get("fragments", []) + cfg.get("suspects", [])
    out.append("\n## 实体统计（含疑似碎片，需你 grep 核实归属）")
    for k in stat_keys:
        v = af.get(k)
        if not v:
            out.append(f"- {k}: all_female_characters 无此 key")
            continue
        others = ", ".join(v.get("other_names", [])[:20])
        out.append(f"- {k}: count={v.get('count')} avg={v.get('avg_score')}")
        if others:
            out.append(f"  别名: {others}")
        if k == name or k in cfg.get("fragments", []):
            for s in (v.get("summaries") or [])[:12]:
                out.append(f"  · {s[:200]}")

    # 2) heroines profile
    prof = [h for h in ctx["heroines"] if h.get("name") in names]
    for h in prof:
        out.append(f"\n## 流水线角色画像 ({h.get('name')})")
        for key in ("aliases", "importance_rank", "relationship_type", "is_mutual",
                    "heroine_type", "key_interactions", "character_traits", "summary"):
            if h.get(key) is not None:
                out.append(f"- {key}: {h.get(key)}")

    # 3) heroine_facts（本体+碎片）
    fact_entries = [e for e in ctx["heroine_facts"] if e.get("name") in names]
    for fe in fact_entries:
        out.append(f"\n## 扫描事实条目 ({fe.get('name')})")
        total = 0
        for cat, items in fe.get("facts", {}).items():
            for i, e in enumerate(items, 1):
                out.append(fmt_fact(cat, e, i))
                total += 1
        if total == 0:
            out.append("（此 key 事实条目为 0——注意这可能本身就是漏抽信号，请用 extra_relations 和 grep 补）")

    # 4) extra_relations
    er = [e for e in ctx["extra_relations"] if e.get("female") in names]
    out.append(f"\n## 互动关系条目 ({len(er)} 条)")
    for e in er:
        det = (e.get("detail") or "")[:220]
        ev = (e.get("evidence") or "").strip().replace("\n", " / ")[:300]
        ml = "男主" if e.get("is_male_lead") else e.get("male", "?")
        out.append(f"- vs {ml}: {det} 证据:「{ev}」(chunk {e.get('chunk_index')})")

    # 5) purity 判定
    for p in ctx["purity"]:
        if p.get("name") in names:
            out.append(f"\n## 纯洁度判定 ({p.get('name')})")
            out.append("```json\n" + json.dumps(p, ensure_ascii=False, indent=1)[:1500] + "\n```")

    # 6) 男主补充
    if cfg.get("male"):
        mp = ctx["male"]
        out.append("\n## 男主画像")
        out.append(json.dumps(mp, ensure_ascii=False, indent=1)[:2000])

    # 7) chunk 换算线索
    if ctx.get("chunk_lines"):
        out.append("\n## chunk_index -> 原文行号 对照")
        for ck, (l1, l2) in sorted(ctx["chunk_lines"].items()):
            out.append(f"- chunk {ck}: 约 {l1}-{l2} 行")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--book", required=True)
    ap.add_argument("--novel", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--chars", required=True)
    args = ap.parse_args()

    results = os.path.join(args.project, "results")
    heroine_dir = find_latest(results, f"{args.book}_heroine_")
    scan_dir = find_latest(results, f"{args.book}_scan_")

    detailed = load_json(find_file(heroine_dir, "_detailed_"))
    raw = load_json(find_file(scan_dir, "raw_data"))
    vs_path = [f for f in os.listdir(scan_dir) if f.startswith("VERIFIED_SUMMARY")]
    vs = load_json(os.path.join(scan_dir, sorted(vs_path)[-1])) if vs_path else {}
    manifest = load_json(find_file(scan_dir, "chunk_manifest"))

    offsets, _ = build_line_index(args.novel)
    chunk_lines = {}
    for ch in manifest.get("chunks", []):
        l1 = offset_to_line(offsets, ch.get("core_start", 0))
        l2 = offset_to_line(offsets, ch.get("core_end", 0))
        chunk_lines[ch["chunk_index"]] = (l1, l2)

    ctx = {
        "all_female": detailed.get("all_female_characters", {}),
        "heroines": (detailed.get("heroine_result", {}) or {}).get("heroines", []),
        "male": detailed.get("male_protagonist", {}),
        "heroine_facts": raw.get("heroine_facts", []),
        "extra_relations": raw.get("extra_relations", []),
        "purity": vs.get("heroines_purity", []),
        "chunk_lines": chunk_lines,
    }

    os.makedirs(args.out, exist_ok=True)
    chars = load_json(args.chars)
    for cfg in chars:
        md = export_char(cfg, ctx)
        path = os.path.join(args.out, f"{cfg['id']}_{cfg['name']}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"[OK] {path} ({len(md)} chars)")
    print(f"共 {len(chars)} 个 dump -> {args.out}")


if __name__ == "__main__":
    sys.exit(main())
