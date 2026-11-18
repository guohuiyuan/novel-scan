#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
novel-scan: detect_dup_range.py —— 找 txt 里「重复收录」的实际行区间

有些盗版全本会把两个版本拼在一起（一本 100 万字读成 200 万字），
后半段与前半段大段逐字相同。扫书没必要把同一段剧情读两遍。

做法：把全文按 window 行分桶，取每桶中间若干 48 字窗口，
在前 window_start 行里查是否原样命中，命中率 > thr 判为重复桶，
再把连续重复桶合并成区间输出。

用法：
  python detect_dup_range.py --novel x.txt [--half 0.5] [--thr 0.6]
"""
import argparse
import json
import random
import sys

WIN = 20          # 采样窗口长度（规范化后的字）
PER_BUCKET = 30   # 每桶采样数
BUCKET = 500      # 分桶行数

# 常见 OCR 误认/易混字：比较前统一，否则同一段文字因「的/地/得」差异匹配不上
NORM_MAP = str.maketrans({"地": "的", "得": "的", "着": "著", "么": "麽",
                          "他": "他", "她": "他", "它": "他"})
PUNCT = "，。！？、；：“”‘’（）《》…—·,.!?;:\"'()<>[]{} \t\r\u3000"


def norm_text(s):
    s = s.translate(NORM_MAP)
    return "".join(ch for ch in s if ch not in PUNCT)


def read_text(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--novel", required=True)
    ap.add_argument("--half", type=float, default=0.53,
                    help="从全文哪个比例之后开始找重复（默认 0.53）")
    ap.add_argument("--thr", type=float, default=0.6, help="判重复的命中率阈值")
    ap.add_argument("--trace", action="store_true", help="打印每个桶的命中率")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    text = read_text(a.novel)
    lines = text.split("\n")
    total = len(lines)
    head_end = int(total * a.half)
    head = norm_text("\n".join(lines[:head_end]))
    rnd = random.Random(20261118)

    ranges = []
    cur = None
    for start in range(head_end, total, BUCKET):
        seg = norm_text("\n".join(lines[start:start + BUCKET]))
        if len(seg) < WIN * 3:
            continue
        picks = [rnd.randrange(0, len(seg) - WIN) for _ in range(PER_BUCKET)]
        hit = sum(1 for p in picks if seg[p:p + WIN] in head)
        rate = hit / len(picks)
        if a.trace:
            print("  L%-7s rate=%.2f %s" % (format(start + 1, ","), rate,
                                            "DUP" if rate >= a.thr else ""))
        dup = rate >= a.thr
        if dup:
            if cur and start <= cur[1] + BUCKET:
                cur = (cur[0], min(start + BUCKET, total))
            else:
                if cur:
                    ranges.append(cur)
                cur = (start + 1, min(start + BUCKET, total))
        else:
            if cur:
                ranges.append(cur)
                cur = None
    if cur:
        ranges.append(cur)

    # 只保留够长的区间（≥3 桶），碎片是误命中
    ranges = [(s, e) for s, e in ranges if e - s >= BUCKET * 3]
    keep = total - sum(e - s + 1 for s, e in ranges)

    if a.json:
        print(json.dumps({"total_lines": total, "head_end": head_end,
                          "dup_ranges": ranges, "keep_lines": keep,
                          "dup_chars": sum(e - s + 1 for s, e in ranges)},
                         ensure_ascii=False))
        return
    print("总行数 %s，前 %.0f%% 作基准（到第 %s 行）"
          % (format(total, ","), a.half * 100, format(head_end, ",")))
    if not ranges:
        print("未发现大段重复收录（可全量扫）")
    for s, e in ranges:
        print("  重复区间：第 %s - %s 行（%s 行）"
              % (format(s, ","), format(e, ","), format(e - s + 1, ",")))
    print("有效行数约 %s（去掉 %s 行）"
          % (format(keep, ","), format(total - keep, ",")))


if __name__ == "__main__":
    sys.exit(main())
