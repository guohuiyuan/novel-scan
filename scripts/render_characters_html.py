# -*- coding: utf-8 -*-
"""
novel-scan skill: render_characters_html.py
把人物数据 JSON 渲染成自包含可视化 HTML（浅色主题，无外部依赖）。

用法:
  python render_characters_html.py --json <书名>_人物数据.json --out <书名>_人物可视化.html
"""
import argparse
import html
import json
import os

BADGE = {"处": ("✅", "b-ok"), "非处": ("❌", "b-bad"), "初": ("✅", "b-ok"),
         "非初": ("❌", "b-bad"), "未知": ("❓", "b-unk")}

# purity 字段名 -> 显示名
PURITY_KEYS = [("chu", "处"), ("jingshen_chu", "精神初"), ("hunyin", "初婚"), ("chumo", "初摸")]

LEIDIAN_KEYS = {"绿帽", "死女", "送女", "背叛", "万人骑", "龟作"}


def badge(val):
    for k, (icon, cls) in BADGE.items():
        if val and val.startswith(k):
            return f'<span class="badge {cls}">{icon} {html.escape(val)}</span>'
    return f'<span class="badge b-unk">❓ {html.escape(str(val or "未知"))}</span>'


def card(c, idx):
    name = html.escape(c.get("name", "?"))
    rank = c.get("importance_rank")
    rel = html.escape(c.get("relationship_to_mc", ""))
    ident = html.escape(c.get("identity", ""))
    pers = html.escape(c.get("personality", ""))
    pur = c.get("purity", {})
    leidian = [x for x in c.get("leidian", [])]
    yumen = [x for x in c.get("yumen", [])]
    events = c.get("key_events", [])
    quotes = c.get("quotes", [])
    aliases = c.get("aliases_verified", [])
    rejected = c.get("aliases_rejected", [])

    h = [f'<div class="card" id="c{idx}">']
    h.append(f'<div class="card-head"><span class="rank">#{rank if rank else idx+1}</span>'
             f'<span class="cname">{name}</span>'
             f'{f"<span class=rel>{rel}</span>" if rel else ""}</div>')
    aliases = [a if isinstance(a, str) else str(a.get("alias", a)) for a in (aliases or [])]
    if aliases:
        h.append(f'<div class="aliases">别名：{html.escape("、".join(aliases))}</div>')
    rejected = [r if isinstance(r, dict) else {"alias": str(r), "reason": ""} for r in (rejected or [])]
    if rejected:
        rej = "；".join(f"{r.get('alias','')}（{r.get('reason','')}）" for r in rejected)
        h.append(f'<div class="aliases rej">剔除别名：{html.escape(rej)}</div>')
    if ident:
        h.append(f'<div class="sec"><b>身份</b> {ident}</div>')
    if pers:
        h.append(f'<div class="sec"><b>性格</b> {pers}</div>')
    # purity
    h.append('<div class="purity">')
    for k, label in PURITY_KEYS:
        h.append(badge(pur.get(k, "未知")).replace('badge ', f'badge" title="{label}" data-x="').replace('data-x="', '', 1) if False else badge(pur.get(k, "未知")))
    v = pur.get("verdict")
    if v:
        h.append(f'<span class="verdict">{html.escape(v)}</span>')
    h.append('</div>')
    pe = pur.get("evidence") or []
    if pe:
        h.append('<div class="ev">判定依据：' + "；".join(html.escape(x) for x in pe) + '</div>')
    # leidian / yumen
    for title, items, cls in (("雷点", leidian, "tag-red"), ("郁闷点", yumen, "tag-amber")):
        if items:
            h.append(f'<div class="sec"><span class="stitle {cls}">{title}</span></div><ul class="pts">')
            for it in items:
                cat = html.escape(it.get("category", "未归类"))
                ev = html.escape(it.get("evidence", ""))
                q = html.escape(it.get("quote", ""))
                qq = f' <span class="q">「{q}」</span>' if q else ""
                h.append(f'<li><span class="tag {cls}">{cat}</span>{ev}{qq}</li>')
            h.append('</ul>')
    if events:
        h.append('<div class="sec"><b>关键事件</b></div><ul class="pts">')
        for e in events:
            if isinstance(e, dict):
                e = e.get("event") or e.get("text") or json.dumps(e, ensure_ascii=False)
            h.append(f'<li>{html.escape(str(e))}</li>')
        h.append('</ul>')
    if quotes:
        qs = [q if isinstance(q, str) else json.dumps(q, ensure_ascii=False) for q in quotes]
        h.append('<div class="quotes">' + "".join(f'<div class="q">「{html.escape(q)}」</div>' for q in qs) + '</div>')
    conf = c.get("confidence")
    if conf:
        h.append(f'<div class="conf">置信度：{html.escape(conf)}</div>')
    h.append('</div>')
    return "\n".join(h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    data = json.load(open(args.json, encoding="utf-8"))
    chars = data.get("characters", [])
    male = data.get("male_protagonist", {})
    stats = data.get("book_leidian_summary", []), data.get("book_yumen_summary", [])

    body = []
    body.append('<header><h1>' + html.escape(data.get("book", "")) + ' · 人物可视化</h1>')
    body.append(f'<div class="meta">{html.escape(data.get("source",""))} ｜ 生成 {html.escape(data.get("generated_at",""))} ｜ '
                f'{len(chars)} 个角色 ｜ 雷点 {sum(len(c.get("leidian",[])) for c in chars)} 条 ｜ '
                f'郁闷点 {sum(len(c.get("yumen",[])) for c in chars)} 条</div>')
    if male:
        body.append(f'<div class="mc"><b>男主：{html.escape(male.get("name",""))}</b> — {html.escape(male.get("identity",""))}'
                    + (f'<br>{html.escape(male.get("arc",""))}' if male.get("arc") else "") + '</div>')
    body.append('</header>')

    # 全书级汇总
    for title, items, cls in (("全书雷点汇总", stats[0], "tag-red"), ("全书郁闷点汇总", stats[1], "tag-amber")):
        if items:
            body.append(f'<h2 class="{cls}">{title}</h2><ul class="pts">')
            for it in items:
                body.append(f'<li><span class="tag {cls}">{html.escape(it.get("category",""))}</span>'
                            f'{html.escape(it.get("evidence",""))}'
                            + (f' <span class="q">「{html.escape(it.get("quote",""))}」</span>' if it.get("quote") else "")
                            + '</li>')
            body.append('</ul>')

    body.append('<h2>角色卡片</h2><div class="grid">')
    for i, c in enumerate(chars):
        body.append(card(c, i))
    body.append('</div>')

    css = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1c1e21;--sub:#5f6368;--line:#e3e5e8;
--red:#c5221f;--redbg:#fce8e6;--amber:#a56300;--amberbg:#fef3e2;--ok:#137333;--okbg:#e6f4ea;--unk:#5f6368;--unkbg:#f1f3f4}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font-family:"Microsoft YaHei","PingFang SC",system-ui,sans-serif;line-height:1.65}
header{max-width:1080px;margin:0 auto;padding:28px 20px 8px}
h1{font-size:24px;margin:0 0 8px}.meta{color:var(--sub);font-size:13px}
.mc{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-top:14px;font-size:14px}
h2{max-width:1080px;margin:26px auto 10px;padding:0 20px;font-size:18px}
h2.tag-red{color:var(--red)}h2.tag-amber{color:var(--amber)}
.grid{max-width:1080px;margin:0 auto 40px;padding:0 20px;display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;font-size:13.5px}
.card-head{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.rank{background:var(--unkbg);border-radius:8px;padding:1px 8px;font-weight:700;color:var(--sub);font-size:12px}
.cname{font-size:17px;font-weight:700}
.rel{margin-left:auto;color:var(--sub);font-size:12px;border:1px solid var(--line);border-radius:99px;padding:2px 10px}
.aliases{color:var(--sub);font-size:12px;margin-bottom:6px}.aliases.rej{color:#a50e0e}
.sec{margin-top:8px}.stitle{font-weight:700;border-radius:6px;padding:1px 8px;font-size:12px}
.tag{display:inline-block;border-radius:6px;padding:1px 8px;font-size:12px;font-weight:600;margin-right:6px}
.tag-red{color:var(--red);background:var(--redbg)}.tag-amber{color:var(--amber);background:var(--amberbg)}
.pts{margin:6px 0 0;padding-left:18px}.pts li{margin:4px 0}
.q{color:var(--sub);font-style:normal}
.purity{margin-top:10px;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.badge{border-radius:99px;padding:2px 10px;font-size:12px;font-weight:600}
.b-ok{color:var(--ok);background:var(--okbg)}.b-bad{color:var(--red);background:var(--redbg)}.b-unk{color:var(--unk);background:var(--unkbg)}
.verdict{margin-left:auto;font-weight:700;color:var(--ink)}
.ev{color:var(--sub);font-size:12px;margin-top:6px}
.quotes{margin-top:10px;border-top:1px dashed var(--line);padding-top:8px}
.quotes .q{color:var(--sub);font-size:12.5px;margin:2px 0}
.conf{margin-top:8px;color:var(--sub);font-size:12px}
ul.pts{list-style:disc}
"""
    doc = ("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
           "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
           "<title>" + html.escape(data.get("book", "")) + " · 人物可视化</title>"
           "<style>" + css + "</style></head><body>" + "\n".join(body) + "</body></html>")
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"[OK] {args.out} ({len(chars)} cards, {len(doc)} chars)")


if __name__ == "__main__":
    main()
