# 项目深化优化方案（v2 路线图）

> 文档版本：v2.0 ｜ 重写日期：2026-09-16 ｜ 适用代码库：v1.2.0
> 定位：面向**后续优化工作**的活文档（living roadmap）。每完成一项，在对应条目打 ✅ 并在文末「执行记录」登记；发现新问题随时追加到相应维度。
> 使用方式：开工前从第 0 章选定本次冲刺范围 → 按「执行机制」验收 → 更新本文件与相关手册。

## 0. 现状基线（v1.2.0）

已完成并验证（100 个测试通过）：沙箱双后端（subprocess/Docker）与逃逸防护、XSS 全链路修复、权限体系、判分正确性与防刷、考试计时/原子提交、证书 PDF、真实 Jupyter 内核会话、多模型 AI（Claude/DeepSeek/proxy）、AI 工具调用（notebook 素材）、内容生成与修改的 Skill 模式（四硬规则 + 沙箱验证 + 干跑默认）、教师工作台（课程/章节/单元/练习/考试管理 + 章节级 AI 填充）、Celery 接线（eager 默认）、视频校验与渲染、成本跟踪与日限额、工业级文档（用户/程序员手册）。

**已知技术债总量**：见第 5 章登记表（共 30+ 项，按 P0-P3 分级）。

---

## 1. 安全与合规

### 1.1 认证加固（P1）
- **现状**：登录无速率限制（可暴力破解）；无邮件验证；无自助找回密码（仅管理员 `changepassword`）。
- **方案**：登录失败计数（按用户名+IP，5 次/15 分钟锁定，用 cache 实现，无需模型）；密码找回留管理员流程并在手册注明（v2 暂不做邮件验证，邮件配置成本高）。

### 1.2 接口滥用防护（P1）
- **现状**：练习提交/内核执行/单元生成**无请求频率限制**——沙箱与内核都是昂贵资源，单个用户可刷爆（生成类还会刷爆 AI 日额度）。
- **方案**：中间件或装饰器级限流（cache 计数）：提交 ≤10 次/分钟/人；AI 生成类端点 ≤20 次/小时/人；内核会话每用户上限（现全局 LRU 20 个会被单用户挤占他人，见 3.3）。

### 1.3 密钥与配置（P1）
- **现状**：`.env` 有真实密钥（已 gitignore）；`deepseek_Api` 存于系统环境变量；`SECRET_KEY` 为占位符（开发可用，生产已强制拦截）。
- **方案**：① 密钥轮换流程写入部署手册；② 开发机 `.env` 占位符 → 生成真实随机值；③ 排查系统环境变量与 `.env` 的优先级冲突（此前 `AI_MODEL` 系统变量曾覆盖 `.env` 造成困惑——在部署手册补「环境变量优先级」小节）。

### 1.4 依赖与基线更新（P2）
- **现状**：requirements.txt 已按 Python 3.13 对齐（2026-09），但无定期更新机制；无 `pip-audit` 类漏洞扫描。
- **方案**：季度依赖升级 + 每次升级跑全量测试；GitHub Actions 加 `pip-audit` 步骤（见 5.6 CI）。

---

## 2. 可靠性

### 2.1 AI 生成稳定性监控（P1）
- **现状**：`AIGenerationHistory` 记录了每次调用（成功/失败/耗时/成本），但**没有可视化**——ai_agents 未注册 admin，失败原因只能查库。
- **方案**：`apps/ai_agents/admin.py` 注册 `AIGenerationHistory`（只读：agent/模型/成败/成本/时间），加失败率展示；`test_ai_agents` 已是连通性探针，可再加 cron 定期探测告警。

### 2.2 模型回退链（P1）
- **现状**：单模型无回退——`deepseek-flash` 偶发思考循环（已内置去 temperature 重试），仍失败则整次生成失败。
- **方案**：`ai_config` 支持回退链配置（如 `AI_FALLBACK_MODELS=deepseek-flash,deepseek-chat`）：主模型失败（空文本/APIError 重试后）→ 依次切换回退模型重试一次。生成类 Agent 与聊天共用。

### 2.3 长任务异步化（P2）
- **现状**：课程单元内容生成（两阶段约 30-60 秒）同步阻塞 HTTP；视频渲染同步阻塞命令；仅训练判分接了 Celery。
- **方案**：① 单元生成/章节批量生成走 Celery 任务 + 前端轮询状态（复用 eager 模式保证开发行为不变）；② 视频渲染任务化；③ 任务加 `max_retries` 与指数退避。

