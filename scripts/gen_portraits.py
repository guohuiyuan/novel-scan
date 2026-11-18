#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
novel-scan: gen_portraits.py —— 按人物 JSON 里的 appearance_prompt 出女主图

它自己不出图：把提示词拼好，交给 latent-media skill 的 scripts/latent.py 调
https://latent.moe 文生图，落地到 <输出目录>/人物图/<角色名>.webp，并写一份索引。

用法：
  python gen_portraits.py --json <书名>_人物数据.json --out <输出目录> \
      [--only 曾柔,于紫彤] [--top 12] [--style anime|watercolor|realistic] \
      [--resolution portrait] [--seed 1234] [--dry-run] \
      [--latent <latent.py 路径>] [--key lat_sk_xxx]

前提：
  - latent-media skill 已装好并且 keys.env 里有图像 key（lat_sk_ 开头）；
    或设环境变量 LATENT_IMAGE_KEY，或用 --key 临时给。
  - 图像接口同一时刻只允许 1 个任务，所以本脚本串行跑，别并发。

提示词约定（写进人物 JSON 的 appearance_prompt）：
  - 英文 Danbooru 风格 tag，逗号分隔，只写原文核验过的外形事实；
  - 不写剧情、不写心理、不写"气质高贵"这类无法画出来的词；
  - 本脚本会自动补：人数/构图/画风/画质 tag 与负向词。
