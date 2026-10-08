# 给 AI / 开发者的说明

这是一个本地运行的“行测修仙传 / 行测 RPG”训练网页（Python 标准库后端 + 原生 JS 前端），配合用户的 Obsidian 行测库使用。
默认东方修仙风格，可切换西方玄幻；两种风格共用一套规则。

**开始改代码前先读 [DESIGN.md](DESIGN.md)**（背景、架构、数据结构、游戏规则都在里面）。

## 快速定位

| 想改的东西 | 去哪里 |
|---|---|
| 经验值、等级曲线、分批、复查间隔等数值 | 不用改代码：用户的 `训练/规则.md`；默认值在 `defaults/规则.md` + `rpg/config.py` 的 `DEFAULT_RULES`（两处同步） |
| 游戏规则逻辑（修为、境界、打卡、天道进度、每日功课） | `rpg/engine.py` |
| 训练流程（默写 / 费曼 / 错题 / 渡劫 / 炼丹…的对话步骤） | `rpg/trainer.py` |
| 发给 AI 的提示词、AI 返回的 JSON 字段、世界观设定 | `rpg/prompts.py`（字段名被 trainer.py 读取，改了要一起改） |
| AI 导师什么时候说话、说话依据的学员现状 | `rpg/tutor.py`、`engine.tutor_context()` |
| 风格说法（修仙 / 玄幻的名词、境界名、灵根名、丹药名、世界观） | `rpg/themes.py`（前端通过 dashboard.theme.terms 取；对照表见 DESIGN.md 第 4 节） |
| 境界、渡劫、灵根、丹药、闭关、顿悟、走火入魔、道心、周常、储物袋 | `rpg/engine.py`（文件顶部有总览） |
| 接口 | `rpg/api.py`（顶部有接口清单） |
| 页面、样式 | `web/app.js`、`web/style.css` |
| 🔮 天机简报（时政 PDF 导入、研读 / 消化 / 精卷） | 解析与进度 `rpg/tianji.py`（版式规则在文件顶部），页面 `web/tianji.js`；内容 `训练/天机简报/`，进度 `state["tianji"]` |
| 🖼 修炼战报（海报）、◎ 专注模式 | 数字 `rpg/poster.py`，画图 `web/poster.js`（canvas）；专注 `web/focus.js`（纯前端，`html.focus` 藏顶栏等） |
| 读模考复盘 / skill | `rpg/vault.py`（只读） |
| 听道（网课时间）：计入每日功行 | `engine.add_lecture / lecture_minutes / study_minutes`（`minutes()` = 修炼 + 听道）；首页卡片 `web/app.js lectureCard` |
| 背景 / 语录 / BGM | 后端 `rpg/appearance.py`（存档 state["appearance"]）；前端 `web/ambience.js`（自带背景是 SVG 现画；BGM 只播放 训练/外观/音乐/ 里的文件） |
| 真题导入（模考复盘 / txt → 题库，待修、补答案、AI 补知识点） | `rpg/importer.py`；题库读取与试炼塔在 `rpg/question_bank.py` |
| 默认人设、台词 | `defaults/角色设定.md`、`defaults/台词库.md`、`defaults/台词库·玄幻.md`（首次运行时复制给用户；改结构要升“配置版本”，见 DESIGN.md） |

## 必须遵守

1. 只用 Python 标准库，兼容 Python 3.8；前端不引入构建工具和外部 CDN（离线也要能用）。
2. 只写库里的 `训练/` 文件夹；skill 和复盘文件只读。
3. 经验和等级只由程序计算，AI 只做判断。
4. 用户可调的数值放 `规则.md`，不要写死在代码里。
5. 中文注释，风格和现有代码一致；新增模块在文件顶部写清楚“做什么、数据格式、谁调用它”。
6. 改完运行 `python -m unittest discover -s tests -v`；改了规则或数据结构，同步更新 DESIGN.md。