### 2.4 考试交卷前端收尾（P1）
- **现状**：答题页 2 秒防抖自动保存，**交卷按钮未 flush 未完成的保存**——最后 ~2 秒的输入可能丢失（审计遗留项）。
- **方案**：`submitExam()` 先 `clearTimeout(saveTimers)` 并立即 await 一次 save-answer，再调交卷。

### 2.5 成绩一致性（P2）
- **现状**：后台人工评阅简答题后 `StudentExam.score` **不自动重算**；`show_results_immediately` 字段未在结果页生效（通过的学生永远立即看到结果）。
- **方案**：评阅保存信号或 admin save 钩子里重算 `calculate_score()`；结果页按 `show_results_immediately` 决定是否展示解析。

---

## 3. 性能与容量

### 3.1 剩余 N+1（P2，审计遗留）
- `ExerciseDetailView` 模板 `hints.count`；`exam_interface` 重复调用 `get_total_points()`；`exam_detail` 的 `questions.count`。
- **方案**：视图传 `hints_count`/`total_points` 上下文变量，模板去掉方法调用。

### 3.2 学习进度时间统计（P3）
- **现状**：`LessonProgress.time_spent_seconds` 字段**从未被写入**（界面上显示恒 0）。
- **方案**：前端心跳（每 30 秒或执行单元格时上报增量）或 `last_accessed` 差值估算；写入用 `F()` 原子累加。

### 3.3 内核会话治理加固（P1）
- **现状**：注册表全局 20 个 LRU——**单用户大量并发可挤占他人会话**；无按用户配额。
- **方案**：每用户最多 2 个内核（超出复用/拒绝提示），全局上限保留；空闲回收已有。

### 3.4 静态资源与缓存（P3）
- **现状**：前端库全 CDN；无 HTTP 缓存策略；无 Redis 页面缓存（生产 CACHES 已配 Redis 但只用于 AI 缓存）。
- **方案**：课程列表/详情等读多写少页面加缓存键版本化（课程发布时失效）；`staticfiles` 指纹已由 WhiteNoise 处理。

---

## 4. 功能完整度

### 4.1 学习课堂
- [ ] **单元格版本恢复 UI**（P2）：API 已就绪（`restore_cell_version` + 快照），编辑器加「历史」下拉 + 恢复按钮。
- [ ] **导出 PDF**（P3）：`export_notebook` 已有 json/md，补 PDF（reportlab 复用证书模式）与 `.ipynb` 格式（解析器 `to_json` 反写 ipynb 结构）。
- [ ] **孤儿 `Video` 模型接线**（P3）：视频单元格/生成命令已存 `Video` 记录，但课程单元的视频展示走 Cell.data——统一视频元数据入口或明确废弃该模型。
- [ ] **`Cell.execute()` 旧方法退役**（P3）：学习执行已走内核，该方法无调用方——删除或改为内核语义，避免新代码误用。

### 4.2 训练课堂
- [x] **练习编辑/删除界面**（P2）：现只有创建 + AI 修改，缺常规编辑表单（复用 exercise_form 加编辑模式）与删除（含提交历史保护策略）。*（注：编辑/删除仍待做，AI 修改已完成）*
- [x] **AI 修改按钮**（P1）：习题详情页「AI 修改」预览/应用流程（端点 + 前端 + 测试 ✅）。

### 4.3 考试课堂
- [x] **考试管理页题目级 AI 修改**（P1）：考试管理页题目列表 + 逐题「AI 修改」预览/应用（含沙箱验证）✅。
- [x] **`validate_exam` 命令**（P1）：发布前整卷代码题沙箱验证 ✅。
- [ ] **简答题教师评阅界面**（P2）：现仅 admin 可改；教师考试管理页加待评阅列表 + 打分表单（复用 2.5 重算）。
- [ ] **整卷 AI 生成改为两阶段**（P2）：`generate_exam` 现单次 JSON 生成整卷，推理模型下不稳定——改为「题型分布请求 → 逐题短请求」，复用 6.8 两阶段模式。

### 4.4 聊天助手
- [ ] **流式响应**（P3）：SSE 逐字输出，前端增量渲染（打字体验）；当前整段返回 max_tokens=2000。
- [ ] **消息长度限制**（P2）：服务端校验输入 ≤4000 字符；超长历史窗口截断/摘要（现只取最近 20 条）。
- [ ] **推荐资源结构化**（P3）：现用文件名子串匹配——改为让模型在回答中输出结构化资源引用（工具循环已具备，加一个 `suggest_resource` 工具或输出约定）。

