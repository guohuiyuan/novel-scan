#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
novel-scan: prescan.py —— 确定性预扫（2 秒级，纯本地，不花 token）

解决三件事：
1. 分块表：卷级/章级区间 + 每块 ≤ chunk_lines 行（一块一次 Read 读完，避免子代理
   反复读同一前缀导致的上下文平方膨胀）。
2. 候选清单：人物名频次、外貌描写命中行、雷点/郁闷点关键词命中行。子代理从
   "逐行读书"变成"审候选 + 补剧情"，省掉大量无信息量的扫描。
3. C 阶段输入：--digest 把 24 份分卷笔记里跟某人物相关的行拼成一个小文件，
   替代"每个角色重读全部笔记"。

用法：
  # 预扫（A 阶段，一次）
  python prescan.py --novel <原文.txt> --out <输出目录> [--chunk-lines 2000] [--top 60]

  # 按人物拼装笔记摘录（C 阶段，每个角色一次）
  python prescan.py --digest --notes <输出目录>/scan_notes --out <输出目录> \
      --character <人物名> [--alias 别名1 --alias 别名2]

产物（都在 <输出目录>/_prescan/ 下）：
  summary.md            统计与成本估算
  chunks.tsv            分块表（块号/卷/起止行/章名）
  characters.tsv        人物候选（名/频次/首现行/说-类上下文命中数）
  appearance.md         外貌线索（按人物归并，带行号）
  leidian_candidates.md 雷点/郁闷点关键词命中
  state.json            断点状态（子代理完成一块就把 done 置 true）
