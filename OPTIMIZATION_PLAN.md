# 项目深化优化方案（v2 路线图）

> 文档版本：v2.0 ｜ 重写日期：2026-09-16 ｜ 适用代码库：v1.2.0
> 定位：面向**后续优化工作**的活文档（living roadmap）。每完成一项，在对应条目打 ✅ 并在文末「执行记录」登记；发现新问题随时追加到相应维度。
> 使用方式：开工前从第 0 章选定本次冲刺范围 → 按「执行机制」验收 → 更新本文件与相关手册。

## 0. 现状基线（v1.2.0）

已完成并验证（100 个测试通过）：沙箱双后端（subprocess/Docker）与逃逸防护、XSS 全链路修复、权限体系、判分正确性与防刷、考试计时/原子提交、证书 PDF、真实 Jupyter 内核会话、多模型 AI（Claude/DeepSeek/proxy）、AI 工具调用（notebook 素材）、内容生成与修改的 Skill 模式（四硬规则 + 沙箱验证 + 干跑默认）、教师工作台（课程/章节/单元/练习/考试管理 + 章节级 AI 填充）、Celery 接线（eager 默认）、视频校验与渲染、成本跟踪与日限额、工业级文档（用户/程序员手册）。

**已知技术债总量**：见第 5 章登记表（共 30+ 项，按 P0-P3 分级）。

---

## 1. 安全与合规

### 1.1 认证加固（P1）✅
- 登录失败计数（按用户名+IP，5 次/15 分钟锁定，cache 实现）已落地并测试；密码找回维持管理员 `changepassword` 流程，用户手册 §2.3 已注明（邮件验证成本高，v2 不做）。

### 1.2 接口滥用防护（P1）✅
- `apps/core/rate_limit.py` 装饰器（cache 滑动窗口）已应用于：练习提交（10 次/分钟）、内核执行（60 次/5 分钟）、AI 生成类端点（20 次/小时：习题草稿/习题修改/考题修改/单元生成/章节规划/整卷生成）；配套 429 测试。

### 1.3 密钥与配置（P1）✅
- ① 密钥轮换流程已写入部署手册 §9.3；② 开发机 `.env` 已生成真实随机 `SECRET_KEY`；③ 环境变量优先级（系统 > .env > 默认）与 `AI_ACTIVE_MODEL` 应用专属覆盖已写入部署手册 §5。

### 1.4 依赖与基线更新（P2）✅
- CI 含 `pip-audit` 步骤（非阻断，告警人工跟进）；季度升级流程（升级 → 全量测试 → audit → 连通性探针 → CHANGELOG）已写入部署手册 §9.4。

---

## 2. 可靠性

### 2.1 AI 生成稳定性监控（P1）✅
- `apps/ai_agents/admin.py` 注册 `AIGenerationHistory`（只读）并附**近 24 小时看板**（调用数/失败数/失败率/成本，失败率 >10% 红色告警徽标）；`test_ai_agents` 命令为连通性探针。

### 2.2 模型回退链（P1）✅
- `AI_FALLBACK_MODELS` 回退链 + 推理模型兼容层已落地（见执行记录「模型路由修复」与「AI 架构重写」）；`.env` 默认 flash→chat。

### 2.3 长任务异步化（P2）✅
- ① 单元生成/章节批量生成/课程大纲设计走 Celery + 前端轮询（eager 兼容）；② 视频渲染任务化（仅超时重试一次）；③ 三个 AI 生成任务 `max_retries=2` + 指数退避（5s→10s，封顶 120s）；**eager 模式 Retry 穿透问题已修复**（`is_eager` 守卫，见学习/考试 tasks.py）。

### 2.4 考试交卷前端收尾（P1）✅
- `submitExam()` 先 flush 防抖保存再交卷（T1 已落地并测试）。

### 2.5 成绩一致性（P2）✅
- 简答评阅（admin save 钩子 + 教师评阅端点）后自动重算总分；`show_results_immediately` 在结果页生效（不展示则不渲染解析）；未 AI 判分的简答统一置 `needs_review`。

---

## 3. 性能与容量

### 3.1 剩余 N+1（P2，审计遗留）✅
- 视图传 `hints_count`/`total_points`/`question_count` 上下文变量（`get_total_points` 为单次聚合），模板无方法调用。

### 3.2 学习进度时间统计（P3）✅
- `lesson_heartbeat` 端点（每拍 0-300s 钳制，`F()` 原子累加）+ 前端 30 秒心跳 + 学习页时长显示。