### 4.5 AI 基础设施
- [ ] **PromptTemplate / ContentValidation 模型落地**（P2）：CLAUDE.md 承诺但未实现——至少把各 Agent 的契约提示词收敛到 `AIGenerationHistory.prompt` 可检索的模板表（内容生成已内置沙箱验证，ContentValidation 可先不做，明确从 CLAUDE.md 移除或标记延后）。
- [ ] **AIGenerationHistory admin 视图**（P1，同 2.1）。
- [ ] **生成任务并发闸**（P3）：防多教师同时触发大量生成——Celery 队列限流（`task_rate_limit`）。

### 4.6 视频
- [ ] **缩略图生成**（P3）：FFmpeg 首帧抽帧 + `Video.thumbnail`。
- [ ] **渲染队列异步化**（P2，同 2.3）。
- [ ] **清理命令**（P3）：`cleanup_videos --older-than N`（CLAUDE.md 已列）——清理孤儿渲染文件与失败任务。

### 4.7 账号体系
- [ ] **登录限流**（P1，同 1.1）。
- [ ] **教师仪表盘增强**（P3）：考试通过率、练习提交趋势等简单统计卡片。

---

## 5. 技术债登记表

> 格式：编号 ｜ 位置 ｜ 债务 ｜ 优先级 ｜ 建议处理

| # | 位置 | 债务 | 优先级 | 处理 |
|---|------|------|--------|------|
| T1 | `examination/views.py::submit_exam` 前端 | 交卷前未 flush 防抖保存（最后 2 秒答案丢失） | P1 | 2.4 |
| T2 | `apps/ai_agents/admin.py`（不存在） | AI 调用记录无管理界面 | P1 | 2.1 |
| T3 | `jupyter_kernel.py` 注册表 | 无按用户内核配额，LRU 可被单用户挤占 | P1 | 3.3 |
| T4 | `accounts/views.py::login_view` | 登录无限流（暴力破解面） | P1 | 1.1 |
| T5 | 各 AI 生成端点 | 生成类请求无限流 | P1 | 1.2 |
| T6 | `examination` admin 评阅 | 简答评阅后总分不重算 | P2 | 2.5 |
| T7 | `ExamResultsView` | `show_results_immediately` 未生效 | P2 | 2.5 |
| T8 | `exam_interface.html` | 交卷丢最后 2 秒输入 | P1 | T1 同源 |
| T9 | `ExerciseDetailView` 模板 | `hints.count` 等剩余 N+1 | P2 | 3.1 |
| T10 | `LessonProgress.time_spent_seconds` | 从未写入，界面恒 0 | P3 | 3.2 |
| T11 | `CellVersion` | 版本快照无恢复 UI（API 已就绪） | P2 | 4.1 |
| T12 | `learning/models.py::Video` | 孤儿模型（视频走 Cell.data） | P3 | 4.1 |
| T13 | `learning/models.py::Cell.execute()` | 无调用方的旧执行路径（共享单元格写入语义） | P3 | 4.1 |
| T14 | 训练无编辑/删除界面 | 练习只能创建/AI 改 | P2 | 4.2 |
| T15 | `generate_exam` | 整卷单次 JSON 生成（推理模型不稳） | P2 | 4.3 |
| T16 | 简答题评阅 | 教师无评阅界面（仅 admin） | P2 | 4.3 |
| T17 | `chat/ai_service.py` | 无流式、max_tokens 固定 2000、输入无长度限制 | P2/P3 | 4.4 |
| T18 | `_extract_suggestions` | 文件名子串匹配推荐 | P3 | 4.4 |
| T19 | CLAUDE.md 承诺模型 | `AIGenerationRequest`/`PromptTemplate`/`ContentValidation`/`ManimScript`/`VideoRenderJob` 不存在 | P2 | 4.5（落地或从文档删除承诺） |
| T20 | `ai_config` | 无模型回退链 | P1 | 2.2 |
| T21 | 视频 | 无缩略图、无清理命令、渲染未异步 | P2/P3 | 4.6 |
| T22 | `export_notebook` | 无 PDF/ipynb 格式（CLAUDE.md 承诺） | P3 | 4.1 |
| T23 | UI 中英混杂 | 无 i18n 规划 | P3 | 单独评估 |
| T24 | `config/urls.py` 开发静态服务 | `static()` 依赖 settings 内部常量 | P3 | 微调 |
| T25 | 无 CI 流水线 | 测试/漏洞扫描靠手动 | P2 | 5.6 |
| T26 | 无覆盖率基线 | 100 测试但无 coverage 配置与阈值 | P2 | 5.5 |
| T27 | 无 lint 配置 | flake8/ruff 未配置（README 提到 flake8 但未装） | P2 | 5.5 |
| T28 | `.env` SECRET_KEY 占位符 | 开发环境弱密钥 | P1 | 1.3 |
| T29 | 部署手册缺备份/恢复 | 无数据备份方案 | P2 | 6.2 |
| T30 | 无全栈 compose | 仅沙箱/内核两个镜像，无 app+db+redis+celery 编排 | P2 | 6.1 |
| T31 | AI 模型选择受系统环境变量干扰 | 此前 `AI_MODEL` 系统变量覆盖 `.env` 造成困惑 | P1 | 1.3（文档化优先级规则） |