"""
import argparse
import bisect
import json
import os
import re
import sys
from collections import Counter, defaultdict

# ---------------------------------------------------------------- 读文件

def read_text(path):
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read(), enc
        except (UnicodeDecodeError, LookupError):
            continue
    raise SystemExit("[ERROR] 无法识别编码：%s" % path)


# ---------------------------------------------------------------- 结构切分

CN_NUM = "0-9０-９一二三四五六七八九十百千零〇两.．"
_PREFIX = r"^[\s#＃=\-—]{0,10}(?:正文\s*)?"
VOL_RE = re.compile(
    _PREFIX + r"第\s*([" + CN_NUM + r"]+)\s*([卷部集篇])\s*(.{0,40})$")
VOL_RE2 = re.compile(r"^[\s#＃=\-—]{0,10}卷\s*([" + CN_NUM + r"]+)\s*(.{0,40})$")
CH_RE = re.compile(
    _PREFIX + r"第\s*([" + CN_NUM + r"]+)\s*([章节回])\s*(.{0,40})$")
# 行内任意位置出现「第X章/节/回」→ 这一行是章节标题，不是卷标题
IN_CH = re.compile(r"第\s*[" + CN_NUM + r"]+\s*[章节回]")


def scan_structure(lines):
    """返回 (volumes, chapters)。volumes/chapters 元素为 (title, line_no 1-based)。"""
    vols, chaps = [], []
    for i, ln in enumerate(lines, 1):
        if len(ln) > 60:          # 标题行不会太长
            continue
        m = VOL_RE.match(ln) or VOL_RE2.match(ln)
        if m and not IN_CH.search(ln):
            vols.append((ln.strip()[:40], i))
            continue
        m = CH_RE.match(ln)
        if m:
            chaps.append((ln.strip()[:40], i))
    # 卷标记太少 / 太靠后 / 间距太密（其实是章节标题）→ 认为本书不分卷
    if len(vols) < 3 or vols[0][1] > len(lines) * 0.25:
        vols = []
    elif len(vols) > 3:
        gaps = [b[1] - a[1] for a, b in zip(vols, vols[1:])]
        gaps.sort()
        if gaps[len(gaps) // 2] < 300:
            vols = []
    return vols, chaps


def build_chunks(total_lines, vols, chaps, chunk_lines):
    """按卷切块；卷内再按 chunk_lines 切；无卷则整本切。"""
    if vols:
        bounds = [(t, s) for t, s in vols] + [("<END>", total_lines + 1)]
    else:
        bounds = [("全书", 1), ("<END>", total_lines + 1)]
    chunks = []
    chap_lines = sorted(l for _, l in chaps)
    for idx in range(len(bounds) - 1):
        vtitle, vstart = bounds[idx]
        vend = bounds[idx + 1][1] - 1
        if vend < vstart:
            continue
        vlabel = vtitle if vols else "全书"
        part = 0
        cur = vstart
        while cur <= vend:
            part += 1
            end = min(cur + chunk_lines - 1, vend)
            # 落点附近有章标题就对齐到章首，别在句子中间切块（±15% 容差）
            tol = max(60, chunk_lines // 10)
            ideal = end + 1
            cand = [cl for cl in chap_lines if abs(cl - ideal) <= tol and cl > cur + chunk_lines // 3]
            if cand:
                end = min(cand, key=lambda cl: abs(cl - ideal)) - 1
            # 块内章节标题，便于子代理确认自己在哪
            heads = [t for t, l in chaps if cur <= l <= end][:3]
            cid = ("%s_%02d" % (vlabel, part)) if vols else ("块%02d" % part)
            chunks.append({
                "id": cid, "volume": vlabel, "start": cur, "end": end,
                "lines": end - cur + 1, "chapter_heads": heads,
                "note": "scan_notes/%s.md" % cid, "done": False,
            })
            cur = end + 1
    return chunks


# ---------------------------------------------------------------- 人物候选

NAME_CTX = re.compile(
    r"([\u4e00-\u9fa5]{2,3})(?="
    r"说道|笑道|问道|答道|喝道|叹道|叫道|骂道|沉声道|冷声道|轻声道|低声道|开口道"
    r"|开口|皱眉|点头|摇头|冷哼|苦笑|一愣|一笑|抬头|低头|伸手|转身|看着|笑了)")

# 先从「说-类」后缀命中位置回看 2-3 字，比逐行宽匹配快两个数量级
SUFFIXES = [
    "沉声道", "冷声道", "轻声道", "低声道", "开口道", "说道", "笑道", "问道", "答道",
    "喝道", "叹道", "叫道", "骂道", "开口", "皱眉", "点头", "摇头", "冷哼", "苦笑",
    "一愣", "一笑", "抬头", "低头", "伸手", "转身",
]
_SUFFIX_RE = re.compile("|".join(sorted(SUFFIXES, key=len, reverse=True)))
_CJK3 = re.compile(r"[\u4e00-\u9fa5]{3}$")
_CJK2 = re.compile(r"[\u4e00-\u9fa5]{2}$")

STOP = set("""
的时候 这样 那样 一个 这个 那个 自己 他们 我们 你们 什么 怎么 但是 因为 所以
然后 现在 已经 只是 可是 就是 不是 一点 有些 没有 知道 觉得 看着 忽然 终于
一声 一切 起来 出来 过去 之后 之前 说话 心里 眼中 脸上 手里 身上 时候 似乎
仿佛 如果 于是 而且 不过 还有 两人 三人 众人 那人 这人 别人 对方 男人 女人
少年 少女 老头 老者 大汉 女子 男子 声音 目光 神色 表情 地方 东西 事情
不敢 不能 不会 不知 不忍 不肯 不想 不愿 不得 不觉 不禁 不由 不住 不断
急忙 慌忙 连忙 赶紧 赶快 立刻 马上 顿时 登时 突然 猛然 陡然 缓缓 慢慢
轻轻 悄悄 默默 淡淡 微微 稍稍 渐渐 徐徐 匆匆 连连 频频 一再 只好 只能
点头 摇头 抬头 低头 回头 转头 皱眉 蹙眉 挑眉 眯眼 睁眼 闭眼 叹气 苦笑
冷笑 冷哼 轻笑 微笑 大笑 一笑 一愣 一怔 一顿 开口 转身 伸手 拍手 摆手
挥手 拱手 抱拳 起身 站起 坐下 走近 后退 停下 沉声 冷声 低声 轻声 大声
高声 小声 柔声 厉声 厉喝 温声 应道 答道 说道 笑道 问道 叹道 续道 接道
望着 盯着 瞧了 听着 想着 笑着 说着 看了 想了 暗道 心道 心中 心底
眼里 口中 嘴边 面前 身后 身边 身边 上面 下面 里面 外面 前面 后面
大家 所有 全部 一起 一直 依旧 依然 果然 竟然 居然 显然 自然 当然
小姐 公子 夫人 大人 师父 师兄 师姐 师妹 姑娘 娘子 老爷 少爷 丫鬟 管家
掌柜 书生 道士 和尚 摊主 小二 护卫 家丁 侍女 侍从 随从 首领 长老
哈哈 嘻嘻 咯咯 嘿嘿 呵呵 哎呀 哎哟 见他 见她 见他们 急急 仙子 仙子们
姐姐 妹妹 哥哥 弟弟 姐姐们 兄弟们 众人 满脸 一脸 连声 失声 低声 高声
""".split())

# 名字里不该出现的功能字（含这些基本是副词/短语误判）
BAD_CHARS = set("的了着过是在和与就都也还又很便却才再已正仍只更最太挺偏不没么样个些地得然")
BAD_TAIL = set("地得然着了是在有么样边里上下中前后个些")

ALIAS_PREFIX = ("小", "阿", "老")


def line_index(text):
    """所有行首偏移；配合 line_of 把字符位置换成 1-based 行号。"""
    starts = [0]
    i = 0
    while True:
        j = text.find("\n", i)
        if j < 0:
            break
        starts.append(j + 1)
        i = j + 1
    return starts


def line_of(starts, pos):
    return bisect.bisect_right(starts, pos)


def ok_name(n):
    if n in STOP or len(n) < 2:
        return False
    if any(ch in BAD_CHARS for ch in n):
        return False
    return n[-1] not in BAD_TAIL


def find_candidates(text, starts, top_n):
    c3, c2, first = Counter(), Counter(), {}
    kinds3, kinds2 = defaultdict(set), defaultdict(set)
    for m in _SUFFIX_RE.finditer(text):
        s = m.start()
        suf = m.group(0)
        if s >= 3:
            n3 = text[s - 3:s]
            if _CJK3.match(n3) and ok_name(n3):
                c3[n3] += 1
                kinds3[n3].add(suf)
                first.setdefault(n3, line_of(starts, s - 3))
        if s >= 2:
            n2 = text[s - 2:s]
            if _CJK2.match(n2) and ok_name(n2):
                c2[n2] += 1
                kinds2[n2].add(suf)
                first.setdefault(n2, line_of(starts, s - 2))
    # 「唐晓茜」的尾两字「晓茜」会被重复计入 → 若长名覆盖了短名的大部分命中就丢掉短名
    names = {n: c for n, c in c3.items() if len(kinds3[n]) >= 2}
    by_tail = {}
    for n, c in names.items():
        by_tail.setdefault(n[-2:], []).append(c)
    for n, c in c2.items():
        if len(kinds2[n]) < 2 or c < 6:   # 只出现在一两种「说道」里的，多半是副词碎片
            continue
        longer = by_tail.get(n)
        if longer and max(longer) >= 0.6 * c:
            continue
        names[n] = names.get(n, 0) + c
    # 全文出现次数只对候选前若干名统计（str.count 对每名都要扫全文，不能全量做）
    pre = sorted(names.items(), key=lambda kv: -kv[1])[: max(top_n * 3, 150)]
    raw = {n: text.count(n) for n, _ in pre}
    # 末轮过滤：真名几乎一定以「X的」形式出现过（"林晚荣的"），副词碎片不会
    raw = {n: c for n, c in raw.items()
           if text.count(n + "的") >= 3 or names[n] >= 80}
    ranked = [n for n, _ in sorted(raw.items(), key=lambda kv: -kv[1])
              if names[n] >= 3 or raw[n] >= 200]
    return [(n, raw[n], first.get(n, 0), names[n]) for n in ranked[:top_n]]


# ---------------------------------------------------------------- 外貌线索

APPEAR_STRONG = [
    "容貌", "容颜", "长相", "五官", "面容", "脸蛋", "脸庞", "眉眼", "眼眸", "眸子",
    "瞳孔", "肌肤", "肤色", "白皙", "雪白", "娇嫩", "长发", "短发", "秀发", "银发",
    "金发", "白发", "马尾", "麻花辫", "丸子头", "盘发", "刘海", "腰肢", "纤腰",
    "身段", "酥胸", "双峰", "玉腿", "长腿", "身高", "一袭", "冷艳", "清丽", "妖娆",
    "妩媚", "绝美", "胎记", "酒窝", "锁骨", "俏脸", "瓜子脸", "鹅蛋脸", "身姿",
    "曲线", "纤手", "藕臂", "香肩", "玉颈", "耳垂", "明眸", "凤眼", "桃花眼",
]
APPEAR_WEAK = [
    "皮肤", "身材", "眼睛", "脸", "头发", "裙子", "衣服", "漂亮", "好看", "可爱",
    "气质", "手指", "嘴唇", "眉毛", "鼻子", "红衣", "白衣", "黑衣", "青衫", "校服",
    "旗袍", "长裙", "短裙", "外套", "衬衫", "高跟鞋", "耳环", "项链", "珠子",
]

_APPEAR_RE = re.compile("|".join(APPEAR_STRONG))
_APPEAR_WEAK_RE = re.compile("|".join(APPEAR_WEAK))


def appearance_hits(lines, names, cap_per_char=40, cap_orphan=120):
    """返回 (by_char, orphan)：by_char[name] = [(line_no, text)]"""
    by_char = defaultdict(list)
    orphan = []
    name_re = {n: re.compile(re.escape(n)) for n, *_ in names}
    for i, ln in enumerate(lines, 1):
        if not ln.strip() or len(ln) > 400:
            continue
        strong = bool(_APPEAR_RE.search(ln))
        weak_n = len(set(_APPEAR_WEAK_RE.findall(ln)))
        if not strong and weak_n < 2:
            continue
        hit = [n for n, r in name_re.items() if r.search(ln)]
        text = ln.strip()[:140]
        if not hit:
            # 上下各一行里有名字也算（对话/动作分行写的书很常见）
            for j in (i - 2, i):
                if 0 <= j < len(lines):
                    for n, r in name_re.items():
                        if r.search(lines[j]):
                            hit.append(n)
                    if hit:
                        break
            if not hit:
                if strong and len(orphan) < cap_orphan:
                    orphan.append((i, text))
                continue
        for n in set(hit):
            if len(by_char[n]) < cap_per_char:
                by_char[n].append((i, text))
    return by_char, orphan


# ---------------------------------------------------------------- 雷点/郁闷点候选

LEIDIAN_KW = {
    "绿帽": ["绿帽", "戴绿", "出轨", "偷情", "劈腿", "跟了别人", "被别人睡", "头顶草原"],
    "死女": ["香消玉殒", "咽了气", "没了呼吸", "停止了呼吸", "葬礼", "墓碑", "坟前", "遗体"],
    "送女": ["让给别人", "送给别人", "拱手相让", "嫁给别人", "许配给别", "让了出去"],
    "背叛": ["背叛", "出卖", "反水", "叛变", "倒戈", "卖主"],
    "万人骑": ["人尽可夫", "公交车", "卖身", "娼", "妓", "被很多男人", "来者不拒"],
    "龟作": ["忍气吞声", "当龟", "舔狗", "认怂", "低声下气", "不敢还手"],
}
YUMEN_KW = {
    "非处": ["不是处女", "已非完璧", "早不是处", "被破身", "失了身", "不再干净"],
    "亵女": ["摸胸", "揉胸", "袭胸", "走光", "春光", "裙底", "偷窥", "被摸", "舔了", "按在胸口"],
    "强暴": ["强奸", "强暴", "迷奸", "轮奸", "下药", "春药", "催情", "强行要了"],
    "怀孕": ["怀孕", "有喜", "怀了", "打胎", "流产", "堕胎"],
    "婚约": ["婚约", "订婚", "指腹为婚", "娃娃亲", "嫁给", "娶了"],
    "初吻": ["初吻", "第一次亲", "吻了她", "亲了他"],
    "虐主": ["跪下", "打断", "折断", "吐血", "濒死", "被吊", "折磨"],
    "百合": ["两个女人", "女人和女人", "女女", "磨镜"],
    "漏女": ["没有交代", "再无音讯", "不知去向", "再也没有出现"],
    "接盘": ["接盘", "喜当爹", "养别人"],
    "拉皮条": ["介绍给", "送到床上", "陪客", "陪睡"],
    "擦边": ["贴在身上", "身体贴", "肌肤相亲", "被抱住", "搂在怀里"],
}


def keyword_hits(text, starts, lines, table, cap_per_cat=150):
    """按类目做一次 alternation 扫描，比逐行 any() 快一个数量级。"""
    out = {}
    for cat, kws in table.items():
        rx = re.compile("|".join(sorted((re.escape(k) for k in kws), key=len, reverse=True)))
        hits, last = [], -1
        for m in rx.finditer(text):
            ln = line_of(starts, m.start())
            if ln == last:
                continue
            last = ln
            hits.append((ln, lines[ln - 1].strip()[:120]))
            if len(hits) >= cap_per_cat:
                break
        if hits:
            out[cat] = hits
    return out


# ---------------------------------------------------------------- 输出

def write(path, s):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(s)


def cmd_scan(args):
    text, enc = read_text(args.novel)
    lines = text.split("\n")
    starts = line_index(text)
    total = len(lines)
    chars = len(text)
    vols, chaps = scan_structure(lines)
    chunks = build_chunks(total, vols, chaps, args.chunk_lines)
    names = find_candidates(text, starts, args.top)
    # 外貌归并只认前 30 名候选，避免"脸皮/焦急"这类碎片把行抢走
    by_char, orphan = appearance_hits(lines, names[:30], cap_per_char=15, cap_orphan=60)
    lei = keyword_hits(text, starts, lines, LEIDIAN_KW)
    yu = keyword_hits(text, starts, lines, YUMEN_KW)

    pd = os.path.join(args.out, "_prescan")
    os.makedirs(pd, exist_ok=True)
    os.makedirs(os.path.join(args.out, "scan_notes"), exist_ok=True)

    # chunks.tsv
    rows = ["chunk\tvolume\tstart\tend\tlines\tchapters"]
    for c in chunks:
        rows.append("%s\t%s\t%d\t%d\t%d\t%s" % (
            c["id"], c["volume"], c["start"], c["end"], c["lines"],
            " / ".join(c["chapter_heads"])))
    write(os.path.join(pd, "chunks.tsv"), "\n".join(rows) + "\n")

    # characters.tsv
    rows = ["name\tfreq\tfirst_line\tsay_ctx"]
    for n, f, fl, sc in names:
        rows.append("%s\t%d\t%d\t%d" % (n, f, fl, sc))
    write(os.path.join(pd, "characters.tsv"), "\n".join(rows) + "\n")

    # appearance.md
    out = ["# 外貌线索（脚本抽取，需逐条回原文裁定）", "",
           "> 命中行按人物归并；行号只用于回原文核对，**成品正文不写行号**。",
           "> `?` = 该行未出现人物名，靠上下文推断，优先级低。", ""]
    for name, hits in sorted(by_char.items(), key=lambda kv: -len(kv[1])):
        out.append("## %s（命中 %d 行）" % (name, len(hits)))
        for ln_no, t in hits:
            out.append("- L%d %s" % (ln_no, t))
        out.append("")
    if orphan:
        out.append("## ? 未归属（含外貌硬指标但上下文无候选名）")
        for ln_no, t in orphan[:80]:
            out.append("- L%d %s" % (ln_no, t))
        out.append("")
    write(os.path.join(pd, "appearance.md"), "\n".join(out))

    # 雷点候选
    out = ["# 雷点/郁闷点候选命中（关键词粗筛，**必须逐条回原文判断，命中≠成立**）", ""]
    for title, table in (("雷点候选", lei), ("郁闷点候选", yu)):
        out.append("## " + title)
        if not table:
            out.append("- （无命中）")
        for cat, hits in sorted(table.items(), key=lambda kv: -len(kv[1])):
            out.append("### %s（%d 处）" % (cat, len(hits)))
            for ln_no, t in hits:
                out.append("- L%d %s" % (ln_no, t))
        out.append("")
    write(os.path.join(pd, "leidian_candidates.md"), "\n".join(out))

    # 按块切片：每个子代理只读自己那一段的线索，几百行而不是上千行
    slice_dir = os.path.join(pd, "chunks")
    os.makedirs(slice_dir, exist_ok=True)
    for c in chunks:
        a, b = c["start"], c["end"]
        o = ["# 本块线索 · %s（L%d-L%d）" % (c["id"], a, b), ""]
        if c["chapter_heads"]:
            o.append("章名：" + " / ".join(c["chapter_heads"]))
            o.append("")
        ap = [(n, [(ln, t) for ln, t in hits if a <= ln <= b])
              for n, hits in by_char.items()]
        ap = [(n, h) for n, h in ap if h]
        ap.sort(key=lambda kv: -len(kv[1]))
        ap = ap[:15]
        o.append("## 外貌命中（本块）")
        if ap:
            for n, hits in ap:
                o.append("### %s" % n)
                o.extend("- L%d %s" % (ln, t) for ln, t in hits[:8])
        else:
            o.append("- （本块无）")
        o.append("")
        o.append("## 雷点/郁闷点候选（本块）")
        any_hit = False
        for title, table in (("雷点", lei), ("郁闷点", yu)):
            for cat, hits in sorted(table.items(), key=lambda kv: -len(kv[1])):
                sub = [(ln, t) for ln, t in hits if a <= ln <= b]
                if not sub:
                    continue
                any_hit = True
                o.append("### [%s] %s（%d 处）" % (title, cat, len(sub)))
                o.extend("- L%d %s" % (ln, t) for ln, t in sub[:6])
        if not any_hit:
            o.append("- （本块无）")
        o.append("")
        o.append("> 命中 ≠ 成立。逐条回原文看一眼，成立的写进笔记（带行号+≤50字引文），")
        o.append("> 不成立的直接丢掉，不要为凑数写「未归类」。")
        write(os.path.join(slice_dir, c["id"] + ".md"), "\n".join(o) + "\n")

    # state.json
    state = {
        "novel": os.path.abspath(args.novel), "encoding": enc,
        "chars": chars, "lines": total, "chunk_lines": args.chunk_lines,
        "volumes": len(vols), "chapters": len(chaps),
        "chunks": chunks,
    }
    write(os.path.join(pd, "state.json"),
          json.dumps(state, ensure_ascii=False, indent=1))

    # summary.md
    est_tokens = chars * 0.7
    lines_out = [
        "# 预扫结果", "",
        "- 原文：`%s`（编码 %s）" % (args.novel, enc),
        "- 规模：**%.1f 万字 / %s 行**" % (chars / 10000, format(total, ",")),
        "- 结构：%d 卷 / %d 章" % (len(vols), len(chaps)) if vols else
        "- 结构：无卷标记，%d 章，按 %d 行一块切" % (len(chaps), args.chunk_lines),
        "- 分块：**%d 块**（每块 ≤%d 行，一块一次 Read 读完）" % (len(chunks), args.chunk_lines),
        "- 通读一遍的原文输入量 ≈ **%.0f 万 tokens**（一次性、不重复）" % (est_tokens / 10000),
        "- 人物候选 %d 个；外貌命中归并到 %d 人；雷点候选 %d 类 / 郁闷点候选 %d 类"
        % (len(names), len(by_char), len(lei), len(yu)), "",
        "## 后续派活建议", "",
        "1. 分块扫描：**一次并行发起 6-8 个子代理**（不是 2-4），每个只读自己那一块，"
        "一块一次 Read 读完（`limit` 设为块行数），不要回头重读。",
        "2. 每个子代理先读 `_prescan/chunks/<块号>.md`（本块的外貌命中 + 雷点候选，几 KB），"
        "再读原文那一段——判断线索 + 补剧情，不做盲扫。",
        "3. 人物汇总：每个角色先跑 `prescan.py --digest` 生成该角色的小输入，再派子代理，"
        "禁止让子代理重读全部分卷笔记。", "",
        "## Top 人物候选", "",
        "| 名 | 全文出现 | 首次行 | 说话上下文 |", "|---|---|---|---|",
    ]
    for n, f, fl, sc in names[:25]:
        lines_out.append("| %s | %d | %d | %d |" % (n, f, fl, sc))
    write(os.path.join(pd, "summary.md"), "\n".join(lines_out) + "\n")

    print("[OK] %s" % pd)
    print("  规模 %.1f万字 / %s行 | %d卷 / %d章 | 切成 %d 块（每块≤%d行）"
          % (chars / 10000, format(total, ","), len(vols), len(chaps),
             len(chunks), args.chunk_lines))
    print("  通读一遍输入量 ≈ %.0f 万 tokens（一次性）" % (est_tokens / 10000))
    print("  人物候选 %d | 外貌归并 %d 人 | 雷点候选 %d 类 | 郁闷点候选 %d 类"
          % (len(names), len(by_char), len(lei), len(yu)))
    print("  下一步：设 %d 个并行子代理，看 %s" % (min(8, len(chunks)), os.path.join(pd, "summary.md")))
    return 0


def cmd_digest(args):
    """把分卷笔记里跟某人物相关的行抽出来，拼成 C 阶段的小输入。"""
    aliases = [args.character] + list(args.alias or [])
    pats = [re.compile(re.escape(a)) for a in aliases if a]
    notes = sorted(f for f in os.listdir(args.notes) if f.endswith(".md"))
    blocks, total_hit = [], 0
    for fn in notes:
        with open(os.path.join(args.notes, fn), encoding="utf-8") as f:
            lines = f.read().split("\n")
        keep = set()
        for i, ln in enumerate(lines):
            if any(p.search(ln) for p in pats):
                for j in (i - 1, i, i + 1):        # 带前后一行，保留列表结构
                    if 0 <= j < len(lines):
                        keep.add(j)
        if keep:
            blocks.append("## %s（%d 行命中）" % (fn, len(keep)))
            prev = -9
            for j in sorted(keep):
                if j - prev > 1:
                    blocks.append("")
                blocks.append(lines[j].rstrip())
                prev = j
            blocks.append("")
            total_hit += len(keep)

    # 外貌线索里属于该人物的段
    ap_path = os.path.join(args.out, "_prescan", "appearance.md")
    ap_sec = ""
    if os.path.exists(ap_path):
        with open(ap_path, encoding="utf-8") as f:
            txt = f.read()
        m = re.search(r"^## %s（.*?)(?=^## |\Z)" % re.escape(args.character),
                      txt, flags=re.M | re.S)
        if m:
            ap_sec = "## 外貌线索（脚本预抽）\n" + m.group(0).strip() + "\n"

    body = "\n".join([
        "# %s · 分卷笔记摘录" % args.character,
        "",
        "> 脚本从 %d 份分卷笔记里抽出的相关行（含前后一行），共 %d 行。"
        % (len(notes), total_hit),
        "> 只读这个文件，**不要**再去翻全部分卷笔记；需要复核原文时按笔记里的行号定向 Grep。",
        "",
        ap_sec,
        "## 笔记正文",
        "",
    ] + blocks)
    out_dir = os.path.join(args.out, "_prescan")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "char_%s.md" % re.sub(r"[\\/:*?\"<>|]", "_",
                                                          args.character))
    write(out_path, body)
    print("[OK] %s（%d 行，%.1f KB）" % (out_path, total_hit, len(body) / 1024))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--novel")
    ap.add_argument("--out", required=True)
    ap.add_argument("--chunk-lines", type=int, default=2000)
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--digest", action="store_true")
    ap.add_argument("--notes")
    ap.add_argument("--character")
    ap.add_argument("--alias", action="append")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    if args.digest:
        if not (args.notes and args.character):
            raise SystemExit("--digest 需要 --notes 与 --character")
        return cmd_digest(args)
    if not args.novel:
        raise SystemExit("需要 --novel")
    return cmd_scan(args)


if __name__ == "__main__":
    sys.exit(main())
