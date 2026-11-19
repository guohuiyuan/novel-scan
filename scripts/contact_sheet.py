#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
novel-scan: contact_sheet.py —— 把人物图拼成一张联系表，用来目检画风/水印

出图之后、发帖之前跑一次：模型偶尔会在角落画一行「© 某某」画师署名（负向词里虽然
有 signature/watermark，指定画师 tag 后仍会漏），单张看不出来，拼一起一眼就能抓到。

用法:
  python contact_sheet.py --dir <输出目录>/人物图 [-o <输出目录>/_立绘联系表.png] \
      [--cols 5] [--thumb 300] [--fmt webp,jpg]

发现某张有问题：`gen_portraits.py --only <名> --force --seed-salt 1` 单张重出，
别整批重跑（会白花额度，还可能把好的那几张摇坏）。
"""
import argparse
import os
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="图片目录，如 <输出目录>/人物图")
    ap.add_argument("-o", "--out", help="输出 PNG（默认 <dir>/_联系表.png）")
    ap.add_argument("--cols", type=int, default=5)
    ap.add_argument("--thumb", type=int, default=300, help="每张缩略图宽度")
    ap.add_argument("--fmt", default="webp,jpg,png", help="收哪些扩展名")
    a = ap.parse_args()

    exts = tuple("." + e.strip().lower().lstrip(".") for e in a.fmt.split(",") if e.strip())
    files = sorted(f for f in os.listdir(a.dir) if f.lower().endswith(exts))
    if not files:
        print("[ERROR] %s 里没有 %s 图片" % (a.dir, "/".join(exts)))
        return 1
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("[ERROR] 需要 Pillow：pip install pillow（本机可用 miniconda 的 python）")
        return 1

    ims = []
    for f in files:
        try:
            im = Image.open(os.path.join(a.dir, f)).convert("RGB")
        except Exception as e:
            print("[warn] 跳过 %s（%s）" % (f, e))
            continue
        ims.append((os.path.splitext(f)[0], im))
    if not ims:
        print("[ERROR] 一张都读不出来")
        return 1

    tw = a.thumb
    th = max(int(i.height * tw / max(1, i.width)) for _, i in ims)
    rows = (len(ims) + a.cols - 1) // a.cols
    sheet = Image.new("RGB", (a.cols * tw, rows * (th + 28)), "white")
    d = ImageDraw.Draw(sheet)
    for n, (name, im) in enumerate(ims):
        t = im.copy()
        t.thumbnail((tw, th))
        x, y = (n % a.cols) * tw, (n // a.cols) * (th + 28)
        sheet.paste(t, (x + (tw - t.width) // 2, y))
        d.text((x + 6, y + th + 6), name, fill=(25, 25, 25))

    out = a.out or os.path.join(a.dir, "_联系表.png")
    sheet.save(out)
    print("[OK] %d 张 → %s  %d×%d" % (len(ims), out, sheet.width, sheet.height))
    return 0


if __name__ == "__main__":
    sys.exit(main())
