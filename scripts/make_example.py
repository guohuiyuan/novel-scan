# -*- coding: utf-8 -*-
"""
novel-scan: make_example.py —— 把一次真实输出做成 `examples/<书名>/` 展示副本

为什么要把产物抄进仓库：
  - 用户看 SKILL.md 只有流程，不知道这东西到底长什么样；放一份完整样例，
    装完就知道「要拿到什么」，也方便对照自己的输出判断哪一步没做到。
  - 但原样抄会带进 16MB 人物图 + 700KB 预扫中间产物，仓库会被撑爆。
    所以这里把人物图降采样（默认宽 560、webp q82，单张约 40-60KB），
    md / json 逐字保留（图片用相对路径，目录结构照搬，链接不断）。

用法：
  python make_example.py --src <某本书的输出目录> --dst examples/都市良人行
  python make_example.py --src <输出目录> --dst examples/xxx --max-width 480 --quality 78
  python make_example.py --src <输出目录> --dst examples/xxx --no-intermediates

约定：
  - 交付物全带：`<书名>_书评.md`、`<书名>_人物卡.md`、`<书名>_人物数据.json`、
    `封面.*` + `_封面.json`、`人物图/`；
  - 中间产物默认只抽**一份**角色 JSON + **一份**分块笔记（放 `中间产物样例/`），
    够看清格式，又不搬整条流水线；
  - 末尾打印体积对比，超 3MB 会提醒（GitHub 单文件 100MB 上限，但仓库别养到几十 MB）。
"""
import argparse
import glob
import json
import os
import shutil
import sys

IMG_EXT = (".webp", ".png", ".jpg", ".jpeg")


def human(n):
    for unit in ("B", "KB", "MB"):
        if n < 1024 or unit == "MB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024.0


def dir_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def shrink(src, dst, max_width, quality):
    """webp/png/jpg 统一转 webp 并限宽；PIL 缺失时原样复制。"""
    try:
        from PIL import Image
    except ImportError:
        shutil.copy2(src, dst)
        return "copy"

    im = Image.open(src)
    im = im.convert("RGB") if im.mode not in ("RGB", "RGBA") else im
    if im.width > max_width:
        im = im.resize((max_width, round(im.height * max_width / im.width)), Image.LANCZOS)
    base = os.path.splitext(dst)[0]
    out = base + ".webp"
    im.save(out, "WEBP", quality=quality, method=6)
    if os.path.abspath(out) != os.path.abspath(dst) and os.path.exists(dst):
        os.remove(dst)
    return "webp"


def copy_deliverables(src, dst, max_width, quality):
    made = []
    os.makedirs(dst, exist_ok=True)

    for pat in ("*_书评.md", "*_人物卡.md", "*_人物数据.json", "_封面.json", "封面.*"):
        for p in glob.glob(os.path.join(src, pat)):
            if os.path.isfile(p) and os.path.splitext(p)[1].lower() in (".md", ".json") + IMG_EXT:
                shutil.copy2(p, os.path.join(dst, os.path.basename(p)))
                made.append(os.path.basename(p))

    # 人物图：同名目录照搬，图降采样
    src_img = os.path.join(src, "人物图")
    if os.path.isdir(src_img):
        dst_img = os.path.join(dst, "人物图")
        os.makedirs(dst_img, exist_ok=True)
        n = 0
        for name in sorted(os.listdir(src_img)):
            sp = os.path.join(src_img, name)
            if not os.path.isfile(sp):
                continue
            if os.path.splitext(name)[1].lower() in IMG_EXT:
                shrink(sp, os.path.join(dst_img, name), max_width, quality)
                n += 1
            else:
                shutil.copy2(sp, os.path.join(dst_img, name))
        made.append(f"人物图/（{n} 张，限宽 {max_width}px）")
    return made


def copy_intermediates(src, dst, pick_char=None):
    """抽一份角色 JSON + 一份分块笔记，够看清格式即可。"""
    out = os.path.join(dst, "中间产物样例")
    os.makedirs(out, exist_ok=True)
    made = []

    cdir = os.path.join(src, "json")
    if os.path.isdir(cdir):
        cands = sorted(glob.glob(os.path.join(cdir, "*.json")))
        if pick_char:
            cands.sort(key=lambda p: 0 if pick_char in os.path.basename(p) else 1)
        if cands:
            shutil.copy2(cands[0], os.path.join(out, "角色片段_" + os.path.basename(cands[0])))
            made.append("角色片段_" + os.path.basename(cands[0]))

    notes = sorted(glob.glob(os.path.join(src, "scan_notes", "*.md")))
    if notes:
        # 挑块内有内容最多的一份，比首块信息量大
        best = max(notes, key=lambda p: os.path.getsize(p))
        shutil.copy2(best, os.path.join(out, "分块笔记_" + os.path.basename(best)))
        made.append("分块笔记_" + os.path.basename(best))

    if not made:
        os.rmdir(out)
    return made


def clean_owned(dst):
    """只删本脚本自己会写的东西。

    以前直接 rmtree(dst)，把人工写的 README.md、导出的 书评.docx 一起删了。示例目录
    是"交付 + 人工补充"混住的，只清自己产出的那几类，其它文件原样留着。
    """
    removed = []
    for pat in ("*_书评.md", "*_人物卡.md", "*_人物数据.json", "_封面.json", "封面.*"):
        for p in glob.glob(os.path.join(dst, pat)):
            if os.path.isfile(p):
                os.remove(p)
                removed.append(os.path.basename(p))
    for sub in ("人物图", "中间产物样例"):
        d = os.path.join(dst, sub)
        if os.path.isdir(d):
            shutil.rmtree(d)
            removed.append(sub + "/")
    return removed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="某本书的输出目录")
    ap.add_argument("--dst", required=True, help="examples/<书名>")
    ap.add_argument("--max-width", type=int, default=560, help="人物图限宽（默认 560）")
    ap.add_argument("--quality", type=int, default=82, help="webp 质量（默认 82）")
    ap.add_argument("--no-intermediates", action="store_true", help="不抽中间产物样例")
    a = ap.parse_args()

    if not os.path.isdir(a.src):
        sys.exit(f"[example] 源目录不存在：{a.src}")
    if os.path.abspath(a.src) == os.path.abspath(a.dst):
        sys.exit("[example] 源和目标是同一个目录，拒绝执行")

    before = dir_size(a.src)
    os.makedirs(a.dst, exist_ok=True)
    kept = [f for f in sorted(os.listdir(a.dst))
            if os.path.isfile(os.path.join(a.dst, f)) and f not in ("_封面.json",)
            and not f.startswith(("封面.",)) and not f.endswith(("_书评.md", "_人物卡.md", "_人物数据.json"))]
    clean_owned(a.dst)
    made = copy_deliverables(a.src, a.dst, a.max_width, a.quality)
    if not a.no_intermediates:
        made += copy_intermediates(a.src, a.dst)
    after = dir_size(a.dst)

    print(f"[example] {a.dst}")
    for m in made:
        print(f"   + {m}")
    if kept:
        print(f"   = 原样保留 {len(kept)} 个非脚本产物：{', '.join(kept)}")
    print(f"[example] 体积 {human(before)} → {human(after)}（图片限宽 {a.max_width}px / q{a.quality}）")
    if after > 3 * 1024 * 1024:
        print("[example] [WARN] 超过 3MB，建议调小 --max-width 或 --quality")


if __name__ == "__main__":
    main()
