#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
novel-scan: pick_cover.py —— 从 latent.moe 公开图库里**挑**一张现成的 SFW 图当书评封面

注意：**这是挑图，不是生图**。走公开图库的 `resolve` 接口，取的是别人已发布的作品，
不调用 `generate`、不写 prompt、不花出图额度、无需 API key，秒级返回。

为什么单独一个脚本：
  - 书评（公众号体例）第一屏是「标题 + 封面」，封面不必与人物图同源，
    随手挑一张能立刻让整篇有成品感；人物图另走 gen_portraits.py（按 appearance_prompt
    生成、要 key、要排队）。
  - 「随机」必须落在 **SFW 子集** 里：resolve 默认就只返回公开 SFW 作品
    （越界会报 `no_match ... Pass nsfw=1 to include NSFW`），本脚本再对返回的
    `nsfw` 字段做一次硬校验，双保险。

用法：
  python pick_cover.py --out <输出目录>/封面.webp
  python pick_cover.py --out 封面.webp --tags 1girl solo city --shape portrait
  python pick_cover.py --out 封面.webp --json <人物数据.json>   # 用 book_meta.cover_tags
  python pick_cover.py --out 封面.webp --rank 233              # 指定排位（可复现）

产物：
  <out>                 封面图（扩展名按 Content-Type 自动校正）
  <out 同目录>/_封面.json  出处留痕（artwork id / 排位 / 标签 / 模型 / 尺寸 / 作品页 URL）
"""
import argparse
import json
import os
import random
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://latent.moe"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) novel-scan/cover"}
RANK_MAX = 1000  # 服务端限制：rank must be an integer from 1 to 1000
DEFAULT_TAGS = ["1girl", "solo", "portrait"]  # portrait 把池子从"随手涂"收窄到胸像/半身，当封面更像样


def api(tags, rank=None, fmt="json"):
    q = [("tag", t) for t in tags]
    if rank:
        q.append(("rank", str(rank)))
    if fmt:
        q.append(("format", fmt))
    url = f"{BASE}/api/v1/images/resolve?{urllib.parse.urlencode(q, doseq=True)}"
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r).get("data") or {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        try:
            err = json.loads(body)
        except Exception:
            err = {"error": body[:120]}
        return {"_error": e.code, "_msg": err.get("message") or err.get("error") or ""}


def count_of(tags):
    """二分出该标签组合下公开 SFW 作品数（服务端按 rank 截断，上限 1000）。"""
    lo, hi = 1, RANK_MAX + 1
    while lo < hi:
        mid = (lo + hi) // 2
        d = api(tags, mid)
        if "_error" in d and d["_error"] in (404, 400):
            hi = mid
        elif "_error" in d:
            raise RuntimeError(f"检索失败：{d['_error']} {d['_msg']}")
        else:
            lo = mid + 1
    return lo - 1


def resolve_tags(tags, shape, tries):
    """标签太苛刻时逐级放宽，最后兜底 1girl；返回 (实际用的 tags, (rank, data))。"""
    ladder = [list(tags)]
    for i in range(len(tags) - 1, 0, -1):   # 逐个丢掉末尾标签：a b c → a b → a
        ladder.append(list(tags[:i]))
    if ["1girl"] not in ladder:
        ladder.append(["1girl"])
    seen = set()
    for work in ladder:
        key = tuple(work)
        if not work or key in seen:
            continue
        seen.add(key)
        n = count_of(work)
        if n <= 0:
            print(f"[cover] 标签 {work} 无可用的公开 SFW 作品，放宽一档")
            continue
        for _ in range(tries):
            rank = random.randint(1, n)
            d = api(work, rank)
            if "_error" in d:
                continue
            if d.get("nsfw") is True:      # 硬校验：宁可不换图也不用 NSFW
                continue
            if shape == "portrait" and d.get("height", 0) <= d.get("width", 0):
                continue
            return work, (rank, d)
        print(f"[cover] {work} 抽到 {tries} 次都不合条件，放宽一档")
    raise SystemExit("[cover] 连 1girl 都抽不到图，检查网络或 latent 服务状态")


def download(art_id, out_path):
    url = f"{BASE}/api/media/{art_id}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        raw = r.read()
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip()
    ext = {"image/webp": ".webp", "image/png": ".png", "image/jpeg": ".jpg"}.get(ctype, ".webp")
    base, old = os.path.splitext(out_path)
    if old.lower() != ext:
        out_path = base + ext
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(raw)
    return out_path, len(raw), ctype


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="封面输出路径，如 <输出目录>/封面.webp")
    ap.add_argument("--tags", nargs="*", default=None, help=f"图库标签（默认 {' '.join(DEFAULT_TAGS)}）")
    ap.add_argument("--shape", choices=["any", "portrait"], default="portrait",
                    help="portrait = 只要竖图（封面默认，池子里 832x1216 占多数）")
    ap.add_argument("--rank", type=int, help="指定排位（可复现某张图），给了就不随机")
    ap.add_argument("--json", help="人物数据 JSON；从中取 book_meta.cover_tags 当标签")
    ap.add_argument("--tries", type=int, default=8, help="同一标签组合的最大重抽次数")
    ap.add_argument("--seed", type=int, help="随机种子（想复现「随机」结果时用）")
    a = ap.parse_args()

    tags = a.tags
    if not tags and a.json and os.path.exists(a.json):
        meta = (json.load(open(a.json, encoding="utf-8")).get("book_meta") or {})
        tags = meta.get("cover_tags") or None
    tags = [t for t in (tags or DEFAULT_TAGS) if t]

    if a.seed is not None:
        random.seed(a.seed)

    if a.rank:
        d = api(tags, a.rank)
        if "_error" in d:
            raise SystemExit(f"[cover] 排位 {a.rank} 取不到图：{d['_error']} {d['_msg']}")
        if d.get("nsfw") is True:
            raise SystemExit("[cover] 该排位是 NSFW，换一个排位")
        used, (rank, data) = tags, (a.rank, d)
    else:
        used, (rank, data) = resolve_tags(tags, a.shape, a.tries)

    path, size, ctype = download(data["id"], a.out)
    meta = {
        "file": os.path.basename(path),
        "source": "latent.moe 公开图库（resolve，仅 SFW）",
        "tags": used,
        "rank": rank,
        "nsfw": data.get("nsfw"),
        "width": data.get("width"),
        "height": data.get("height"),
        "model": data.get("model"),
        "artwork_id": data.get("id"),
        "artwork_url": data.get("artworkUrl"),
        "view_count": data.get("viewCount"),
        "content_type": ctype,
        "bytes": size,
    }
    with open(os.path.join(os.path.dirname(os.path.abspath(path)), "_封面.json"),
              "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"[OK] {path}  {data.get('width')}x{data.get('height')}  "
          f"tags={' '.join(used)}  rank={rank}  nsfw={data.get('nsfw')}  {size//1024}KB")
    print(f"     作品页 {data.get('artworkUrl')}")


if __name__ == "__main__":
    sys.exit(main())
