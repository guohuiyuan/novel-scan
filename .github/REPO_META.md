# 仓库元信息（GitHub description / topics）

GitHub 的仓库简介与 topic 存在服务端，改完不会体现在 git 里；这份文件是**唯一事实源**，
改口径先改这里，再用下面的命令推上去。

## Description

> 长篇网文扫书 Agent Skill：一本 .txt 进去，出来一套能直接发的扫书稿（标题党大标题 + 封面 + 8 维评分 + 简介 + 男主卡 + 女主逐条含外貌与名场面）+ 人物卡 + 结构化 JSON + 按外貌反推的人物图。子代理直读原文，引文逐字可核验，成品无行号。

字数 130，未超 GitHub 350 上限。对外一句话版：**把一本网文 txt 扫成可直接发布的扫书稿。**

## Topics

```
ai-agent  agent-skill  llm  claude-code  workbuddy  web-novel  chinese-novel
book-review  character-extraction  text-analysis  python  markdown
prompt-engineering  image-generation  literature
```

共 15 个。取舍口径：前 5 个定位"这是什么形态的东西"（Agent 技能、跑在哪），中间 5 个定位"干什么活"
（网文、书评、人物抽取、文本分析），后 5 个定位"用什么做的"（Python 脚本、Markdown 交付、提示词工程、
配图）。不要加 `awesome`、`novel`（太泛，与 `web-novel` 重复）、`scraping`（本项目不抓站）这类噪音 topic。

## 应用命令

需要本机装了 GitHub CLI 且已 `gh auth login`：

```bash
gh repo edit guohuiyuan/novel-scan \
  --description "长篇网文扫书 Agent Skill：一本 .txt 进去，出来一套能直接发的扫书稿（标题党大标题 + 封面 + 8 维评分 + 简介 + 男主卡 + 女主逐条含外貌与名场面）+ 人物卡 + 结构化 JSON + 按外貌反推的人物图。子代理直读原文，引文逐字可核验，成品无行号。" \
  --add-topic ai-agent --add-topic agent-skill --add-topic llm \
  --add-topic claude-code --add-topic workbuddy --add-topic web-novel \
  --add-topic chinese-novel --add-topic book-review --add-topic character-extraction \
  --add-topic text-analysis --add-topic python --add-topic markdown \
  --add-topic prompt-engineering --add-topic image-generation --add-topic literature
```

没有 gh 时用 API（`repo` scope 的 PAT）：

```bash
curl -sS -X PATCH https://api.github.com/repos/guohuiyuan/novel-scan \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -d '{"description":"…同上…","topics":["ai-agent","agent-skill","llm","claude-code","workbuddy","web-novel","chinese-novel","book-review","character-extraction","text-analysis","python","markdown","prompt-engineering","image-generation","literature"]}'
```

> 注意：`PATCH /repos` 的 `topics` 字段需要 `application/vnd.github.mercy-preview+json` 时代的老客户端才认；
> 现在直接放进 PATCH body 即可，但**会整体替换**原有 topics，不是追加——所以每次都要带全量清单。

## 校验

```bash
gh repo view guohuiyuan/novel-scan --json description,repositoryTopics
```