### 3.3 内核会话治理加固（P1）✅
- 每用户最多 2 个内核（`JUPYTER_MAX_KERNELS_PER_USER`，超出复用/淘汰最旧），全局 LRU 保留，带配额测试。

### 3.4 静态资源与缓存（P3）✅
- 课程列表页内容版本化缓存（`bump_content_version` 变更点失效，搜索/筛选绕过缓存）；WhiteNoise 指纹化已就绪。

---

## 4. 功能完整度

### 4.1 学习课堂
- [x] **单元格版本恢复 UI**（P2）：API 已就绪（`restore_cell_version` + 快照），编辑器加「历史」下拉 + 恢复按钮。
- [x] **导出 PDF**（P3）：`export_notebook` 已有 json/md，补 PDF（reportlab 复用证书模式）与 `.ipynb` 格式（解析器 `to_json` 反写 ipynb 结构）。
- [x] **孤儿 `Video` 模型接线**（P3）：视频单元格/生成命令已存 `Video` 记录，但课程单元的视频展示走 Cell.data——统一视频元数据入口或明确废弃该模型。
- [x] **`Cell.execute()` 旧方法退役**（P3）：学习执行已走内核，该方法无调用方——删除或改为内核语义，避免新代码误用。

### 4.2 训练课堂
- [x] **练习编辑/删除界面**（P2）：编辑表单（预填+提示重建）与删除（有提交历史需 force 确认）✅
- [x] **AI 修改按钮**（P1）：习题详情页「AI 修改」预览/应用流程（端点 + 前端 + 测试 ✅）。

### 4.3 考试课堂
- [x] **考试管理页题目级 AI 修改**（P1）：考试管理页题目列表 + 逐题「AI 修改」预览/应用（含沙箱验证）✅。
- [x] **`validate_exam` 命令**（P1）：发布前整卷代码题沙箱验证 ✅。
- [x] **简答题教师评阅界面**（P2）：现仅 admin 可改；教师考试管理页加待评阅列表 + 打分表单（复用 2.5 重算）。
- [x] **整卷 AI 生成改为两阶段**（P2）：`generate_exam` 现单次 JSON 生成整卷，推理模型下不稳定——改为「题型分布请求 → 逐题短请求」，复用 6.8 两阶段模式。
- [x] **考试网页创建与 AI 生成入口**（P1，用户反馈）：`exam_create` 表单页（标题/时长/通过线/尝试次数/即时结果/乱序）+ 管理页空卷「AI 生成题目」按钮（ExamSkill 异步任务 + 轮询 + 限流）；落库逻辑抽出 `exam_assembly.save_generated_questions` 供命令与任务共用 ✅。

### 4.4 聊天助手
- [x] **流式响应**（P3）：SSE 逐字输出，前端增量渲染（打字体验）；当前整段返回 max_tokens=2000。
- [x] **消息长度限制**（P2）：服务端校验输入 ≤4000 字符；超长历史窗口截断/摘要（现只取最近 20 条）。
- [x] **推荐资源结构化**（P3）：现用文件名子串匹配——改为让模型在回答中输出结构化资源引用（工具循环已具备，加一个 `suggest_resource` 工具或输出约定）。

### 4.5 AI 基础设施
- [x] **PromptTemplate / ContentValidation 模型落地**（P2）：CLAUDE.md 承诺但未实现——至少把各 Agent 的契约提示词收敛到 `AIGenerationHistory.prompt` 可检索的模板表（内容生成已内置沙箱验证，ContentValidation 可先不做，明确从 CLAUDE.md 移除或标记延后）。
- [x] **AIGenerationHistory admin 视图**（P1，同 2.1）。
- [x] **生成任务并发闸**（P3）：防多教师同时触发大量生成——Celery 队列限流（`task_rate_limit`）。

### 4.6 视频
- [x] **缩略图生成**（P3）：FFmpeg 首帧抽帧 + `Video.thumbnail`。
- [x] **渲染队列异步化**（P2，同 2.3）。
- [x] **清理命令**（P3）：`cleanup_videos --older-than N`（CLAUDE.md 已列）——清理孤儿渲染文件与失败任务。

### 4.7 账号体系
- [x] **登录限流**（P1，同 1.1）。
- [x] **教师仪表盘增强**（P3）：考试通过率、练习提交趋势等简单统计卡片。

---

## 5. 技术债登记表

> 格式：编号 ｜ 位置 ｜ 债务 ｜ 优先级 ｜ 建议处理

