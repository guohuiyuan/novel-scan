# -*- coding: utf-8 -*-
"""
novel-scan: textfmt.py —— 渲染/组装共用的小文本处理

目前只放一件事：把「雷点 / 郁闷点」条目里开头的人称代词换回角色名。

为什么需要：子代理写证据时习惯顺着上文写「她随身带着卫星电话……」，单看角色条目
没问题（标题就是人名），但汇总到书评开头的「雷点与郁闷点概况」里，24 条全是「她」，
读者根本不知道说的是谁——必须逐条带人名。

为什么只换「她」、绝不碰「他」（2026-11-18 踩过）：
  默认被扫的角色是女性，条目里的「她」基本就是本条主角。早先写成 `PRONOUNS = "她他"`，
  于是「为留在他身边，她当面扯掉外衣……」里第一个代词是**男主**的「他」，被换成了
  本条角色名，变成「**为留在关雅妮身边**，她当面扯掉外衣」——语义直接反了。
  同一条证据里「她」是主角、「他」是男主，只有前者能换。男主的「他」要换，必须由
  调用方显式传 gender="男"。
"""
FEMALE, MALE = "她", "他"
NEAR_START = 20                       # 代词出现在前 20 字内才替换：再往后，多半指的不是本条主角
PLURAL_TAIL = "们俩"                  # 「她们/她俩」是复数，换成人名会读成「某某们」
MALE_HINTS = ("男", "male", "m", "M", "公")


def _first_clause_head(t):
    """取第一个分句（到第一个句号/分号/感叹号为止）。"""
    end = len(t)
    for sep in "。；;！!":
        k = t.find(sep)
        if k != -1:
            end = min(end, k)
    return t[:end]


def named_evidence(text, name, gender=None):
    """把条目里靠前的、与角色性别一致的人称代词换成角色名。

    保守策略，改不动就原样返回：
      - 前半句已经出现角色名 → 不动（已经够明确）；
      - 默认只换「她」；只有显式传 gender="男" 时才换「他」；
      - 「她们 / 她俩」这类复数不换；
      - 代词在第 20 字之后 → 不动；
      - 只在第一句（第一个句号/分号前）里找，避免误伤后文的代词。
    """
    t = (text or "").strip()
    if not t or not name or name in t[:30]:
        return t
    pron = MALE if str(gender or "") in MALE_HINTS else FEMALE
    head = _first_clause_head(t)
    for i, ch in enumerate(head):
        if ch != pron:
            continue
        if i > NEAR_START:
            return t
        nxt = head[i + 1] if i + 1 < len(head) else ""
        if nxt in PLURAL_TAIL:
            return t
        return t[:i] + name + t[i + 1:]
    return t


if __name__ == "__main__":
    # 回归用例：`python textfmt.py` 必须全部 ok。第二条就是 2026-11-18 报的 bug。
    cases = [
        ("她随身带着卫星电话却主动藏进树林", "许念欣",
         "许念欣随身带着卫星电话却主动藏进树林"),
        ("为留在他身边，她当面扯掉外衣只剩内衣", "关雅妮",
         "为留在他身边，关雅妮当面扯掉外衣只剩内衣"),   # 男主的「他」不能动
        ("她们三个一起去了海岛", "曾柔", "她们三个一起去了海岛"),          # 复数不换
        ("关雅妮自己也不知道", "关雅妮", "关雅妮自己也不知道"),            # 已有人名不换
        ("她他混排时只换她，他留给男主", "于紫彤", "于紫彤他混排时只换她，他留给男主"),
    ]
    bad = 0
    for src, nm, want in cases:
        got = named_evidence(src, nm)
        flag = "ok " if got == want else "FAIL"
        if got != want:
            bad += 1
        print(f"[{flag}] {src[:20]:<22} → {got}")
    raise SystemExit(1 if bad else 0)