"""
import argparse
import json
import os
import re
import subprocess
import sys

STYLE = {
    # 实测（2026-11-18，曾柔三版对比）：这套 tag 出图最稳——正面、无手部畸形、无水印、
    # 背景干净（方便给扫书视频叠字幕）。扁平上色/全身/伸向镜头是三个最常见的翻车。
    "anime": (
        ["portrait", "simple background", "gradient background", "anime screencap",
         "official art", "masterpiece", "best quality", "highly detailed", "soft lighting"],
        ["photorealistic", "3d", "realistic", "flat color", "sketch", "monochrome"],
    ),
    "watercolor": (
        ["watercolor (medium)", "soft light", "muted palette", "paper texture",
         "simple background", "delicate", "masterpiece", "best quality"],
        ["photorealistic", "3d", "heavy contrast", "oversaturated", "flat color"],
    ),
    "realistic": (
        ["photorealistic", "cinematic lighting", "85mm portrait", "shallow depth of field",
         "film grain", "simple background", "masterpiece", "best quality"],
        ["anime", "cartoon", "illustration", "3d render", "cgi"],
    ),
}

BASE_POS = ["1girl", "solo", "upper body", "looking at viewer", "arms at sides",
            "standing", "detailed face", "beautiful detailed eyes"]

# 男主用这套（1girl 换 1boy，眼睛 tag 换成男性向的写法）
BASE_POS_MALE = ["1boy", "solo", "upper body", "looking at viewer", "arms at sides",
                 "standing", "detailed face", "handsome"]

# 年龄/体型 tag 互斥：角色自己带了更具体的，就把基线里的去掉
AGE_TAGS = {"young woman": ["mature female", "high school student", "loli", "child"],
            "mature female": ["young woman"], }

BASE_NEG = (
    "lowres, worst quality, bad anatomy, bad hands, extra fingers, missing fingers, "
    "text, watermark, signature, username, logo, artist name, copyright name, "
    "chinese text, english text, text block, corner label, magazine cover, barcode, stamp, "
    "jpeg artifacts, blurry, cropped, deformed, extra limbs, mutation, nsfw, nude, "
    "full body, feet, leaning forward, from below, from above, "
    "outstretched arm, reaching towards viewer, pov, hand in foreground, "
    "blurry foreground, messy background, multiple girls, "
    "streaked hair, green hair, colored hair tips, two-tone hair"
)

DEFAULT_LATENT = os.path.expanduser("~/.workbuddy/skills/latent-media/scripts/latent.py")


def dedupe(tags):
    seen, out = set(), []
    for t in tags:
        t = t.strip().strip(",").strip()
        k = t.lower()
        if not t or k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out


def build_prompt(ch, style, male=False):
    own = [t.strip() for t in re.split(r"[,，]", (ch.get("appearance_prompt") or "")) if t.strip()]
    style_pos, style_neg = STYLE[style]
    base = list(BASE_POS_MALE if male else BASE_POS)
    low = " ".join(own).lower()
    for k, rivals in AGE_TAGS.items():
        if k in base and any(r in low for r in rivals):
            base.remove(k)
    tags = dedupe(base + own + style_pos)
    neg = list(dedupe([BASE_NEG] + style_neg))
    if male:
        neg = [t for t in neg if t not in ("multiple girls",)] + ["multiple girls", "female focus"]
    return ", ".join(tags), ", ".join(dedupe(neg))


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", s).strip("_") or "char"


def call_latent(latent, key, prompt, negative, out_path, resolution, seed, steps):
    cmd = [sys.executable, latent, "image",
           "--prompt", prompt, "--negative", negative,
           "--resolution", resolution, "--steps", str(steps),
           "-o", out_path, "--json"]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    if key:
        cmd += ["--key", key]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "").strip()[-500:])
    txt = (p.stdout or "").strip()
    m = re.search(r"\{.*\}", txt, flags=re.S)
    return json.loads(m.group(0)) if m else {"raw": txt}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True, help="人物数据 JSON")
    ap.add_argument("--out", required=True, help="输出目录（图放 <out>/人物图/）")
    ap.add_argument("--only", help="只出这些人（逗号分隔）")
    ap.add_argument("--top", type=int, default=0, help="只出 importance_rank <= N 的角色")
    ap.add_argument("--with-male", dest="with_male", action="store_true", default=True,
                    help="男主也出图（排 00，默认开）")
    ap.add_argument("--no-male", dest="with_male", action="store_false",
                    help="不画男主")
    ap.add_argument("--style", default="anime", choices=sorted(STYLE))
    ap.add_argument("--resolution", default="portrait",
                    choices=["square", "portrait", "landscape"])
    ap.add_argument("--seed", type=int, help="固定种子（所有角色同一 seed 会让构图趋同，慎用）")
    ap.add_argument("--steps", type=int, default=12)
    ap.add_argument("--dry-run", action="store_true", help="只打印提示词，不调接口")
    ap.add_argument("--reindex", action="store_true",
                    help="不调接口，只按现有图片重建 _图片索引.json（断点续跑后修索引）")
    ap.add_argument("--latent", default=DEFAULT_LATENT, help="latent.py 路径")
    ap.add_argument("--key", help="临时图像 key（默认读 latent-media 的 keys.env / 环境变量）")
    a = ap.parse_args()

    data = json.load(open(a.json, encoding="utf-8"))
    chars = data.get("characters", [])
    male = data.get("male_protagonist") or {}
    if a.with_male and male.get("name"):
        chars = [dict(male, importance_rank=0)] + chars
    if a.only:
        want = {x.strip() for x in a.only.split(",") if x.strip()}
        chars = [c for c in chars if c.get("name") in want]
    if a.top:
        chars = [c for c in chars if (c.get("importance_rank") or 999) <= a.top]
    if not chars:
        print("[ERROR] 没有匹配到角色（检查 --only / --top）")
        return 1
    male_name = male.get("name")

    img_dir = os.path.join(a.out, "人物图")
    os.makedirs(img_dir, exist_ok=True)
    index = []
    fail = 0

    if a.reindex:
        for ch in chars:
            name = ch.get("name") or "未命名"
            hit = [f for f in os.listdir(img_dir)
                   if f.endswith(".webp") and safe_name(name) in f]
            if not hit:
                continue
            prompt, _ = build_prompt(ch, a.style, male=(name == male_name))
            index.append({"name": name, "file": sorted(hit)[0], "seed": None,
                          "artwork_id": None, "prompt": prompt})
        idx_path = os.path.join(img_dir, "_图片索引.json")
        with open(idx_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"book": data.get("book"), "style": a.style,
                       "resolution": a.resolution,
                       "items": sorted(index, key=lambda x: x["file"])},
                      f, ensure_ascii=False, indent=1)
        print("[OK] 重建索引 %d 条：%s" % (len(index), idx_path))
        return 0

    for i, ch in enumerate(chars, 1):
        name = ch.get("name") or "未命名"
        if not (ch.get("appearance_prompt") or "").strip():
            print("[SKIP] %s：没有 appearance_prompt（先让子代理按模板三写）" % name)
            continue
        prompt, negative = build_prompt(ch, a.style, male=(name == male_name))
        print("\n[%d/%d] %s" % (i, len(chars), name))
        print("  prompt: %s" % prompt)
        if a.dry_run:
            continue
        seed = a.seed
        rank = ch.get("importance_rank")
        rank = i if rank is None else rank
        out_path = os.path.join(img_dir, "%02d_%s.webp" % (rank, safe_name(name)))
        try:
            r = call_latent(a.latent, a.key, prompt, negative, out_path,
                            a.resolution, seed, a.steps)
        except Exception as e:
            fail += 1
            print("  [FAIL] %s" % e)
            continue
        got = r.get("file") or out_path
        size = os.path.getsize(got) if os.path.exists(got) else 0
        print("  ok  seed=%s  %.0f KB  %s" % (r.get("seed"), size / 1024, got))
        index.append({"name": name, "file": os.path.basename(got), "seed": r.get("seed"),
                      "artwork_id": r.get("artwork_id"), "prompt": prompt,
                      "signature_line": (ch.get("signature_line") or {}).get("quote")
                      if isinstance(ch.get("signature_line"), dict)
                      else ch.get("signature_line")})

    if a.dry_run:
        print("\n[DRY-RUN] 未调用接口。")
        return 0

    idx_path = os.path.join(img_dir, "_图片索引.json")
    old = []
    if os.path.exists(idx_path):
        try:
            old = json.load(open(idx_path, encoding="utf-8")).get("items", [])
        except Exception:
            old = []
    by_name = {it.get("name"): it for it in old}
    for it in index:
        by_name[it["name"]] = it
    items = sorted(by_name.values(), key=lambda x: str(x.get("file", "")))
    with open(idx_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"book": data.get("book"), "style": a.style,
                   "resolution": a.resolution, "items": items},
                  f, ensure_ascii=False, indent=1)
    print("\n[OK] 本次 %d 张，索引共 %d 条：%s" % (len(index), len(items), idx_path))
    if fail:
        print("[WARN] %d 张失败，可能撞上 409 too_many_active 或额度用尽" % fail)
    return 0 if index else 2


if __name__ == "__main__":
    sys.exit(main())
