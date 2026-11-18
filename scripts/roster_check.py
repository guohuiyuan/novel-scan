#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
novel-scan: roster_check.py —— 从分块笔记里汇总「出场角色」，核对有没有漏人

扫书最常见的漏项是女主：块扫时某个女角只在两三个块里出现，
逐人物汇总阶段容易被忘掉。这个脚本把 21 份 scan_notes 的
「## 2. 出场角色」表合并，给出：

  1. 每个名字出现在哪些块、被写成什么身份（人工判断男女与重要度）
  2. 与现有 json/ 里已定稿的角色比对，列出「有人但没 JSON」的缺口
  3. 与 _prescan/characters.tsv 的频次表比对，标出候选里有、笔记里没提的（反向漏检）

用法：
  python roster_check.py --notes <目录>/scan_notes --json <目录>/json \
      [--freq <目录>/_prescan/characters.tsv]
"""
import argparse
import glob
import json
import os
import re
import sys

ROW = re.compile(r"^\s*\|(.*)\|\s*$")
SEP = re.compile(r"^[\s|:-]+$")


def parse_notes(notes_dir):
    """返回 {name: {"blocks": [...], "roles": [...], "first": [...]}}"""
    people = {}
    for path in sorted(glob.glob(os.path.join(notes_dir, "*.md"))):
        block = os.path.splitext(os.path.basename(path))[0]
        lines = open(path, encoding="utf-8").read().split("\n")
        in_sec = False
        for ln in lines:
            s = ln.rstrip()
            if s.startswith("## "):
                in_sec = ("出场角色" in s)
                continue
            if not in_sec:
                continue
            m = ROW.match(s)
            if not m or SEP.match(s):
                continue
            cells = [c.strip() for c in m.group(1).split("|")]
            if len(cells) < 3:
                continue
            name = cells[0]
            if not name or name in ("姓名", "---") or set(name) <= set("-: "):
                continue
            infos = people.setdefault(name, {"blocks": [], "roles": [], "first": []})
            if block not in infos["blocks"]:
                infos["blocks"].append(block)
            role = cells[1] if len(cells) > 1 else ""
            if role and role not in infos["roles"]:
                infos["roles"].append(role)
            first = cells[3] if len(cells) > 3 else ""
            if first.startswith("是") and block not in infos["first"]:
                infos["first"].append(block)
    return people


def split_alias(name):
    """「曾柔（柔柔、小辣椒）」→ 主名 + 别名列表"""
    m = re.match(r"^(.+?)[（(](.+?)[)）]\s*$", name)
    if not m:
        return name, []
    main = m.group(1).strip()
    aliases = [a.strip() for a in re.split(r"[、,，/]", m.group(2)) if a.strip()]
    return main, aliases


def load_json_names(json_dir):
    out = {}
    if not os.path.isdir(json_dir):
        return out
    for p in glob.glob(os.path.join(json_dir, "*.json")):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        name = d.get("name")
        if not name:
            continue
        out[name] = d
        for a in (d.get("aliases_verified") or []):
            out.setdefault("__alias__" + a, d)
    return out


def load_freq(path):
    freq = {}
    if not path or not os.path.exists(path):
        return freq
    for i, ln in enumerate(open(path, encoding="utf-8")):
        if i == 0:
            continue
        parts = ln.rstrip("\n").split("\t")
        if len(parts) >= 2 and parts[1].isdigit():
            freq[parts[0]] = int(parts[1])
    return freq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--notes", required=True)
    ap.add_argument("--json", required=True)
    ap.add_argument("--freq")
    ap.add_argument("--min-blocks", type=int, default=2,
                    help="至少出现在几个块里才算「主要候选」")
    a = ap.parse_args()

    people = parse_notes(a.notes)
    done = load_json_names(a.json)
    freq = load_freq(a.freq)

    merged = {}
    for raw, info in people.items():
        main, aliases = split_alias(raw)
        if main in done or any(x in done for x in aliases):
            continue
        slot = merged.setdefault(main, {"blocks": set(), "roles": [], "aliases": set()})
        slot["blocks"] |= set(info["blocks"])
        slot["aliases"] |= set(aliases)
        for r in info["roles"]:
            if r not in slot["roles"]:
                slot["roles"].append(r)

    rows = []
    for name, info in merged.items():
        rows.append((name, len(info["blocks"]), sorted(info["blocks"]),
                     freq.get(name, 0), "；".join(info["roles"][:2]),
                     "、".join(sorted(info["aliases"])[:3])))
    rows.sort(key=lambda r: (-r[3], -r[1]))

    print("== 有出场记录但还没有人物 JSON 的角色：%d 个 ==" % len(rows))
    print("%-10s %-6s %-5s %-22s %s" % ("姓名", "块数", "频次", "出现块", "身份线索"))
    for name, nb, blocks, f, role, al in rows:
        flag = "★" if nb >= a.min_blocks or f >= 300 else " "
        print("%s%-9s %-6d %-5d %-22s %s"
              % (flag, name, nb, f, ",".join(b.replace("块", "") for b in blocks[:6]),
                 (role[:46] + ("…" if len(role) > 46 else ""))))
    print("\n★ = 出现在 ≥%d 块 或 频次 ≥300，优先补卡" % a.min_blocks)

    # 反向：频次表里高但笔记里一次没提
    if freq:
        miss = [(n, f) for n, f in freq.items()
                if f >= 200 and n not in people
                and not any(n in k for k in people)]
        if miss:
            print("\n== 频次高但 21 块笔记里从未出现（可能漏扫/别名）==")
            for n, f in sorted(miss, key=lambda kv: -kv[1]):
                print("  %s %d" % (n, f))

    print("\n已定稿 JSON：%s" % "、".join(sorted(k for k in done if not k.startswith("__alias__"))))


if __name__ == "__main__":
    sys.exit(main())