---

## 6. 工程质量与部署

### 6.1 Docker Compose 全栈（P2）
- 现状：只有 `docker/sandbox`、`docker/kernel` 两个执行镜像。
- 方案：`docker-compose.yml`（web + celery worker + redis + postgres + 可选内核镜像），开发与生产两套 profile；README/部署手册补启动步骤。

### 6.2 备份与恢复（P2）
- 方案：PostgreSQL 定时 dump + `media/`（证书/视频）同步；恢复演练步骤写入部署手册。

### 6.3 配置即代码（P3）
- 方案：`.env.example` 与部署手册保持同步（已建立习惯）；生产部署脚本（幂等）入 `scripts/`。

### 6.4 可观测性（P2）
- Sentry 已可选接线；补：请求耗时日志（中间件，DEBUG 外仅采样）、AI 失败率看板（2.1 的延伸）、Celery 任务失败告警。

### 6.5 代码质量门禁（P2）
- 方案：`ruff`（lint+format 检查）+ `pytest-cov`（阈值：核心模块 apps/code_runner、apps/learning、apps/training、apps/examination ≥80%）+ `pre-commit` 配置。

### 6.6 CI 流水线（P2）
- 方案：GitHub Actions——push/PR 触发：install → `ruff check` → `pytest`（跳过 Manim 渲染与 Docker 依赖的用例，加 pytest marker `@pytest.mark.slow`）→ `pip-audit`。

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

- 2026-09-17 ｜ 模型路由修复 ｜ 新增 `AI_ACTIVE_MODEL`（应用专属最高优先级模型，免疫宿主 harness 环境变量污染）；planner 角色移除硬编码 reasoner 默认（未配置时随 provider）；`.env` 设 flash 为全角色模型 + flash→chat 回退链；相关 override 测试补 `AI_ACTIVE_MODEL=''` ｜ 117
- 2026-09-17 ｜ 修复：logger 未定义与成本统计时区边界 ｜ `learning_agent.py` 引用 logger 未定义（单元生成失败时 NameError 掩盖真实错误）→ 补定义 + 静态守护测试；`daily_cost_exceeded` 用 `now().date()`（UTC 日期）与 `__date` 本地时区查询在午夜附近漏计 → 改 `localdate()`；`.env` 配回退链（deepseek-flash→deepseek-chat） ｜ 115
- 2026-09-16 ｜ AI 落地深化 + P1 安全快赢 ｜ T4 登录限流（5 次/15 分钟锁定）、T3 内核每用户配额（默认 2）、T2 AI 审计 admin（只读）、T1 交卷 flush 防抖保存、T28 开发环境真实随机 SECRET_KEY；课程创建 AI 设计切到 CourseSkill（planner 角色）；Agent 角色标注（大纲/章节规划/结构请求→planner，作文评分→grader） ｜ 114
- 2026-09-16 ｜ **AI 架构重写（DeepSeek Harness 模式）** ｜ 新增 HarnessCore（角色路由 planner/worker/grader + 回退链 + 兼容层 + 审计）、Skills 层（CourseSkill/ExerciseSkill/ExamSkill）、BaseAgent 薄适配、三个生成命令切到 Skills；真实落地验证（ExerciseSkill 一次通过 7/7 沙箱用例） ｜ 111
- 2026-09-16 ｜ AI 修改能力（网页版） ｜ 习题详情「AI 修改」按钮（4.2）、考试管理页题目级 AI 修改（4.3）、`validate_exam` 命令（4.3）；抽公共模块 `apps/examination/question_ai.py` ｜ 107
