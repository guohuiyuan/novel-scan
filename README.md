<div align="center">
  <img src="logo.png" alt="novel-scan logo" width="200">
</div>

# novel-scan

长篇网文扫书 Agent Skill —— 把一本 `.txt` 小说变成一套能直接发出去的扫书稿：

1. **扫书稿 Markdown**（主交付物，对标公众号扫书帖）：标题党式大标题 + 随机封面 + 书名/作者/字数/题材/状态/平台 + 8 维评分（档位与依据同表，S→C）+ 简介 + 雷点郁闷点概况（逐条带角色名，放在简介后当接受度闸门）+ 男主卡 + 女主逐条（身份/外貌/经历线/纯洁度/性格特点/本人雷点明细/名场面台词，字段带标签、长段落按句拆段）+ 其他角色 + 分维度点评 + 数据说明
2. **人物数据 JSON + 人物卡 Markdown**：逐角色结构化数据（身份/外貌锚点/别名裁定/纯洁度四维/雷点/郁闷点），可导出手机长图
3. **人物图 / 封面**：按外貌反推 `appearance_prompt` 出图（`latent.moe`），封面从公开图库随机 roll 一张 SFW 图

## 先看效果

[`examples/都市良人行/`](examples/都市良人行) 是一次真实跑完的完整产物（111 万字 txt → 1 男主 + 11 女主 + 8 配角，
图片已降采样，全目录 0.9MB 以内）：

[封面样张](examples/都市良人行/封面.webp)

| 你能看到 | 文件 |
|---|---|
| 可直接发布的扫书稿：标题 + 封面 + 书况 + 8 维评分 + 简介 + 雷点郁闷点概况 + 男主 + 11 位女主逐条（含各自雷点明细）+ 分维度点评 | [`都市良人行_书评.md`](examples/都市良人行/都市良人行_书评.md) |
| 备查卡片：身份/别名裁定/外貌原文/纯洁度四维/雷点郁闷点/名场面台词 | [`都市良人行_人物卡.md`](examples/都市良人行/都市良人行_人物卡.md) |
| 结构化数据（给视频、知识库直接吃） | [`都市良人行_人物数据.json`](examples/都市良人行/都市良人行_人物数据.json) |
| 12 张按外貌反推的人物图 + 每张的 prompt/seed 溯源 | [`examples/都市良人行/人物图/`](examples/都市良人行/人物图) |
| 子代理实际交付的中间格式（角色片段 / 分块笔记） | [`examples/都市良人行/中间产物样例/`](examples/都市良人行/中间产物样例) |

那次跑完的自检：引文 81/81 逐字命中、12/12 角色有外貌、12/12 有名场面台词、8/8 评分齐全、成品行号残留 0。

## 核心理念

- **线索 ≠ 事实**：任何没落原文的陈述不许进成品。子代理直接读原文、边读边记，幻觉在源头被杜绝——没有"事后清洗"阶段
- **成品无行号**：阅读界面无法跳转行号，用 ≤50 字原文引文定位（可全文搜索验证）；行号只进内部笔记
- **外貌是一等公民**：每个角色必须有可复述的外形锚点（发色/瞳色/体态/标志物），作者没写就明说，禁止按模板脑补
- **名场面台词逐字照抄**：留给 TTS/分镜做扫书视频，改一个字口型就不对
- **雷点/郁闷点有唯一口径**：雷点 6 类 / 郁闷点 26 类 + 「初/处」术语，见 `references/leidian-taxonomy.md`
- **纯洁度四维**（处/精神初/初婚/初摸）证据不足一律记"未知"，禁止默认全初

## 流程

```
A0 脚本预扫（纯正则，秒级；切块 + 人物候选 + 外貌/雷点线索 + 重复收录检测）
→ B 分块扫描（子代理 6-8 并行，一块一次 Read 读完）
→ C 逐人物汇总（每人一份拼装切片 → 角色 JSON + 笔记）
→ C2 书级字段（一个子代理写全书：书况/8 维评分/简介/男主/分维度点评/标题卖点）
→ D 组装交付（合并 JSON → 封面 roll → 书评 md → 人物卡 md → 审计 → 人物图 → 手机长图）
```

## 文件结构

```
logo.png                      # 项目 logo（README 顶部展示）
SKILL.md                      # 主流程（Agent 读取的入口）
references/
  leidian-taxonomy.md         # 雷点/郁闷点分类学（唯一判定口径）
  subagent-prompt.md          # 分块扫描/逐人物/JSON/书级字段四套模板
  pitfalls.md                 # 多本书实跑沉淀的历史教训
scripts/
  prescan.py                  # 预扫：切块表、人物候选、外貌/雷点线索、--digest 拼装切片
  detect_dup_range.py         # txt 混了两版时找重复边界（规范化窗口比对）
  roster_check.py             # 合并块笔记出场角色表，抓"有出场但没 JSON"的漏人
  assemble_json.py            # 合并角色 JSON + 书级字段，聚合全书雷点/郁闷点
  render_bookreview_md.py     # JSON → 扫书稿（标题 + 封面 + 评分 + 人物 + 排雷）
  render_characters_md.py     # JSON → 人物卡 Markdown（无行号版）
  render_characters_html.py   # JSON → 可视化 HTML（备用）
  render_tieba_cards.py       # md 原格式 → 贴吧手机端连图
  gen_portraits.py            # 按 appearance_prompt 出人物图（latent.moe，要 key；seed 按角色名派生可复现）
  pick_cover.py                # 书评封面：公开图库随机 roll 一张 SFW 图（免 key）
  merge_sections.py           # 章节合并 + 目录锚点
  make_example.py             # 把一次输出做成 examples/<书名> 展示副本（人物图降采样）
  check_links.py              # 校验 md 里的相对链接/图片是否指得实（挪目录、改名后必跑）
  audit_deliverables.py       # 交付前自检：引文逐字/外貌/名场面/书级字段/行号残留
examples/
  都市良人行/                  # 完整效果示例（书评 + 人物卡 + JSON + 封面 + 12 张人物图）
    README.md                 # 该次输出的导读（产物清单、审计结论、如何复现）
```

## 安装（WorkBuddy / Claude Code 类 Agent）

复制到用户级 skill 目录即可：

```bash
git clone https://github.com/guohuiyuan/novel-scan.git ~/.workbuddy/skills/novel-scan
```

出图需要配套的 `latent-media` skill；只跑扫读与封面则不需要任何 key。

## 声明

- 产出的扫书报告对外传播时必须保留「AI 辅助生成」标注
- 雷点/郁闷点判定标准已内置于 `references/leidian-taxonomy.md`

## License

GNU Affero General Public License v3.0 (AGPL-3.0)