| # | 位置 | 债务 | 优先级 | 处理 |
|---|------|------|--------|------|
| T1 | `examination/views.py::submit_exam` 前端 | 交卷前未 flush 防抖保存（最后 2 秒答案丢失） | P1 | ✅ 2.4 |
| T2 | `apps/ai_agents/admin.py`（不存在） | AI 调用记录无管理界面 | P1 | ✅ 2.1（含 24h 失败率看板） |
| T3 | `jupyter_kernel.py` 注册表 | 无按用户内核配额，LRU 可被单用户挤占 | P1 | ✅ 3.3 |
| T4 | `accounts/views.py::login_view` | 登录无限流（暴力破解面） | P1 | ✅ 1.1 |
| T5 | 各 AI 生成端点 | 生成类请求无限流 | P1 | ✅ 1.2（提交 10/分钟、AI 20/小时、内核 60/5 分钟） |
| T6 | `examination` admin 评阅 | 简答评阅后总分不重算 | P2 | ✅ 2.5 |
| T7 | `ExamResultsView` | `show_results_immediately` 未生效 | P2 | ✅ 2.5 |
| T8 | `exam_interface.html` | 交卷丢最后 2 秒输入 | P1 | ✅ T1 同源 |
| T9 | `ExerciseDetailView` 模板 | `hints.count` 等剩余 N+1 | P2 | ✅ 3.1 |
| T10 | `LessonProgress.time_spent_seconds` | 从未写入，界面恒 0 | P3 | ✅ 3.2（心跳端点 + F() 累加） |
| T11 | `CellVersion` | 版本快照无恢复 UI（API 已就绪） | P2 | ✅ 4.1 |
| T12 | `learning/models.py::Video` | 孤儿模型（视频走 Cell.data） | P3 | ✅ 4.1 |
| T13 | `learning/models.py::Cell.execute()` | 无调用方的旧执行路径（共享单元格写入语义） | P3 | ✅ 4.1 |
| T14 | 训练无编辑/删除界面 | 练习只能创建/AI 改 | P2 | ✅ 4.2 |
| T15 | `generate_exam` | 整卷单次 JSON 生成（推理模型不稳） | P2 | ✅ 4.3（两阶段 + 网页入口） |
| T16 | 简答题评阅 | 教师无评阅界面（仅 admin） | P2 | ✅ 4.3 |
| T17 | `chat/ai_service.py` | 无流式、max_tokens 固定 2000、输入无长度限制 | P2/P3 | ✅ 4.4 |
| T18 | `_extract_suggestions` | 文件名子串匹配推荐 | P3 | ✅ 4.4 |
| T19 | CLAUDE.md 承诺模型 | `AIGenerationRequest`/`PromptTemplate`/`ContentValidation`/`ManimScript`/`VideoRenderJob` 不存在 | P2 | ✅ 4.5（从文档删除承诺，harness 审计 + 沙箱验证替代） |
| T20 | `ai_config` | 无模型回退链 | P1 | ✅ 2.2 |
| T21 | 视频 | 无缩略图、无清理命令、渲染未异步 | P2/P3 | ✅ 4.6 |
| T22 | `export_notebook` | 无 PDF/ipynb 格式（CLAUDE.md 承诺） | P3 | ✅ 4.1 |
| T23 | UI 中英混杂 | 无 i18n 规划 | P3 | ✅ 决策归档：中文为主、LANGUAGE_CODE=zh-hans，完整 i18n 不启动（单语言教学平台成本收益不成比例） |
| T24 | `config/urls.py` 开发静态服务 | `static()` 依赖 settings 内部常量 | P3 | ✅ 循环服务全部 STATICFILES_DIRS |
| T25 | 无 CI 流水线 | 测试/漏洞扫描靠手动 | P2 | ✅ 6.6 |
| T26 | 无覆盖率基线 | 100 测试但无 coverage 配置与阈值 | P2 | ✅ 6.5（核心模块 83%，CI ≥80% 门禁） |
| T27 | 无 lint 配置 | flake8/ruff 未配置（README 提到 flake8 但未装） | P2 | ✅ 6.5（ruff lint + pre-commit；format 有意不启用） |
| T28 | `.env` SECRET_KEY 占位符 | 开发环境弱密钥 | P1 | ✅ 1.3 |
| T29 | 部署手册缺备份/恢复 | 无数据备份方案 | P2 | ✅ 6.2 |
| T30 | 无全栈 compose | 仅沙箱/内核两个镜像，无 app+db+redis+celery 编排 | P2 | ✅ 6.1 |
| T31 | AI 模型选择受系统环境变量干扰 | 此前 `AI_MODEL` 系统变量覆盖 `.env` 造成困惑 | P1 | ✅ 1.3（`AI_ACTIVE_MODEL` + 优先级文档） |
| T32 | 历史 git 提交中的 `ghp_` token | ClassLib 教学材料曾嵌入两个真实 GitHub PAT（已从 git 历史清洗，但 token 本身未撤销，视为已泄露）；本地备份 bundle（`TeachingSpace-history-backup.bundle`）仍含旧历史 | P1 | ⏳ **项目收尾处理**：① github.com/settings/tokens 撤销两个 token；② 确认推送无误后删除备份 bundle |

