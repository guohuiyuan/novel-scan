# -*- coding: utf-8 -*-
"""
novel-scan: textfmt.py —— 渲染/组装共用的小文本处理

目前只放一件事：把「雷点 / 郁闷点」条目里开头的人称代词换回角色名。

为什么需要：子代理写证据时习惯顺着上文写「她随身带着卫星电话……」，单看角色条目
没问题（标题就是人名），但汇总到书评开头的「雷点与郁闷点概况」里，24 条全是「她」，
读者根本不知道说的是谁——必须逐条带人名。
"""
PRONOUNS = "她他"
NEAR_START = 20          # 代词出现在前 20 字内才替换：再往后，多半指的不是本条主角


def named_evidence(text, name):
    """把条目里靠前的第一个人称代词换成角色名。

    保守策略，改不动就原样返回：
      - 前半句已经出现角色名 → 不动（已经是明确的）；
      - 代词出现在第 20 字之后 → 不动（可能是「禹言把她推给……」里的她，也可能指别人）；
      - 只在第一句（第一个句号/分号前）里找，避免误伤后文的代词。
    """
    t = (text or "").strip()
    if not t or not name or name in t[:30]:
        return t
    head_end = len(t)
    for sep in "。；;！!":
        k = t.find(sep)
        if k != -1:
            head_end = min(head_end, k)
    head = t[:head_end]
    for i, ch in enumerate(head):
        if ch in PRONOUNS:
            if i <= NEAR_START:
                return t[:i] + name + t[i + 1:]
            break
    return t
