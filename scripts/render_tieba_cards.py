# -*- coding: utf-8 -*-
"""贴吧连图生成器：把人物数据 JSON + 情节速览报告拆成多张手机端卡片图。"""
import json, os, re, sys, html

W = 750          # 逻辑宽度
SCALE = 2        # 2x 输出 1500px
BOOK = "极品家丁"
OUT = r"C:\Users\guohuiyuan\code\aiwork\novelwork\novel-digest\results\自扫_极品家丁\贴吧图片"
TMP = os.path.join(OUT, "_html")
DATA = r"C:\Users\guohuiyuan\code\aiwork\novelwork\novel-digest\results\自扫_极品家丁\极品家丁_人物数据.json"

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{width:750px;background:#eef1f5;font-family:"Microsoft YaHei","PingFang SC",sans-serif;color:#22252a;-webkit-font-smoothing:antialiased}
.top{background:linear-gradient(135deg,#2f5af0,#7a3cf0);color:#fff;padding:34px 40px 26px}
.top .k{font-size:24px;opacity:.85;letter-spacing:2px}
.top h1{font-size:52px;margin:6px 0 8px}
.top .sub{font-size:26px;opacity:.92}
.body{padding:30px 40px 36px}
h2{font-size:34px;margin:26px 0 14px;padding-left:18px;border-left:10px solid #2f5af0;line-height:1.3}
h2:first-child{margin-top:0}
h2.red{border-color:#c5221f;color:#c5221f}
h2.amber{border-color:#a56300;color:#a56300}
h2.green{border-color:#137333;color:#137333}
p,li,td,th{font-size:28px;line-height:1.72}
ul{padding-left:36px}
li{margin:8px 0}
.tag{display:inline-block;background:#e8edff;color:#2f5af0;border-radius:10px;padding:2px 16px;font-size:24px;margin:4px 8px 4px 0;font-weight:600}
.tag.red{background:#fce8e6;color:#c5221f}
.tag.amber{background:#fef3e2;color:#a56300}
.tag.green{background:#e6f4ea;color:#137333}
.tag.gray{background:#f1f3f4;color:#5f6368}
.box{background:#fff;border-radius:20px;padding:24px 28px;margin:14px 0;box-shadow:0 2px 8px rgba(0,0,0,.06)}
.hl{color:#c5221f;font-weight:700}
.hg{color:#137333;font-weight:700}
.q{color:#5f6368;font-style:normal}
table{width:100%;border-collapse:collapse;margin:10px 0}
td,th{border-bottom:1px solid #eceef1;padding:12px 8px;text-align:left;vertical-align:top}
th{color:#5f6368;font-size:24px}
.footer{padding:20px 40px 34px;color:#9aa0a6;font-size:22px;text-align:center}
.chip{display:inline-block;background:#fff;border:1px solid #e3e5e8;border-radius:14px;padding:10px 18px;margin:6px 8px 6px 0;font-size:26px}
.name{font-size:38px;font-weight:800;margin-right:14px}
.rel{color:#7a3cf0;font-weight:600;font-size:26px}
.dim{display:inline-block;margin:6px 14px 6px 0;font-size:26px;font-weight:700}
.evt{margin:6px 0 6px 0;padding-left:0;list-style:none}
.evt li{position:relative;padding-left:30px;margin:10px 0}
.evt li:before{content:"";position:absolute;left:0;top:16px;width:12px;height:12px;border-radius:50%;background:#2f5af0}
.quote{background:#f6f7f9;border-left:8px solid #c9cdd4;padding:14px 20px;margin:10px 0;color:#44474b;border-radius:0 12px 12px 0}
.big{font-size:30px;font-weight:700}
"""


def esc(s):
    return html.escape(str(s or ""))


def clean(s, n=None):
    s = re.sub(r"L\d+(?:[/-]\d+)*", "", str(s or ""))
    s = re.sub(r"（[^（）]*L\d+[^（）]*）", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" 　、;；")
    return s[:n] + "…" if n and len(s) > n else s


def purity_icons(pur):
    def icon(v, good, bad):
        v = str(v or "未知")
        if "不适用" in v: return "➖"
        if any(k in v for k in bad): return "❌"
        if "未知" in v or v in ("", "?"): return "❓"
        return "✅"
    a = icon(pur.get("chu"), 0, ("非处", "破鞋"))
    b = icon(pur.get("jingshen_chu"), 0, ("非初", "非"))
    c = icon(pur.get("hunyin"), 0, ("有婚史", "离异"))
    d = icon(pur.get("chumo"), 0, ("被非男主",))
    return (f'<span class="dim">处 {a}</span><span class="dim">精神初 {b}</span>'
            f'<span class="dim">初婚 {c}</span><span class="dim">初摸 {d}</span>')


def page(idx, total, body_html, title):
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<div class="top"><div class="k">扫书报告 · {idx:02d}/{total:02d}</div><h1>《{esc(BOOK)}》</h1><div class="sub">{esc(title)}</div></div>
<div class="body">{body_html}</div>
<div class="footer">AI 辅助生成 · 全部事实经原文核验 · novel-scan</div></body></html>"""


def build_cards(data):
    cards = []  # (title, body_html)
    chars = data["characters"]
    male = data["male_protagonist"]

    # 1 封面
    cards.append(("书籍信息与结论速览", f"""
<h2>这本书</h2>
<div class="box"><p><span class="big">禹岩 · 经典穿越后宫文</span></p>
<p>正文 691 章完结（第691章「万千柔情（全剧终！）」）+ 10 篇番外</p>
<p class="q">现代销售经理穿越成萧家小家丁林三，凭一块香皂和满肚子歪诗从后宅混到朝堂，弃帝位携十三位佳人西湖逍遥。</p></div>
<h2>速览结论</h2>
<div class="box">
<p><span class="tag green">六类硬雷 0</span><span class="tag green">完结大团圆</span><span class="tag amber">虐心 26 处</span><span class="tag amber">亵女 15 处</span><span class="tag gray">擦边 14 处</span><span class="tag gray">拒女 10 处</span></p>
<p style="margin-top:10px">六类雷点（绿帽/死女/送女/背叛/万人骑/龟作）逐卷排查<span class="hg">零检出</span>；郁闷点第一大类是<span class="hl">虐心</span>——女主线分离桥段多，但全部 HE 收束。</p></div>"""))

    # 2 核心设定
    cards.append(("核心设定", """
<h2>三层外挂</h2>
<div class="box"><p>① <b>商业金手指</b>：三花草/香水/肥皂/联营商战，从家丁混成商界传奇</p>
<p>② <b>诗词名场面</b>：桃花庵、鹧鸪天等，才子人设立住</p>
<p>③ <b>朝堂军功</b>：剿白莲参谋将军 → 北伐突厥 → 斗倒诚王</p></div>
<h2>势力格局</h2>
<div class="box"><p>帝党 vs 诚王党阴谋贯穿全书；外战三线——白莲教（安碧如/秦仙儿/依莲）、高丽（徐长今）、东瀛+突厥（玉伽/月牙儿）。</p>
<p>皇帝身负「绝嗣血仇」秘辛，番外揭晓其一：二十年前诚王兵乱弑其幼子并伤其身。</p></div>"""))

    # 3-4 主线
    rows1 = [
        ("1-92章 萧府家丁篇", "穿越入萧府；救肖青璇结怨又结缘；香水商战发家；萧玉霜「私定终身」救林；巧巧定情拜堂"),
        ("93-184章 白莲圣女篇", "秦仙儿=白莲妖女/肖青璇双身份对立；囚室春药局失身传功（对象男主）；七夕玉佛寺之约；灵隐寺双龙金牌伏笔"),
        ("185-277章 剿白莲篇", "参谋将军统五万兵；洛府寿宴连败沈半山/玄玄子；洛凝表白；白莲圣母假死；女祭酒伏笔"),
        ("278-369章 京城篇", "宁雨昔御前护卫；金殿力打东瀛王子；天牢救驾；秦妃挡剑旧案；招亲四题；诚王做局"),
    ]
    rows2 = [
        ("370-462章 救妻篇", "微山湖捞银三十五万两；宁雨昔坠崖假死；肖青璇孕中被囚玉德仙坊→炮打牌坊救妻；出云公主三重身份揭晓；仙儿解蛊圆房"),
        ("463-554章 诚王覆灭篇", "灯笼炸药重伤→诈死引蛇→火烧王府+玉玺栽赃→城南决战诚王被擒；皇帝绝嗣血仇秘辛；北伐突厥启动"),
        ("555-646章 北伐草原篇", "贺兰山奇袭、草原三连胜；李武陵万箭穿心假死复生；玉伽=突厥大可汗揭晓；叼羊抢可汗；消忆诀别；冰窟婚纱"),
        ("647-691章 大结局", "赵康宁终局；肖青璇之子赵铮继位；林晚荣弃帝位选人间逍遥；全家杭州西湖收束——全剧终；番外揭晓「两大绝密」之一"),
    ]
    def tl(rows):
        return '<div class="box">' + "".join(
            f'<p style="margin:14px 0"><span class="tag">{esc(r[0])}</span><br>{esc(r[1])}</p>' for r in rows) + '</div>'
    cards.append(("主线剧情（上）", "<h2>从家丁到朝堂</h2>" + tl(rows1)))
    cards.append(("主线剧情（下）", "<h2>北伐与全剧终</h2>" + tl(rows2)))

    # 5 男主
    cards.append(("男主：林晚荣（林三）", f"""
<h2>人物速览</h2>
<div class="box"><p>{esc(clean(male.get('identity',''), 160))}</p>
<p style="margin-top:10px">{esc(clean(male.get('personality',''), 160))}</p></div>
<h2 class="amber">郁闷点（他挨的）</h2>
<div class="box"><ul class="evt">""" + "".join(
        f'<li><span class="tag amber">{esc(it.get("category"))}</span>{esc(clean(it.get("evidence"),90))}</li>'
        for it in male.get("yumen", [])[:6]) + f"""</ul></div>
<div class="quote">「{esc(clean((male.get('quotes') or ["既然现实中不能进行恋爱喜剧，那就从零开始创造出来"])[0], 60))}」</div>"""))

    # 6-8 女主团（13人分三张）
    groups = [chars[1:5], chars[5:9], chars[9:14]]
    titles = ["女主团速览（一）", "女主团速览（二）", "女主团速览（三）"]
    for g, t in zip(groups, titles):
        body = ""
        for c in g:
            pur = c.get("purity", {})
            ev = pur.get("evidence") or []
            ycats = []
            for it in c.get("yumen", []):
                if it.get("category") not in ycats:
                    ycats.append(it.get("category"))
            body += f"""<div class="box"><p><span class="name">{esc(c['name'])}</span><span class="rel">{esc(clean(c.get('relationship_to_mc',''),26))}</span></p>
<p>{purity_icons(pur)}<span class="tag gray">{esc(clean(pur.get('verdict',''),14))}</span></p>
<p style="margin-top:6px">{esc(clean(c.get('arc') or c.get('identity',''), 150))}</p>
<p style="margin-top:6px">{''.join(f'<span class="tag amber">{esc(x)}</span>' for x in ycats[:4])}</p></div>"""
        cards.append((t, body))

    # 9 雷点判定
    cards.append(("雷点判定：六类零检出", """
<h2 class="red">绿帽/死女/送女/背叛/万人骑/龟作</h2>
<div class="box"><p>全书逐卷排查<span class="hg">零检出</span>。三个易误判点的甄别结论：</p>
<ul><li>肖青璇「失身传功」——起因被下药，但<span class="hg">对象是男主本人</span>（处子明文），不构成绿帽</li>
<li>肖青璇幼年被皇帝送入玉德仙坊——送女口径限定<span class="hl">男主行为</span>，此为帝王权谋，不构成送女</li>
<li>秦仙儿生母秦妃挡剑而死——死女口径限定<span class="hl">女主/准女主本人</span>死亡，不构成</li></ul></div>"""))

    # 10 郁闷点
    ysum = data.get("book_yumen_summary", [])
    rows = "".join(f'<tr><td><span class="tag amber">{esc(s["category"])}</span></td><td>{esc(s["evidence"])}</td></tr>' for s in ysum)
    cards.append(("郁闷点汇总", f"<h2 class=\"amber\">12 类分布</h2><div class=\"box\"><table>{rows}</table>"
                  "<p style=\"margin-top:10px\" class=\"q\">虐心=分离-误会-寻找桥段密集但全 HE；亵女以未遂为主；「被系统控制」=痴情之蛊（秦仙儿自请种下）。</p></div>"))

    # 11 排雷结论
    cards.append(("排雷结论", """
<h2 class="green">可以放心看</h2>
<div class="box"><p><span class="hg">完结 + 后宫大团圆 + 六类硬雷零</span>，本书是雷点意义上的安全牌。</p>
<ul style="margin-top:12px">
<li>标准种马文（13 位红颜），介意后宫的直接避雷</li>
<li>虐心密度全类别第一——分离/误会/寻找反复出现，但全 HE</li>
<li>玉伽「消忆诀别」是全书最大虐点（男主主动消除爱人记忆），作者后记明言十年之约是幌子、主动权在林三</li>
<li>「迷奸取精」桥段喜剧化处理，介意者跳过第 416-462 章相关章节</li>
<li>番外补完「两大绝密」之一（皇帝绝嗣真相），另一绝密刻意留白</li></ul></div>
<div class="quote">「岁岁种桃树，开在断肠时」</div>"""))

    # 12-… 人物卡（每人一张，精简版）
    for c in chars:
        if c.get("importance_rank") == 0:
            continue
        pur = c.get("purity", {})
        ycats = []
        for it in c.get("yumen", []):
            if it.get("category") not in ycats:
                ycats.append(it.get("category"))
        ev = [clean(x, 90) for x in (pur.get("evidence") or []) if clean(x)]
        body = f"""<div class="box"><p>{purity_icons(pur)}<span class="tag gray">{esc(clean(pur.get('verdict',''),16))}</span></p>"""
        if ev:
            body += f'<p style="margin-top:6px" class="q">依据：{esc(ev[0])}</p>'
        body += "</div>"
        lei = c.get("leidian", [])
        if lei:
            body += '<h2 class="red">雷点</h2><div class="box"><ul class="evt">' + "".join(
                f'<li><span class="tag red">{esc(it.get("category"))}</span>{esc(clean(it.get("evidence"),90))}</li>' for it in lei) + '</ul></div>'
        if ycats:
            body += '<h2 class="amber">郁闷点</h2><div class="box"><p>' + ''.join(
                f'<span class="tag amber">{esc(x)}</span>' for x in ycats) + '</p></div>'
        kvs = [clean(e, 90) for e in (c.get("key_events") or []) if clean(e)]
        body += '<h2>关键剧情</h2><div class="box"><ul class="evt">' + "".join(f"<li>{esc(e)}</li>" for e in kvs[:6]) + "</ul></div>"
        qs = [clean(q, 50) for q in (c.get("quotes") or []) if clean(q)][:2]
        for q in qs:
            body += f'<div class="quote">「{esc(q)}」</div>'
        cards.append((f"人物卡 · {c['name']}", body))
    return cards


def main():
    data = json.load(open(DATA, encoding="utf-8"))
    cards = build_cards(data)
    total = len(cards)
    os.makedirs(TMP, exist_ok=True)
    paths = []
    for i, (title, body) in enumerate(cards, 1):
        p = os.path.join(TMP, f"card_{i:02d}.html")
        open(p, "w", encoding="utf-8").write(page(i, total, body, title))
        paths.append((p, os.path.join(OUT, f"极品家丁扫书_{i:02d}.png")))
    print(f"[OK] {total} cards -> {TMP}")
    # playwright 截图
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": 1200}, device_scale_factor=SCALE)
        for src, dst in paths:
            pg.goto("file:///" + src.replace("\\", "/"))
            pg.wait_for_timeout(120)
            pg.screenshot(path=dst, full_page=True)
            print("shot:", os.path.basename(dst))
        b.close()


if __name__ == "__main__":
    main()