---

## 6. 工程质量与部署

### 6.1 Docker Compose 全栈（P2）✅
- `docker-compose.yml`（web + celery worker + redis + postgres，healthcheck + 持久卷），`scripts/deploy.sh` 幂等部署脚本；README/部署手册 §9.1 有启动步骤。

### 6.2 备份与恢复（P2）✅
- PostgreSQL 定时 dump + `media/` 同步方案与恢复演练步骤写入部署手册 §9.2，`scripts/backup.sh` 脚本化。

### 6.3 配置即代码（P3）✅
- `.env.example` 与部署手册保持同步；生产部署脚本入 `scripts/`。

### 6.4 可观测性（P2）✅
- Sentry 可选接线；请求耗时中间件（`apps/core/middleware.py`，慢请求日志采样）；AI 失败率看板（2.1 admin 24h 统计）。

### 6.5 代码质量门禁（P2）✅
- `ruff` lint（pyproject.toml）+ `pre-commit` 配置（.pre-commit-config.yaml）+ pytest-cov 核心模块阈值 ≥80%（当前 83%）；`ruff format` 经评估不启用（与既有风格冲突，改动 98 文件收益为负——决策记录在配置注释与开发规范第 8 条）。

### 6.6 CI 流水线（P2）✅
- GitHub Actions（.github/workflows/ci.yml）：install → ruff check → pytest（not slow）+ 核心模块覆盖率门禁（≥80%）→ pip-audit；slow 任务（Manim 真渲染）单独 job。

---

## 7. 执行机制（后续优化工作如何做）

1. **冲刺选择**：从 P1 开始（T1-T5、T20、T28、T31），每轮 3-5 个相关条目（如"考试可靠性冲刺"= T1/T6/T7/T8）。
2. **验收标准（每个条目）**：
   - 修复类：附回归测试（能写测试的场景必须写）；涉及模板 JS 的改动做「渲染脚本 → node --check」验证；
   - 功能类：测试 + 用户/程序员手册对应章节更新 + CHANGELOG 记录；
   - 安全类：参考既有模式（沙箱逃逸测试、权限 403 测试）。
3. **提交纪律**：语义化 commit（fix/feat/security/docs 分开），引用本表编号（如 `fix(T4): 登录限流`）。
4. **文档同步**：完成冲刺后更新本文件对应条目为 ✅ + 文末「执行记录」一行；改动公开行为同步 `docs/USER_MANUAL.md`、`docs/DEVELOPER_MANUAL.md`、`CLAUDE.md`。
5. **待办未完成项**：本轮已写完待验证/提交的（4.2 AI 修改按钮、4.3 考试题目 AI 修改 + `validate_exam`）优先补测提交。

---

## 8. 历史里程碑（自 v1.0 审计以来）

| 里程碑 | 内容摘要 |
|--------|---------|
| 安全止血（P0） | 沙箱重写（subprocess/Docker）、XSS 修复、越权/开放重定向、权限体系、判分三 bug、单元格重排 |
| 核心修复（P1） | 考试计时/原子提交、防刷积分、生产配置、Agent 基建、N+1 治理 |
| 平台能力（P2/P3） | 真实 Jupyter 内核、多模型 AI、AI 工具调用、成本控制、证书、视频管线、Celery、教师工作台、内容生成 Skill 模式 |
| 稳定性（深夜批） | 推理模型兼容层、两阶段生成、章节级 AI 填充、AI 修改能力（网页 + 命令） |

---

## 9. 执行记录

> 格式：日期 ｜ 冲刺主题 ｜ 完成条目 ｜ 测试数

