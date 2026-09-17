# Python 教学平台 — 程序员说明手册

> 文档版本：v1.2.0 ｜ 适用代码库：TeachingSpace（2026-09）
> 读者：平台开发与维护工程师

## 目录

1. [架构总览](#1-架构总览)
2. [技术栈](#2-技术栈)
3. [目录结构](#3-目录结构)
4. [开发环境搭建](#4-开发环境搭建)
5. [配置参考（环境变量全表）](#5-配置参考环境变量全表)
6. [核心系统设计](#6-核心系统设计)
   - 6.1 代码执行安全（沙箱）
   - 6.2 AI 系统（多模型 / 工具调用 / 成本控制）
   - 6.3 Notebook 素材解析
   - 6.4 考试系统
   - 6.5 异步任务（Celery）
   - 6.6 视频生成管线
7. [管理命令参考](#7-管理命令参考)
8. [测试](#8-测试)
9. [部署](#9-部署)
10. [开发规范](#10-开发规范)
11. [已知限制与路线图](#11-已知限制与路线图)

---

## 1. 架构总览

Django 5 单体应用，`apps/` 下按业务域拆分 10 个模块：

```
accounts      认证与角色（自定义 User、StudentProfile）
learning      学习课堂（Course→Chapter→Lesson→Cell + 版本快照 + 进度）
training      训练课堂（Exercise/Hint/Submission + 自动判分）
examination   考试课堂（多态题目、限时尝试、判分、证书）
chat          AI 助手（会话 + 工具调用）
ai_agents     AI 智能体（基类 + 4 个 Agent + 生成命令 + 成本跟踪）
code_runner   代码执行沙箱（subprocess / Docker 双后端）
core          共享工具（notebook 解析器）
video_generator  Manim 视频校验与渲染
```

关键设计原则：

1. **学生代码永不进入 Django 进程**——所有执行走隔离沙箱（见 6.1）。
2. **AI 多模型可插拔**——所有 AI 调用经 `apps/ai_agents/ai_config.py` 统一路由（见 6.2）。
3. **素材单一来源**——ClassLib notebook 的解析只有一份实现 `apps/core/notebook_parser.py`，管理命令、聊天工具、Claude Code skill 共用。
4. **关键内容人工审核**——AI 生成的考试一律保存为草稿；简答题无 AI 时保持待评阅。

## 2. 技术栈

| 层 | 选型 |
|----|------|
| Web | Django 5.2 + Bootstrap 5 + Alpine.js |
| 前端增强 | Marked.js（+DOMPurify 消毒）、KaTeX、SortableJS、Prism |
| 数据库 | SQLite（开发）/ PostgreSQL（生产） |
| 代码执行 | 子进程沙箱（默认）/ Docker 容器（`CODE_EXECUTION_BACKEND=docker`）/ 可选 RestrictedPython 编译加固 |
| AI | Anthropic SDK（兼容多 provider：Claude / DeepSeek / 自定义代理） |
| 异步 | Celery + Redis（开发默认 eager 内联，无需 broker） |
| 视频 | Manim Community（CLI 子进程渲染）+ FFmpeg |
| PDF | reportlab（STSong-Light CID 中文字体，无需字体文件） |
| 测试 | pytest + pytest-django（69 个测试） |

## 3. 目录结构

```
teaching_space/
├── config/                 # settings(base/dev/prod)、urls、celery、wsgi/asgi
├── apps/                   # 业务应用（见架构总览）
│   ├── code_runner/        #   executor.py(调度) + sandbox_runner.py(沙箱进程入口,单一来源)
│   ├── core/               #   notebook_parser.py（纯标准库,无 Django 依赖）
│   └── …                  #   各 app: models/views/urls/tests/tasks/management/commands/
├── templates/              # Django 模板（按 app 分目录）
├── static/                 # 静态资源（当前多为 CDN 引入）
├── media/                  # 上传与生成产物（images/videos/certificates/…）
├── docker/sandbox/         # 代码执行沙箱镜像（Dockerfile）
├── docs/                   # 本手册与用户手册
├── ClassLib/               # 教学素材 notebook（AI 助手与解析器的数据源）
├── conftest.py + pytest.ini # pytest 配置
└── manage.py
```

## 4. 开发环境搭建

```bash
# 1. Python 3.11+（本项目在 3.13 上开发验证；requirements.txt 已按 3.13 兼容锁定）
# 2. 虚拟环境
python -m venv venv
venv\Scripts\activate            # Windows
source venv/bin/activate        # Linux/macOS

# 3. 依赖
pip install -r requirements.txt

# 4. 环境变量：复制 .env.example 为 .env 并填写（见第 5 节）

# 5. 数据库
python manage.py migrate --settings=config.settings.development

# 6. 运行
python manage.py runserver --settings=config.settings.development

# 7. 测试
python -m pytest
```

依赖说明：

- `gunicorn` 是 **Linux-only**，不写入 requirements.txt——生产服务器上单独 `pip install gunicorn==21.2.0`；
- `RestrictedPython` 是可选加固（装上自动生效）；Python 3.13 需用 8.x（7.0 因沙箱逃逸漏洞被 PyPI 下架）；
- `manim` 渲染还需要 **FFmpeg 可执行文件在 PATH 中**（pip 不提供）；Windows 可 `winget install ffmpeg` 或使用 Anaconda；
- 应用启动**不依赖 celery**（`config/__init__.py` 对导入做了降级处理）；但训练判分的异步队列需要 celery 包。

可选组件：

```bash
# Docker 沙箱（完整 OS 级隔离）
docker build -f docker/sandbox/Dockerfile -t teaching-space-sandbox .
# 然后在 .env 设 CODE_EXECUTION_BACKEND=docker

# Celery worker（生产异步判分；开发无需）
celery -A config worker -l info --pool=solo   # Windows
celery -A config worker -l info               # Linux
```

## 5. 配置参考（环境变量全表）

设置通过 python-decouple 从 `.env` 读取（`--settings=config.settings.development|production`）。

**优先级规则（重要，T31）**：`系统环境变量 > .env 文件 > 默认值`。宿主环境（如 Claude Code harness）可能注入 `AI_MODEL`/`ANTHROPIC_*` 等变量覆盖 `.env`——应用专属设置请用 `AI_ACTIVE_MODEL`（最高优先级，见 5.2），或在启动终端中 `Remove-Item Env:变量名` 清除。修改 `.env` 后必须重启服务才生效。

### 5.1 核心

| 变量 | 默认 | 说明 |
|------|------|------|
| `SECRET_KEY` | — | **production 强制要求真实值**（占位符直接启动失败） |
| `DEBUG` | True | production 强制 False |
| `ALLOWED_HOSTS` | localhost,127.0.0.1 | 逗号分隔 |
| `DB_ENGINE/NAME/USER/PASSWORD/HOST/PORT` | sqlite3（dev） | production 使用 PostgreSQL 且全部必填 |

### 5.2 AI（多模型）

| 变量 | 默认 | 说明 |
|------|------|------|
| `AI_PROVIDER` | anthropic | 激活的模型供应商：`anthropic` / `deepseek` |
| `AI_MODEL` | （空） | 覆盖当前供应商的模型名（如 `deepseek-reasoner`） |
| `ANTHROPIC_API_KEY` | — | Claude/代理密钥 |
| `ANTHROPIC_MODEL` | claude-sonnet-4-5-20250929 | Anthropic 模型名 |
| `ANTHROPIC_BASE_URL` | — | 自定义 Anthropic 兼容代理端点 |
| `deepseek_Api` | — | **DeepSeek 密钥（注意变量名大小写）** |
| `DEEPSEEK_BASE_URL` | https://api.deepseek.com/anthropic | DeepSeek 的 Anthropic 兼容端点 |
| `DEEPSEEK_MODEL` | deepseek-flash | DeepSeek 模型名（deepseek-flash / deepseek-chat / deepseek-reasoner） |
| `AI_MAX_TOKENS` | 4096 | 单次请求上限 |
| `AI_TEMPERATURE` | 0.7 | 生成温度 |
| `AI_CACHE_ENABLED` | True | 相同 prompt+model 24h 内命中缓存 |
| `AI_COST_LIMIT_DAILY` | 50.00 | 每日成本上限（USD，0 表示不限）；按 `AI_COST_INPUT/OUTPUT_PER_MTOK`（默认 3/15）估算 |

**切换模型示例**：`.env` 中设 `AI_PROVIDER=deepseek` 并确保环境变量 `deepseek_Api` 存在——聊天助手、全部 Agent、作文评分自动跟随，无需改代码。添加新供应商：在 `config/settings/base.py` 的 `AI_PROVIDERS` 注册表增加条目即可。

### 5.3 执行与任务

| 变量 | 默认 | 说明 |
|------|------|------|
| `CODE_EXECUTION_BACKEND` | subprocess | `docker` 时启用完整隔离（需已构建沙箱镜像） |
| `SANDBOX_DOCKER_IMAGE` | teaching-space-sandbox | 沙箱镜像名 |
| `REDIS_URL` | redis://localhost:6379/0 | Celery broker |
| `CELERY_ALWAYS_EAGER` | =DEBUG | True 时任务内联执行（无需 Redis） |

### 5.4 视频

| 变量 | 默认 | 说明 |
|------|------|------|
| `MANIM_OUTPUT_DIR` | media/videos | 渲染输出目录 |
| `MANIM_QUALITY` | medium | 默认画质（low/medium/high/production） |

其余：`EMAIL_*`（邮件）、`SENTRY_DSN`（production 可选）。

## 6. 核心系统设计

### 6.1 代码执行安全（沙箱）

**单一 runner**：`apps/code_runner/sandbox_runner.py` 是沙箱执行唯一实现（stdlib-only）。协议：父进程把 JSON 请求写 stdin（`{mode, code, test_cases?, stdin_input?, max_output_length}`），runner 执行后向 stdout 写 `__SANDBOX_RESULT__<json>`——学生输出全部封装在 JSON 内，不接触进程 stdout。

**双重隔离后端**（`executor.py` 调度）：

| 后端 | 机制 | 隔离级别 |
|------|------|---------|
| `subprocess`（默认） | `python -I` 子进程 + 硬超时 kill | 与 Django 进程隔离；同一 OS 用户 |
| `docker` | 同一 runner 装入容器：`--network none`、128m 内存、0.5 CPU、pids-limit 64、只读 rootfs、`cap-drop ALL`、非 root 用户 | 完整 OS 级隔离 |

**沙箱内三层防护**：
1. **builtins 白名单**：无 `__import__`（仅 math/random/json 等白名单模块）、无 `open/eval/exec/compile`、无 `type/getattr/dir` 等自省函数；
2. **AST 检查**：禁止 `_` 前缀属性访问（封堵 `().__class__.__mro__` gadget 链）；
3. **可选 RestrictedPython**：安装后 runner 自动启用编译期限制（requirements.txt 已含，Dockerfile 留了安装开关）。

**超时**：父进程 `subprocess.run(timeout=N)`，超时即 kill 并抛 `TimeoutError`（判分方据此标记 timeout 状态）。

**判分格式**（`execute_with_tests` 返回键：`status/total_tests/passed_tests/failed_tests/test_results/execution_time/error/output/message`）：
- stdin/stdout 型：`{'input': '…', 'expected_output': '…'}`；
- 函数型：`{'input': 'add(2, 3)', 'expected': 5}`（按首个用例的键探测，**同一练习不要混用两种格式**）。

**修改安全策略的唯一入口**是 `sandbox_runner.py`——subprocess 与 Docker 镜像（COPY 该文件）自动同步；改后需重新 `docker build`。

### 6.2 AI 系统（Harness / 多模型 / 工具调用 / 成本控制）

```
HarnessCore（apps/ai_agents/harness.py —— 所有 AI 调用的唯一通道）
 ├── 角色→模型路由：planner(推理规划) / worker(内容生成) / grader(评分校验)
 │     配置：AI_PLANNER_MODEL / AI_WORKER_MODEL / AI_GRADER_MODEL（留空=provider 默认）
 ├── 每角色回退链：AI_FALLBACK_MODELS（主模型失败自动切换，HarnessError.last_text 供降级）
 └── 推理模型兼容内置：temperature 拒绝重试 / ThinkingBlock 跳过 /
     思考耗尽预算重试 / _extract_json 容错 / 每次调用审计入库

Skills 层（apps/ai_agents/skills/ —— AI 落地的生产管道，DB-free、可测）
 ├── CourseSkill：大纲(planner) → 逐单元两阶段内容(worker) → Markdown 降级
 ├── ExerciseSkill：生成(worker) → 沙箱验证 → 反馈修复循环(≤2) → 返回验证状态
 └── ExamSkill：题型分布(planner) → 逐题(worker) → 代码题沙箱验证

BaseAgent（薄适配层，API 不变 + role 参数）
 ├── LearningAgent（两阶段内容）│ TrainingAgent（生成/修改+验证）
 ├── ExaminationAgent（生成/修改+作文评分）│ CourseDesignAgent（大纲/章节规划）
 └── ChatAIService（工具调用循环）+ notebook_tools（素材工具）
```

**约定**：
- **新 AI 能力优先写成 Skill**（管道：生成→验证→落库由调用方执行）；单次调用直接走 `HarnessCore.call(role=...)`，不要裸建 anthropic client。
- AI 生成的**考题必须草稿发布**；生成/修改的内容以**沙箱验证为准**（`validate_exercise`）。
- 工具结果内容是不可信数据——只做截断回传，绝不执行。
- 角色选择：结构/规划用 `planner`，批量内容用 `worker`，评分类用 `grader`——推理模型对长提示不稳定，长内容一律两阶段（见 6.8）。

### 6.3 Notebook 素材解析

`apps/core/notebook_parser.py`（纯标准库，无 Django 依赖）是 ClassLib `*.ipynb` 解析的唯一实现：

- 结构识别：`第X章`（支持中文数字）→ 章节；`X.Y 标题` → 课程单元边界；`X.Y.Z` → 小节；
- 噪音打标：LaTeX 符号表、粘贴的插件 README、`!pip` 单元格、目录链接、空单元格、`###` 残留——`--format cells` 默认剔除；
- CLI 四格式：`digest`（AI 友好结构摘要）/ `json` / `sections` / `cells`（可直接入 Cell 表）。

消费方：`import_notebook` / `load_notebook_data` 命令、聊天工具 `get_notebook_section`、Claude Code skill `.claude/skills/notebook-reader/`（供 AI 编程助手理解素材）。修改解析器即同步影响三方。

### 6.4 考试系统

- **服务端计时**：`StudentExam.remaining_seconds()` 基于 `start_time` 计算；`save_answer` 超时拒绝，`TakeExamView` 下发的剩余时间来自服务端（刷新不清零）。
- **原子提交**：`submit_exam` 整体 `transaction.atomic()` + `select_for_update()`——双击不重复判分，判分异常回滚不留"已提交未计分"的锁死状态。
- **多态题目**：`Question.get_specific_question()` 用显式 accessor 映射（曾因 `getattr` 拼写错误导致判断题整体失效——**新增题型时同步维护该映射与四个 OneToOne 的 prefetch 列表**）。
- **判分**：选择/判断 `auto_grade()`；编程题沙箱执行测试用例；简答题有 AI 时自动评分，否则 `needs_review` 人工评阅（后台评阅后 `calculate_score()` 需手动重算——当前由管理员操作触发）。
- **证书**：`certificate_download` 惰性生成 PDF（reportlab + STSong-Light CID 字体，中文无需字体文件）；验证码 32 位；公开验证页按码查询。生成流程：先建记录拿验证码（PDF 内嵌）→ 再生成文件。

### 6.5 异步任务（Celery）

- `config/celery.py` + `config/__init__.py`（经典接线）。**autodiscover 在 worker 信号中执行**（任务模块导入 Django 模型，必须在 `django.setup()` 之后）——不要改成在 celery.py 顶层 autodiscover。
- 开发默认 `CELERY_TASK_ALWAYS_EAGER=True`：`delay()` 内联执行、无需 Redis；生产置 False 后训练判分走后台（提交返回 `running` 状态）。
- 无 Celery 安装时 `apps/training/tasks.py` 自动降级为同步调用，应用不中断。
- 新增异步任务：放在已安装 app 的 `tasks.py`，用 `@shared_task`。
- **重试策略（2.3）**：AI 生成类任务（课程大纲/单元生成/整卷生成）`bind=True, max_retries=2`，
  失败时 `self.retry(exc, countdown=5·2^n)`（5s→10s，封顶 120s）；视频渲染仅对超时重试一次
  （脚本错误是确定性的，不重试）。**eager 模式无 broker，Retry 异常会穿透到调用视图**——
  任务内必须用 `self.request.is_eager` 守卫（见 `apps/learning/tasks.py` / `apps/examination/tasks.py`
  的既有实现），eager 下直接发布 error 状态并吞掉异常；最终失败状态写入 cache 供前端轮询。
- 任务进度发布约定：`lesson_gen_status:<id>` / `course_design_status:<id>` /
  `exam_gen_status:<id>`，状态 `running | retrying | done | error`，TTL 1 小时。

### 6.6 视频生成管线

```
VideoAgent.generate_video_script()  # AI 生成脚本（围栏正则提取,不动字符串内反引号）
  → script_validator.validate_script()   # AST:禁 import/调用、必须 Scene 子类、长度上限
  → manim_engine.render_script()         # manim CLI 子进程 + 超时 + 归档 MANIM_OUTPUT_DIR
  → Video 记录（lesson/cell 关联、manim_script、generation_status）
```

渲染是重操作，始终在子进程进行并强制超时；输出 mp4 按 `场景名_时间戳` 归档。校验失败**直接拒绝渲染**并保留脚本供人工审查。

### 6.7 Jupyter 内核会话（学习课堂）

学习课堂的代码单元格运行在**真实 ipykernel 会话**上（`apps/learning/jupyter_kernel.py`）：

- 每个 (user, lesson) 一个长生命周期内核：**变量跨单元格持久**、富输出（stream/execute_result/display_data/error）、In[n] 执行计数、matplotlib 内联图；
- 生命周期：空闲 `JUPYTER_KERNEL_IDLE_TIMEOUT`（默认 15 分钟）回收、`JUPYTER_MAX_KERNELS`（默认 20）LRU 淘汰、`restart` 端点清空变量；
- 超时语义：`JUPYTER_EXECUTE_TIMEOUT`（默认 15 秒）→ interrupt 保留会话；**Windows 下 ipykernel 中断不可靠**，3 秒未恢复自动重启内核并告知（跨平台兜底已在实现中）；
- 双后端：`local`（ipykernel 子进程，**仅限开发**——完整 Python 权限）与 `docker`（`teaching-space-kernel` 镜像：五个 ZMQ 端口仅发布到 127.0.0.1、内存/CPU/PID 受限、cap-drop ALL、非 root）；
- **安全边界（有意为之）**：学习内核是完整 Python（与 Colab 同类产品一致），容器负责隔离宿主；容器网络出口未阻断（学员可 pip install 等），宿主与局域网不受影响。**判分路径（训练/考试）仍走 6.1 的严格沙箱**——两条执行链的安全模型不要混用；
- 输出截断：文本 ≤50KB、二进制 ≤5MB；前端只通过 `textContent` 插入内核文本，HTML 输出过 DOMPurify；
- 内核镜像含 numpy/matplotlib/pandas；构建：`docker build -f docker/kernel/Dockerfile -t teaching-space-kernel .`

### 6.8 AI 辅助课程设计（教师工作台流程）

```
【创建时】教师创建课程（勾选 AI 辅助）
  → CourseDesignAgent.design_course_outline()    # 章节+单元大纲（JSON）
      ↑ 可选接地：notebook_tools.find_related_sections(主题)
        —— 扫描 ClassLib 全部 notebook，按标题/关键词匹配相关小节，注入提示词
  → 创建 Course + Chapters + Lessons（全部草稿、无单元格）
  → 大纲确认页（instructor/outline.html）

【日常使用】课程详情页（教师工作区）每个章节都有「AI 生成本章」：
  ├─ 本章无课程单元 → CourseDesignAgent.design_chapter_lessons()
  │                    AI 先规划单元列表（编号继承章节，素材自动接地）
  └─ 本章有课程单元 → 逐单元调用 instructor_lesson_generate：
       LearningAgent.generate_lesson_content()   # 两阶段生成（见下）
       → 重建该单元 Cells（先清后建，重复生成幂等）
  单元级另有「AI 生成/重新生成」按钮 + 单元格数徽标
```

**两阶段内容生成**（`LearningAgent.generate_lesson_content`，针对推理模型设计）：

1. **结构请求**（小响应、低思考预算）：返回 `{"cells": [{"type", "title"}]}`（6-10 格，max_tokens=800）；
2. **逐格内容请求**：每个单元格一次短请求（max_tokens=1200，代码格自动剥离围栏）——短提示下推理模型（deepseek-flash 等）输出稳定；
3. **降级链**：结构请求失败但有文本 → 按 ``` 围栏把 Markdown 切分为单元格；完全无文本 → 再发一次纯 Markdown 请求（`_generate_plain_lesson`）；单个单元格失败不影响其余格。

- 无 AI 密钥时自动回退手动流程（创建空课程 + 提示）；
- 生成调用经过 `BaseAgent` 统一管道（成本记录/日限额/缓存）；
- 新增 AI 能力遵循同样模式：Agent 类 + 视图内懒导入 + 无密钥降级 + mock 测试（参见 `apps/learning/tests.py::AICourseDesignFlowTests`）。

## 7. 管理命令参考

所有命令加 `--settings=config.settings.development`（生产用 production）。

| 命令 | 用途 |
|------|------|
| `create_instructor --username X [--password] [--make-superuser]` | 开通教师账号（唯一正规渠道，学生注册固定为 student） |
| `generate_lesson "主题" [--difficulty] [--course] [--notebook 名] [--section 1.2] [--publish]` | AI 生成课程单元（可接地真实素材），默认草稿 |
| `generate_exercises --topic X --count N [--course slug]` | AI 生成练习+测试用例+提示 |
| `generate_exam --course slug --question-count N` | AI 生成考试（**草稿**，后台审核发布） |
| `generate_video_script "主题" [--render] [--quality] [--lesson id]` | AI 生成/可选渲染 Manim 视频脚本 |
| `test_ai_agents` | AI 连通性检查（显示 provider/模型，1 token 探测） |
| `batch_generate_content --course-id N` | 课程批量生成练习+考试草稿 |
| `import_notebook <文件> [--course-name]` | 按 `X.Y` 小节拆分为多课程单元导入（幂等） |
| `load_notebook_data [--notebook 名]` | 整本导入为单课程单元（幂等） |
| `load_additional_content` / `load_sample_exercises` / `load_sample_exams` | 示例内容种子数据 |
| `export_notebook --lesson-id N [--format json\|md] [--output 文件]` | 导出课程单元 |

## 8. 测试

```bash
python -m pytest                    # 全量（69 个，约 35 秒,含一次真实 Manim 渲染）
python -m pytest apps/chat          # 单 app
python manage.py test apps.chat --settings=config.settings.development  # 备选通道
```

- 配置在 `pytest.ini` + 根 `conftest.py`（`django.setup()`；pytest-django 安装后自动增强）。
- 覆盖重点（新增功能必须补测试）：
  - `code_runner`：沙箱逃逸尝试（os 导入/gadget 链/open）、超时、双判分模式、返回键契约；
  - `training`：判分正确性、防刷（重复提交不加分）、提示扣分一致性；
  - `examination`：判断题 accessor、证书下载/验证/复用/未通过拒绝；
  - `accounts`：注册越权、开放重定向；`learning`：单元格重排唯一约束、权限、版本恢复；
  - `ai_agents`：provider 路由、成本上限；`chat`：工具循环（mock 客户端）、错误脱敏；`video_generator`：校验器 + 真实渲染（输出隔离到临时目录，不污染 media/）。
- 注意：Docker 沙箱路径依赖本机 Docker 与镜像，未纳入自动化测试；改动 runner 后除跑测试外，还应手动复验 docker 模式（见 6.1 验证清单）。

## 9. 部署

1. **服务器准备**：Python 3.11+、PostgreSQL、Redis（生产异步）、Docker（启用 docker 沙箱时）。
2. **构建沙箱镜像**：`docker build -f docker/sandbox/Dockerfile -t teaching-space-sandbox .`
3. **配置**：`.env` 按第 5 节全表填写；production 强制要求真实 `SECRET_KEY`。
4. **入口**：`wsgi/asgi` 默认指向 `config.settings.production`；启动前自动创建 `logs/`。
5. **静态文件**：WhiteNoise（CompressedManifestStaticFilesStorage）——`collectstatic` 后由 WSGI 直接服务。
6. **Worker**：`celery -A config worker -l info`（supervisor/systemd 托管）。
7. **上线检查清单**：
   - [ ] `SECRET_KEY` 为真实随机值，`.env` 未入库
   - [ ] `DEBUG=False`、`ALLOWED_HOSTS` 不含 `*`
   - [ ] 沙箱：生产建议 `CODE_EXECUTION_BACKEND=docker` 且镜像已构建
   - [ ] 每日 AI 成本上限按预算设置（`AI_COST_LIMIT_DAILY`）
   - [ ] `manage.py check --deploy` 无高危项；Sentry DSN（可选）
   - [ ] 备份：SQLite 文件或 PostgreSQL 定期备份 + `media/`（证书与视频）

### 9.1 Docker Compose 全栈（T30）

`docker-compose.yml` 提供 web + celery + redis + postgres 四服务编排（应用镜像 `docker/app/Dockerfile`，gunicorn 3 workers、非 root）。首次部署：

```bash
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

注意：执行类后端（沙箱/内核镜像）仍按第 6.1/6.7 节单独构建；`media/` 与 `pgdata` 为持久卷。

### 9.2 备份与恢复（T29）

- **数据库**：PostgreSQL 每日 `pg_dump`（cron 示例）：
  ```bash
  docker compose exec db pg_dump -U postgres teaching_space | gzip > backup_$(date +%F).sql.gz
  ```
  恢复：`gunzip -c backup_YYYY-MM-DD.sql.gz | docker compose exec -T db psql -U postgres teaching_space`
- **文件**：`media/` 卷（证书、视频、头像）随 pg_dump 同日归档（tar 或对象存储）；
- **演练**：每季度在测试环境执行一次恢复演练，验证备份可用。

### 9.3 密钥轮换（1.3）

- **轮换时机**：人员离职、疑似泄露、或至少每年一次。
- **步骤**：① 生成新值 `python -c "import secrets; print(secrets.token_urlsafe(50))"`；② 停机维护窗口内
  更新 `.env` 的 `SECRET_KEY`（以及 `deepseek_Api`/`ANTHROPIC_API_KEY` 等外部密钥在其供应商侧
  revoke + 重建）；③ 重启全部 web/worker 进程；④ 轮换后旧会话全部失效（用户需重新登录），提前在公告中说明。
- **注意**：`SECRET_KEY` 参与签名（session/cookie/CSRF），轮换会导致已签发证书验证码外的一切签名失效；
  证书验证码是随机 UUID 存库，不受影响。

### 9.4 依赖与基线更新（1.4）

- **季度升级流程**：① `pip install -U -r requirements.txt`（venv 内，记录 diff）；② 全量测试
  `pytest -m "not slow"` + 冒烟 `pytest -m slow`；③ `pip-audit`（CI 每次运行，本地可手动执行）；
  ④ 有修复项（security）则优先升；⑤ 升级后回归 AI 连通性 `manage.py test_ai_agents`；
  ⑥ 记录版本变更到 CHANGELOG。
- CI 的 pip-audit 步骤当前为非阻断（`|| true`）——安全告警由人工在 PR 页查看并跟进。

## 10. 开发规范

1. **权限**：学习课堂的教师权限用 `_can_edit_lesson()`（课程 instructor 或 staff）；所有单元格写接口必须校验；学生可见内容一律过滤 `is_published`。
2. **错误处理**：API 层统一 `_error_response`（学习）或 DEBUG 开关脱敏模式（训练/考试）——生产响应不泄露 `str(e)`，细节进日志。
3. **安全**：
   - 模板进 JS 一律 `json_script` 或 `escapejs_tick` 过滤器；`x-html` 内容必须过 DOMPurify；聊天 `innerHTML` 前必须 `escapeHtml()`。
   - 学生代码只经 `CodeExecutor` 执行；任何"临时放开"（如直接 `exec`）视为发布阻断。
   - 管理命令创建用户必须显式密码参数或随机生成并打印一次，禁止硬编码。
4. **模型**：slug 用 `save()` 内的兜底+去重逻辑（中文标题 slugify 为空）；JSONField 数据的键名变更需兼容旧数据。
5. **数据库操作**：涉及计数/积分的读改写一律 `F()` + `select_for_update()`；顺序字段批量移动用两阶段（先 +1,000,000 再归位）避免撞唯一约束。
6. **AI 提示词**：f-string 内的 JSON 示例必须双花括号（单花括号在 Python 3.12+ 会被当表达式求值）；函数型测试用例用 `expected` 键（不要 `expected_output`）。
7. **文档同步**：改公开行为后同步本手册、`docs/USER_MANUAL.md`、`CLAUDE.md` 与 `OPTIMIZATION_PLAN.md` 进度记录。
8. **质量门禁（6.5）**：`ruff check apps config` 必须零告警（配置见 `pyproject.toml`；`ruff format` 有意不启用——与既有风格冲突，改动 98 个文件收益为负）；本地提交前装 `pre-commit`（`.pre-commit-config.yaml`）；核心模块（code_runner/learning/training/examination）合并覆盖率 ≥80% 由 CI 强制（`sandbox_runner.py` 以子进程执行，从行覆盖中排除）。

## 11. 已知限制与路线图

| 项 | 状态 | 说明 |
|----|------|------|
| 视频 CDN/对象存储 | 未实现 | 渲染产物与缩略图本地存储；生产 CDN 归档待做 |
| 流式 AI 内容生成 | 未实现 | 生成类任务为异步+轮询（非 SSE）；聊天流式已实现 |
| Docker 镜像源 | 视网络 | 国内环境需镜像源或代理拉取基础镜像（DaoCloud 已验证可用） |
| 多语言 | 中文为主 | 界面中英混杂，完整 i18n 未做（已决策归档，见 T23） |

---

*本手册由代码库审计同步生成；如有出入以代码与 `CLAUDE.md` 为准。*
