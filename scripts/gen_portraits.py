#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
novel-scan: gen_portraits.py —— 按人物 JSON 里的 appearance_prompt 出女主图

它自己不出图：把提示词拼好，交给 latent-media skill 的 scripts/latent.py 调
https://latent.moe 文生图，落地到 <输出目录>/人物图/<角色名>.webp，并写一份索引。

用法：
  # 常规：assemble_json 之后整本出
  python gen_portraits.py --json <书名>_人物数据.json --out <输出目录> \
      [--only 曾柔,于紫彤] [--top 12] [--style anime|watercolor|realistic] \
      [--resolution portrait] [--seed-mode name|random|fixed] [--seed-salt 0] \
      [--seed 1234] [--dry-run] [--force] \
      [--latent <latent.py 路径>] [--key lat_sk_xxx]

  # 边整理边出图：C 阶段每写完几个角色就能出，不用等 assemble
  python gen_portraits.py --chars-dir <输出目录>/json --male 成默 --out <输出目录>
      # 已存在的图自动跳过（断点续跑不重复花额度），要重出加 --force
      # 男主的 appearance_prompt 在 book_info.json 的 male_protagonist 里，脚本会自动取

seed 策略（画风一致性的关键）：
  同一角色、同一 prompt 只换 seed，就可能一张出九〇年代复古赛璐璐、一张出当代 anime。
  - name  （默认）：按角色名派生固定 seed（sha256 前 13 位）。同一本书重跑出同一批图，
          各角色构图又互不相同。整本想换一批就 --seed-salt N，仍可复现。
  - random：每张随机（旧行为，适合探索）。
  - fixed ：所有角色同一个 seed（旧 --seed 行为），构图会趋同，慎用。

前提：
  - latent-media skill 已装好并且 keys.env 里有图像 key（lat_sk_ 开头）；
    或设环境变量 LATENT_IMAGE_KEY，或用 --key 临时给。
  - 图像接口同一时刻只允许 1 个任务，所以本脚本串行跑，别并发。

提示词约定（写进人物 JSON 的 appearance_prompt）：
  - 英文 Danbooru 风格 tag，逗号分隔，只写原文核验过的外形事实；
  - 不写剧情、不写心理、不写"气质高贵"这类无法画出来的词；
  - 不要写 `realistic` / `photorealistic`（本画风的负向词里有），脚本会剔除并告警；
  - 本脚本会自动补：人数/构图/画风/画质 tag 与负向词。