- 2026-09-17 ｜ 继续优化 ⑨·工业级收尾 ｜ **考试网页流**（新建考试表单 + 管理页空卷「AI 生成题目」异步轮询，落库逻辑抽 `exam_assembly` 供命令复用）；**全表债务清零**（T1-T31 全部 ✅，1.1-1.4/2.1-2.5/3.1-3.4/6.1-6.6 收口）；**测试基建**（核心模块覆盖率 68%→83%，CI ≥80% 门禁、pre-commit、ruff 决策归档）；**修复**：Celery eager Retry 穿透视图、心跳返回过期值、start_exam 500、save_answer 吞 404、教师打不开学生提交（相似度徽标死代码）、考试草稿预览 404、作文未判分状态；限流数值对齐计划；AI admin 24h 失败率看板；**安全事件处置**：ClassLib 教学材料历史提交含两个 `ghp_` token → git filter-repo 全史清洗 + 首次全量推送 GitHub（建议撤销原 token） ｜ 256 |
- 2026-09-17 ｜ 继续优化 ⑧ ｜ **自动组卷命令**（按题型/难度配比从源考试抽题克隆、代码题沙箱验证）；**提交相似度提示**（教师视角 difflib 雷同徽标 ≥70%）；**学生学习日历热力图**（近 90 天活动色块） ｜ 160
- 2026-09-17 ｜ 继续优化 ⑦ ｜ **题库 JSON 导入导出**（跨考试批量迁移、代码题导入前沙箱验证、往返闭环测试）；**聊天会话自动摘要**（超 20 条自动压缩旧轮次注入系统提示、按会话状态缓存） ｜ 159
- 2026-09-17 ｜ 继续优化 ⑥ ｜ **课程创建 AI 大纲异步化**（创建即返回、任务后台设计、大纲页 3 秒轮询刷新）；**考试成绩单 CSV 导出**（评阅台逐题成绩表）；**学生积分排行榜**（前三奖牌 + 我的高亮）；**课程单元批量发布**（一键发布全部） ｜ 155
- 2026-09-17 ｜ 继续优化 ⑤ ｜ **页面缓存**（内容版本化 course 列表缓存 + 变更点失效）；**考试提交全流程集成测试**（真实沙箱判分链路）；**学员名单 CSV 导出**（Excel BOM）；代码格「示例输出」标注；学习页「运行全部」按钮 ｜ 150
- 2026-09-17 ｜ 继续优化 ④ ｜ **异步单元生成**（Celery 任务 + 缓存状态 + 前端 3 秒轮询，eager 兼容）；**考试题目手动编辑界面**（四题型表单、代码题沙箱验证、分值变更重算）；课程详情页教师「预览」入口；README 刷新至当前状态；ruff F841 清零 ｜ 144
- 2026-09-17 ｜ 继续优化 ③ ｜ 创建练习表单 **AI 生成草稿**面板（ExerciseSkill 填表不落库、验证状态展示）；聊天工具循环 ThinkingBlock 兼容（`.id` 崩溃修复） ｜ 138

- 2026-09-17 ｜ 模型路由修复 ｜ 新增 `AI_ACTIVE_MODEL`（应用专属最高优先级模型，免疫宿主 harness 环境变量污染）；planner 角色移除硬编码 reasoner 默认（未配置时随 provider）；`.env` 设 flash 为全角色模型 + flash→chat 回退链；相关 override 测试补 `AI_ACTIVE_MODEL=''` ｜ 117
- 2026-09-17 ｜ 修复：logger 未定义与成本统计时区边界 ｜ `learning_agent.py` 引用 logger 未定义（单元生成失败时 NameError 掩盖真实错误）→ 补定义 + 静态守护测试；`daily_cost_exceeded` 用 `now().date()`（UTC 日期）与 `__date` 本地时区查询在午夜附近漏计 → 改 `localdate()`；`.env` 配回退链（deepseek-flash→deepseek-chat） ｜ 115
- 2026-09-16 ｜ AI 落地深化 + P1 安全快赢 ｜ T4 登录限流（5 次/15 分钟锁定）、T3 内核每用户配额（默认 2）、T2 AI 审计 admin（只读）、T1 交卷 flush 防抖保存、T28 开发环境真实随机 SECRET_KEY；课程创建 AI 设计切到 CourseSkill（planner 角色）；Agent 角色标注（大纲/章节规划/结构请求→planner，作文评分→grader） ｜ 114
- 2026-09-16 ｜ **AI 架构重写（DeepSeek Harness 模式）** ｜ 新增 HarnessCore（角色路由 planner/worker/grader + 回退链 + 兼容层 + 审计）、Skills 层（CourseSkill/ExerciseSkill/ExamSkill）、BaseAgent 薄适配、三个生成命令切到 Skills；真实落地验证（ExerciseSkill 一次通过 7/7 沙箱用例） ｜ 111
- 2026-09-16 ｜ AI 修改能力（网页版） ｜ 习题详情「AI 修改」按钮（4.2）、考试管理页题目级 AI 修改（4.3）、`validate_exam` 命令（4.3）；抽公共模块 `apps/examination/question_ai.py` ｜ 107
