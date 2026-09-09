# novel-scan

长篇轻小说/网文扫书 Agent Skill —— 把一本 `.txt` 小说变成**两件套产物**：

1. **人物数据 JSON + 人物卡 Markdown**：逐角色结构化数据（身份/别名/纯洁度四维判定/雷点/郁闷点），渲染成人物卡
2. **情节速览报告**：分卷梗概表 + 人物速览 + 雷点/郁闷点汇总 + 排雷结论

## 核心理念

- **线索 ≠ 事实**：任何没落原文的陈述不许进成品。子代理直接读原文、边读边记，幻觉在源头被杜绝——没有"事后清洗"阶段
- **agent 自扫主路径**：完全自包含，不依赖任何外部项目、LLM 抽取流水线或本地路径产物
- **成品无行号**：阅读界面无法跳转行号，用 ≤50 字原文引文定位（可全文搜索验证）；行号只进内部笔记
- **雷点/郁闷点有唯一口径**：男性向网文毒点分类学（雷点 6 类 / 郁闷点 26 类 + 「初/处」术语），见 `references/leidian-taxonomy.md`，禁止泛化为"读起来难受的情节"
- **纯洁度四维**（处/精神初/初婚/初摸）证据不足一律记"未知"，禁止默认全初

## 流程

```
A 侦察（卷级行号区间 + 人物频次）
→ B 分卷扫描（子代理并行直读原文，边读边记笔记）
→ C 逐人物汇总（归并笔记 → 回原文复核 → 产出角色 JSON）
→ D 组装交付（合并 JSON → 人物卡 md → 情节速览报告 → 引文审计）
```

## 文件结构

```
SKILL.md                      # 主流程（Agent 读取的入口）
references/
  leidian-taxonomy.md         # 雷点/郁闷点分类学（唯一判定口径）
  subagent-prompt.md          # 分卷扫描/逐人物汇总/JSON 模板
  pitfalls.md                 # 三本书实跑沉淀的历史教训
scripts/
  render_characters_md.py     # JSON → 人物卡 Markdown（无行号版）
  render_characters_html.py   # JSON → 可视化 HTML（备用）
  merge_sections.py           # 章节合并 + 目录锚点
```

## 安装（WorkBuddy / Claude Code 类 Agent）

复制到用户级 skill 目录即可：

```bash
git clone https://github.com/guohuiyuan/novel-scan.git ~/.workbuddy/skills/novel-scan
```

## 声明

- 产出的扫书报告对外传播时必须保留「AI 辅助生成」标注
- 雷点/郁闷点判定标准已内置于 `references/leidian-taxonomy.md`

## License

GNU Affero General Public License v3.0 (AGPL-3.0)