"""
import argparse
import hashlib
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

# 画师 tag：放在角色 tag 之前，权重足。morikura_en = 森仓円，干净通透的萌系少女上色，
# 负向词里必须去掉「artist name」（否则和这里的画师 tag 打架）。
DEFAULT_ARTIST = "morikura_en"

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


def neg_set(style):
    """负向词集合（拆成一个个 tag），用来查正向里有没有自相矛盾的词。"""
    _, style_neg = STYLE[style]
    raw = ",".join([BASE_NEG] + style_neg)
    return {t.strip().lower() for t in raw.split(",") if t.strip()}


def build_prompt(ch, style, male=False, artist=DEFAULT_ARTIST):
    """返回 (正向, 负向, 被丢掉的自相矛盾 tag)。

    第三项是画风漂移的头号原因：角色自己的 appearance_prompt 里写了
    `realistic` / `photorealistic`，而这些词正好在本画风的负向列表里——
    同一 tag 既正向又负向，模型只能掷硬币，出图就会一半赛璐璐一半写实。
    """
    own = [t.strip() for t in re.split(r"[,，]", (ch.get("appearance_prompt") or "")) if t.strip()]
    style_pos, style_neg = STYLE[style]
    base = list(BASE_POS_MALE if male else BASE_POS)
    low = " ".join(own).lower()
    for k, rivals in AGE_TAGS.items():
        if k in base and any(r in low for r in rivals):
            base.remove(k)
    nset = neg_set(style)
    kept, dropped = [], []
    for t in own:
        # 整词比对，避免 `realistic` 把 `realistic eyes` 这类子串误伤
        if t.strip().lower() in nset:
            dropped.append(t)
        else:
            kept.append(t)
    art = [artist] if artist and artist.lower() not in ("none", "no") else []
    tags = dedupe(art + base + kept + style_pos)
    neg = list(dedupe([BASE_NEG] + style_neg))
    if art:
        # 「artist name」是防签名的负向词，但指定画师时会把画风一起压掉
        neg = [t for t in neg if t not in ("artist name", "copyright name")]
    if male:
        neg = [t for t in neg if t not in ("multiple girls",)] + ["multiple girls", "female focus"]
    return ", ".join(tags), ", ".join(dedupe(neg)), dropped


def name_seed(name, salt=0):
    """由角色名派生固定种子：同一本书重跑出同一批图，不同角色构图互不相同。

    取 sha256 前 13 位十六进制（≤4.5e15），落在 latent 已验证可用的整数范围内。
    """
    h = hashlib.sha256(("%s|%s" % (salt, name)).encode("utf-8")).hexdigest()
    return int(h[:13], 16)


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
    ap.add_argument("--json", help="人物数据 JSON（与 --chars-dir 二选一，assemble 之后用）")
    ap.add_argument("--chars-dir",
                    help="C 阶段的单角色 JSON 目录：边写边出图，不必等 assemble（见 --male）")
    ap.add_argument("--male", help="配 --chars-dir：哪个名字是男主（他那张排 00）")
    ap.add_argument("--book", help="配 --chars-dir：书名，只写进索引，可省")
    ap.add_argument("--force", action="store_true",
                    help="已有同名图也重出（默认跳过，方便断点续跑）")
    ap.add_argument("--out", required=True, help="输出目录（图放 <out>/人物图/）")
    ap.add_argument("--only", help="只出这些人（逗号分隔）")
    ap.add_argument("--top", type=int, default=0, help="只出 importance_rank <= N 的角色")
    ap.add_argument("--with-male", dest="with_male", action="store_true", default=True,
                    help="男主也出图（排 00，默认开）")
    ap.add_argument("--no-male", dest="with_male", action="store_false",
                    help="不画男主")
    ap.add_argument("--style", default="anime", choices=sorted(STYLE))
    ap.add_argument("--artist", default=DEFAULT_ARTIST,
                    help="画师 tag（默认 morikura_en；传 none 关掉）")
    ap.add_argument("--resolution", default="portrait",
                    choices=["square", "portrait", "landscape"])
    ap.add_argument("--seed", type=int, help="固定种子（配 --seed-mode fixed；所有角色同一 seed 会让构图趋同，慎用）")
    ap.add_argument("--seed-mode", default="name", choices=["name", "random", "fixed"],
                    help="name=按角色名派生（默认，重跑可复现且各角色构图不同）；"
                         "random=每张随机；fixed=用 --seed 一刀切")
    ap.add_argument("--seed-salt", type=int, default=0,
                    help="配 --seed-mode name：换个 salt 等于整本重摇一次，仍可复现")
    ap.add_argument("--steps", type=int, default=12)
    ap.add_argument("--dry-run", action="store_true", help="只打印提示词，不调接口")
    ap.add_argument("--reindex", action="store_true",
                    help="不调接口，只按现有图片重建 _图片索引.json（断点续跑后修索引）")
    ap.add_argument("--latent", default=DEFAULT_LATENT, help="latent.py 路径")
    ap.add_argument("--key", help="临时图像 key（默认读 latent-media 的 keys.env / 环境变量）")
    a = ap.parse_args()

    if not (a.json or a.chars_dir):
        ap.error("--json 与 --chars-dir 至少给一个")

    if a.chars_dir:
        # C 阶段边整理边出图：目录里每落一个单角色 JSON 就能出这一张。
        # 不走 assemble 后的合并 JSON，是因为 assemble 会把 rank 压平成 1..N——
        # 只拿一批子集去 assemble，第二批就会被重编号，图名和最终书评里的序号对不上。
        data = {"book": a.book or os.path.basename(os.path.abspath(a.out))}
        chars, bad = [], []
        for fn in sorted(os.listdir(a.chars_dir)):
            if not fn.endswith(".json") or fn.startswith(("_", ".")):
                continue
            try:
                ch = json.load(open(os.path.join(a.chars_dir, fn), encoding="utf-8"))
            except Exception as e:
                bad.append("%s（%s）" % (fn, e))
                continue
            if not isinstance(ch, dict) or "characters" in ch or "male_protagonist" in ch:
                continue          # book_info.json 之类，不是角色卡
            if ch.get("name"):
                chars.append(ch)
        if bad:
            print("[warn] 跳过解析失败的文件：%s" % "、".join(bad))
        male_name = a.male or ""
        hit_male = False
        for c in chars:
            if male_name and c.get("name") == male_name:
                c["importance_rank"] = 0
                hit_male = True
        if male_name and not hit_male:
            # 男主一般写在 book_info.json 的 male_protagonist 里，不在 characters 目录。
            # C2 写完它落在输出目录根，所以两个位置都找一遍。
            for bi in (os.path.join(a.chars_dir, "book_info.json"),
                       os.path.join(a.out, "book_info.json")):
                if not os.path.exists(bi):
                    continue
                try:
                    m = json.load(open(bi, encoding="utf-8")).get("male_protagonist") or {}
                except Exception:
                    m = {}
                if m.get("name") == male_name:
                    chars.append(dict(m, importance_rank=0))
                    break
        chars.sort(key=lambda c: (c.get("importance_rank")
                                  if isinstance(c.get("importance_rank"), int) else 999,
                                  c.get("name") or ""))
        if male_name and not a.with_male:
            chars = [c for c in chars if c.get("name") != male_name]
        male = {"name": male_name} if male_name else {}
    else:
        data = json.load(open(a.json, encoding="utf-8"))
        chars = data.get("characters", [])
        male = data.get("male_protagonist") or {}
        if a.with_male and male.get("name"):
            chars = [dict(male, importance_rank=0)] + chars
        male_name = male.get("name")

    if a.only:
        want = {x.strip() for x in a.only.split(",") if x.strip()}
        chars = [c for c in chars if c.get("name") in want]
    if a.top:
        chars = [c for c in chars if (c.get("importance_rank") or 999) <= a.top]
    if not chars:
        print("[ERROR] 没有匹配到角色（检查 --chars-dir / --only / --top）")
        return 1

    img_dir = os.path.join(a.out, "人物图")
    os.makedirs(img_dir, exist_ok=True)
    index = []
    fail = 0

    # 旧索引先读进来：边写边出图时每跑一次都会重写索引，跳过的那几张必须原样保留
    # 之前的 seed / artwork_id，否则每跑一遍就把已有记录擦成 None。
    idx_path = os.path.join(img_dir, "_图片索引.json")
    old = []
    if os.path.exists(idx_path):
        try:
            old = json.load(open(idx_path, encoding="utf-8")).get("items", [])
        except Exception:
            old = []
    old_by_name = {it.get("name"): it for it in old}

    if a.reindex:
        for ch in chars:
            name = ch.get("name") or "未命名"
            hit = [f for f in os.listdir(img_dir)
                   if f.endswith(".webp") and safe_name(name) in f]
            if not hit:
                continue
            prompt, _, dropped = build_prompt(ch, a.style, male=(name == male_name), artist=a.artist)
            if dropped:
                print("  [warn] %s 的 appearance_prompt 含与画风负向词冲突的 tag：%s" % (name, dropped))
            index.append({"name": name, "file": sorted(hit)[0], "seed": None,
                          "artwork_id": None, "prompt": prompt})
        idx_path = os.path.join(img_dir, "_图片索引.json")
        with open(idx_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"book": data.get("book"), "style": a.style, "artist": a.artist,
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
        prompt, negative, dropped = build_prompt(ch, a.style, male=(name == male_name),
                                                artist=a.artist)
        print("\n[%d/%d] %s" % (i, len(chars), name))
        if dropped:
            print("  [warn] 丢掉与画风负向词冲突的 tag：%s（改 appearance_prompt 时换个说法）"
                  % ", ".join(dropped))
        print("  prompt: %s" % prompt)
        if a.dry_run:
            continue
        if a.seed_mode == "fixed":
            seed = a.seed if a.seed is not None else name_seed(name, a.seed_salt)
        elif a.seed_mode == "name":
            seed = name_seed(name, a.seed_salt)
        else:
            seed = None
        rank = ch.get("importance_rank")
        rank = i if rank is None else rank
        out_path = os.path.join(img_dir, "%02d_%s.webp" % (rank, safe_name(name)))
        if os.path.exists(out_path) and not a.force:
            # 边写边出图的前提：重复跑不重复花额度。换 seed-salt / 改 prompt 后要重出就加 --force。
            print("  skip 已存在（要重出加 --force）：%s" % os.path.basename(out_path))
            prev = old_by_name.get(name) or {}
            index.append({"name": name, "file": os.path.basename(out_path),
                          "seed": prev.get("seed", seed),
                          "artwork_id": prev.get("artwork_id"), "prompt": prompt,
                          "signature_line": prev.get("signature_line")
                          if prev.get("signature_line")
                          else (ch.get("signature_line") or {}).get("quote")
                          if isinstance(ch.get("signature_line"), dict)
                          else ch.get("signature_line")})
            continue
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
    by_name = {it.get("name"): it for it in old}
    for it in index:
        by_name[it["name"]] = it
    items = sorted(by_name.values(), key=lambda x: str(x.get("file", "")))
    with open(idx_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"book": data.get("book"), "style": a.style, "artist": a.artist,
                   "resolution": a.resolution, "items": items},
                  f, ensure_ascii=False, indent=1)
    print("\n[OK] 本次 %d 张，索引共 %d 条：%s" % (len(index), len(items), idx_path))
    if fail:
        print("[WARN] %d 张失败，可能撞上 409 too_many_active 或额度用尽" % fail)
    return 0 if index else 2


if __name__ == "__main__":
    sys.exit(main())
