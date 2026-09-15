# 项目深度诊断与优化方案

> 生成日期：2026-09-16
> 依据：对全仓库（config、10 个 app、templates、static）的静态深度分析，关键判分 bug 已人工逐行复核。
> 性质：防御性安全审计 + 代码质量诊断，未进行实际渗透测试。

## 总体评价

架构设计合理（课程→章节→课程单元、Cell JSON 多态、AI Agent 分层清晰），功能面广，但存在 **3 类致命安全漏洞 + 3 个让核心功能失效的 bug**，测试覆盖为零，大量依赖（Celery / DRF / HTMX / CodeMirror / allauth / markdownx）安装后未使用。**当前代码不适合对公网开放**。

按优先级分为：🔴 P0（必须立即修）→ 🟠 P1（高）→ 🟡 P2（中）→ 🟢 P3（功能补全与长期优化）。

---

## 🔴 P0 — 安全与核心功能

### P0-1 代码执行完全无沙箱（RCE）

**位置**：[apps/code_runner/executor.py:64-198](apps/code_runner/executor.py#L64-L198)

**问题**：尽管模块 docstring 和 CLAUDE.md 声称使用 RestrictedPython，实际上 `_execute_restricted()` 是裸 `exec(code, namespace)` 直接运行在 Django 进程内，仅靠子串关键词黑名单防护：

- 绕过方式（全部成立）：
  - `from os import system` —— 不含 `import os` 子串
  - `import  os`（双空格）、`open (` 加空格
  - `__builtins__['__builtins__']['__im'+'port__']('os')` —— 字符串拼接绕过 `__import__` 黑名单；且黑名单把真实 `__import__` 直接放进了 "safe builtins"（[executor.py:93-95](apps/code_runner/executor.py#L93-L95)）
  - `len.__self__.__dict__['open']('/etc/passwd').read()` —— `len.__self__` 即真实 builtins 模块，绕过 `open(` 黑名单
  - `().__class__.__mro__[1].__subclasses__()` —— 经典对象子类遍历；`getattr`/`type`/`dir`/`hasattr` 均被显式提供给沙箱
- 后果：任何登录用户（配合 P0-12，甚至不需要选课）即可在服务器上读文件、开进程、访问网络、`os._exit(0)` 杀进程。
- 误伤：`print("open(")` 这类合法代码反而被黑名单误杀。

**修复建议**（按成本递增）：
1. 最短路径：改用 **subprocess 子进程隔离** —— 起一个受限 Python 子进程执行代码，父进程用 `subprocess.run(..., timeout=N)` 强制超时、限制 `resource`/内存，不依赖任何黑名单。
2. 中期：真正接入 RestrictedPython 7.0（已在 requirements.txt 中），配合 `safe_builtins` 白名单 + AST 过滤。
3. 终极：Docker 容器隔离（`docker/` 目录已预留，`_execute_docker` 是 TODO 桩）。

### P0-2 执行无超时（DoS）

**位置**：[apps/code_runner/executor.py:24](apps/code_runner/executor.py#L24)

**问题**：`self.timeout` 赋值后从未被读取，无 signal/线程/subprocess 隔离。`while True: pass` 可永久挂死同步 worker 线程；`Submission.grade()` 里捕获 `TimeoutError` 的分支（[training/models.py:164-166](apps/training/models.py#L164-L166)）是死代码。`CODE_EXECUTION_TIMEOUT` 等设置（[base.py:162-164](config/settings/base.py#L162-L164)）无人使用。

**修复**：随 P0-1 一起解决（subprocess 天然支持 timeout）。

### P0-3 存储型 XSS（4 处）

**位置**：
- [templates/learning/lesson_edit.html:402](templates/learning/lesson_edit.html#L402) —— `{{ cells_json|safe }}` 直接嵌入 `<script>`；`json.dumps` 不转义 `<`/`>`/`&`，而单元格 `output` 是学生可控的（`Cell.execute()` 保存学生 stdout）。学生在代码单元格打印 `</script><script>…</script>`，教师下次打开编辑器即被劫持（以教师权限执行）。
- [templates/learning/lesson_edit.html:276,316](templates/learning/lesson_edit.html#L276) 与 [lesson_detail.html:227](templates/learning/lesson_detail.html#L227) —— `x-html` + `marked.parse()` 默认放行原始 HTML，全项目无 DOMPurify；`escapejs` 不转义反引号，markdown 内容可突破 `renderMarkdown(\`…\`)` 模板字符串参数。
- [templates/chat/chat_interface.html:493-504](templates/chat/chat_interface.html#L493-L504) —— JS 用 `innerHTML` 拼接未转义的用户消息和 AI 回复（`addMessageToUI`/`loadConversation` 共用）。

**修复**：
1. 替换为 Django `{{ cells_json|json_script:"cells-data" }}` + `JSON.parse(document.getElementById('cells-data').textContent)`。
2. 引入 DOMPurify（cdnjs 可用），所有 `x-html` 与 marked 输出统一过 `DOMPurify.sanitize()`。
3. 聊天界面改用 `textContent`/`createElement`，或先 `escapeHtml()` 再插入。
4. `renderMarkdown` 失败回退应返回纯文本而非原始 markdown。

### P0-4 注册越权

**位置**：[apps/accounts/views.py:26,55](apps/accounts/views.py#L26)

**问题**：`user_type = request.POST.get('user_type', 'student')` 无白名单直接传给 `create_user()`。注册页甚至公开提供 "Instructor" 选项；构造 POST `user_type=admin` 可直接建管理员角色账号。

**修复**：只允许 `student`；instructor 账号仅由管理员创建。同时接入 `django.contrib.auth.password_validation.validate_password()`（现有密码校验仅 `len() < 8`，settings 里配好的 4 个 validator 从未被调用）。

### P0-5 登录开放重定向

**位置**：[apps/accounts/views.py:99-100](apps/accounts/views.py#L99-L100)

**问题**：`next_url = request.GET.get('next', ...)` 未校验直接 `redirect(next_url)`，`//evil.com` 可跳离站。

**修复**：用 Django 5.0 的 `django.utils.http.url_has_allowed_host_and_scheme()` 校验。另：logout 是 GET 状态变更，建议改 POST。

### P0-6 硬编码凭据

**位置**：
- [apps/learning/management/commands/import_notebook.py:30](apps/learning/management/commands/import_notebook.py#L30) —— `admin/adminpass`
- [apps/learning/management/commands/load_notebook_data.py:44-46](apps/learning/management/commands/load_notebook_data.py#L44-L46) —— `admin123`
- [apps/examination/management/commands/load_sample_exams.py:17-26](apps/examination/management/commands/load_sample_exams.py#L17-L26) —— `instructor/instructor123`

**修复**：改为命令行参数（`--username`/`--password`）或环境变量，未提供时交互式输入/报错退出，绝不落默认密码。

### P0-7 密钥管理

- `.env` 含真实第三方代理 API key（已 gitignore，但建议**尽快轮换**，特别是仓库可能被分享时）。
- `.env` 与 `.env.example` 中 `SECRET_KEY` 均为占位符 `your-secret-key-here-change-in-production`。
- 聊天请求把服务器本地绝对路径（ClassLib 文件路径）发给 LLM 供应商（[chat/ai_service.py:32-57](apps/chat/ai_service.py#L32-L57)）——应改为只发文件名 + 相对路径。

### P0-8 训练判分恒"通过"（已人工验证）

**位置**：[apps/training/models.py:135-142](apps/training/models.py#L135-L142)

**问题**：`grade()` 读取不存在的键 `results`/`tests_passed`/`tests_total`（`execute_with_tests` 实际返回 `test_results`/`passed_tests`/`total_tests`）。三者恒为 `[]`/`0`/`0`，`if self.tests_passed == self.tests_total` → `0 == 0` 恒真 → **所有提交一律判"通过"、全额给分**（即使测试全错）。积分系统随之可无限刷。

**修复**（一行级改动）：
```python
self.test_results = result.get('test_results', [])
self.tests_passed = result.get('passed_tests', 0)
self.tests_total = result.get('total_tests', 0)
```
并增加 `if self.tests_total > 0` 守卫。

### P0-9 考试代码题恒 0 分（已人工验证）

**位置**：[apps/examination/views.py:257](apps/examination/views.py#L257)

**问题**：`passed_tests = result.get('passed', 0)` —— 实际键是 `passed_tests` → 永远 0 → 所有代码题 0 分、`is_correct=False`。

**修复**：改为 `result.get('passed_tests', 0)`。

### P0-10 判断题完全失效

**位置**：[apps/examination/models.py:119](apps/examination/models.py#L119)

**问题**：`getattr(self, 'truefalseavequestion', None)` 拼写错误（应为 `truefalsequestion`）→ 判断题详情永远取不到 → 考试界面无作答控件（[exam_interface.html:125](templates/examination/exam_interface.html#L125)）、`auto_grade()` 对判断题直接跳过 → 判断题不判分、不进总分。

**修复**：改正拼写；建议给 `TrueFalseQuestion.question` 加显式 `related_name`，并把 4 个 `getattr` 改为显式字典映射，避免同类问题。

### P0-11 单元格重排/插入/删除 IntegrityError

**位置**：[apps/learning/views.py:173,283,346-348](apps/learning/views.py#L346-L348) + [models.py:111](apps/learning/models.py#L111)

**问题**：`unique_together=['lesson','order']` 是即时约束，`order__gte=order).update(order=F('order')+1)` 类逐行位移（如 1→2 与 2→3）在 SQLite/Postgres 默认约束下中途撞唯一性 → 拖拽换序保存必炸；删除同理；两个单元格互换更是第一步就撞。

**修复**：先 `update(order=F('order') + 10000)` 挪到安全区，再归位；或把 constraint 声明为 deferrable。建议抽一个 `_renumber_cells(lesson, orders: list[int])` 工具函数统一三处逻辑。

### P0-12 学习/考试权限缺失

**位置**：
- [apps/learning/views.py:91-152](apps/learning/views.py#L91-L152) —— `LessonDetailView` 不校验 `status=published` 与选课；`LessonEditView` 仅 `LoginRequiredMixin`，任何登录用户可打开任何课程单元的编辑页（泄露全部单元格内容与 `cells_json`）
- [apps/learning/views.py:293-316](apps/learning/views.py#L293-L316) —— `execute_cell` 不校验选课，任何登录用户可执行任意课程单元的代码（配合 P0-1 即全员 RCE）
- [apps/examination/views.py:45-47](apps/examination/views.py#L45-L47) —— `ExamDetailView` 不过滤 `is_published`，草稿考试对所有人可见

**修复**：抽公共权限助手（现 4 处复制粘贴 `request.user != instructor and not is_staff`）；详情页过滤 `status=published`；编辑页要求 instructor/staff；`execute_cell` 要求已选课学员。

---

## 🟠 P1 — 高优先级

### P1-1 考试计时纯摆设

**位置**：[apps/examination/views.py:107-112,188-229](apps/examination/views.py#L107-L112)

`time_remaining_seconds` 只在开始时写入一次、从不校验/递减（模型 help_text 声称"后端验证防作弊"——不存在）。刷新页面计时归零；`save_answer`/`submit_exam` 随时可提交；禁 JS 则无计时。

**修复**：`StudentExam` 记录 `started_at`；`save_answer`/`submit_exam` 校验 `now - started_at <= duration`，超时后 `submit_exam` 按已答内容计分。

### P1-2 考试提交无原子性

**位置**：[apps/examination/views.py:232-234](apps/examination/views.py#L232-L234)

先置 `is_submitted=True` 再判分、无事务。判分中途异常（如无 `student_profile`，[views.py:285](apps/examination/views.py#L285)）→ 学生被锁死在"已提交未计分"；双击并发可双重提交、双重加分。

**修复**：`transaction.atomic()` + `select_for_update()` 包裹整个提交流程；`is_passing()` 加分之前先判断是否已计分。

### P1-3 学生执行结果写入共享单元格

**位置**：[apps/learning/models.py:120-138](apps/learning/models.py#L120-L138)

`Cell.execute()` 把每个学生的 stdout/状态/执行次数持久化进课程共享 cell，学生之间、学生与教师互相覆盖。

**修复**：执行结果只回传前端，不落库；或按用户存到 `LessonProgress.code_cells_run` 级别的会话数据。

### P1-4 积分可刷 + 提示扣分两套标准

**位置**：[apps/training/models.py:142-155](apps/training/models.py#L142-L155)、[views.py:154-158](apps/training/views.py#L154-L158)

- 同一练习可反复提交反复加分（无 passed 唯一性约束），`total_exercises_completed` 按提交数而非去重练习数累计。
- admin "Regrade" 动作对已通过提交重跑 `grade()` → 二次加分、统计二次膨胀。
- 判分用硬编码 `hints_used * 2`，提示查看实际扣 `points_penalty`（样例数据为 3/5/7）。

**修复**：同一 (student, exercise) 通过后不再加分（只更新提交记录）；Regrade 改为只重算不重加分（或加 `select_for_update` 与幂等标记）；扣分统一按 `points_penalty` 累计，提示扣分用 `F()` 表达式防竞态。

### P1-5 随机种子污染全局状态

**位置**：[apps/examination/views.py:138-139](apps/examination/views.py#L138-L139)

`random.seed(student_exam.randomization_seed)` 直接污染进程全局 RNG：并发加载互相穿插 → 同一学生刷新题目顺序变化；并干扰其他 random 消费者（如 `StudentExam.save` 生成 seed）。

**修复**：用局部 `random.Random(seed)` 实例；或按 seed 对题目 id 排序（确定性洗牌）。

### P1-6 聊天历史取错端

**位置**：[apps/chat/views.py:91](apps/chat/views.py#L91)

注释说 "Last 20 messages"，实际 `order_by('created_at')[:20]` 取的是**最旧** 20 条——长对话时上下文陈旧、近期轮次丢失。

**修复**：`order_by('-created_at')[:20]` 后反转；或直接保留窗口截取。

### P1-7 生产部署配置坏

- [wsgi.py:14](config/wsgi.py#L14)/[asgi.py:14](config/asgi.py#L14) 指向 `config.settings`（包 `__init__` 为空文件）→ 未设环境变量时生产启动直接 ImproperlyConfigured。应指向 `config.settings.production`。
- `SECRET_KEY` 占位符、`DEBUG` 默认 True、`ALLOWED_HOSTS=['*']`（development.py）；production.py 应强制要求 `SECRET_KEY` 存在且非占位符。
- production 日志写 `BASE_DIR/logs/django.log`（[production.py:63](config/settings/production.py#L63)）但目录不存在、无人创建 → 首次写日志抛异常。加 `.gitkeep` 或启动时 `mkdir`。
- `LOGIN_REDIRECT_URL='/dashboard/'`（[base.py:141](config/settings/base.py#L141)）不是注册路由（实际是 `/accounts/dashboard/`）→ 登录后 404。
- development.py 的 `CORS_ALLOW_ALL_ORIGINS` 是死配置（未安装 django-cors-headers）；Sentry `send_default_pii=True` 建议关闭。

### P1-8 AI Agent 全是死代码 + 代理端点失效

- 4 个 Agent 类仅被 [verify_features.py](verify_features.py) 引用，无任何 view/命令/模型调用；输出无处落库。
- [base_agent.py:25](apps/ai_agents/base_agent.py#L25) 创建 client 时不传 `base_url` → 忽略 `ANTHROPIC_API_BASE_URL`。`.env` 配置的是第三方代理端点（api.jiekou.ai），Agent 一旦接线会打官方端点 → 鉴权必然失败。（`ChatAIService` 是正确的参考实现。）
- [base_agent.py:44](apps/ai_agents/base_agent.py#L44) `"temperature": temperature or self.temperature` —— `temperature=0` 被吞成 0.7；`generate_json` 的 ```json 围栏剥离只处理首尾，前有前言即解析失败，无重试。

**修复**：统一 Client 工厂（key + base_url + timeout）；`is not None` 判断参数；JSON 用正则提取第一个 `{...}` 块。

### P1-9 course_detail 模板 N+1

**位置**：[templates/learning/course_detail.html:83-110](templates/learning/course_detail.html#L83-L110)

每章 1 次 COUNT + 每课 1 次查询 + **每课重复加载全部进度行再逐条遍历**（O(L²) 行扫描）。

**修复**：视图 `prefetch_related('chapters__lessons', 'enrollments__lesson_progress')`，模板改字典查找。

---

## 🟡 P2 — 中优先级

### P2-1 测试为零（修复 P0 后第一优先补）

- 5 个 app 的 `tests.py` 全是空壳；无 pytest.ini/pyproject/conftest.py；pytest-django 无 `DJANGO_SETTINGS_MODULE` 配置，CLAUDE.md 中的 pytest 命令跑不起来。
- `test_executor.py`/`verify_features.py` 是 print 冒烟脚本，后者直接运行会因注释掉的 `django.setup()` 崩溃。
- **行动**：建立 pytest 配置 + 对每个 P0/P1 修复写回归测试（判分键名、权限、XSS 转义、重排事务）。

### P2-2 装而未用的依赖

Celery（无 celery.py 应用、无 tasks.py、无 `.delay()`）、DRF（零 serializer）、allauth、markdownx、CodeMirror（且 CDN 引入的是 v5 全局版脚本，v6 是 ESM-only，即使使用也无效）、HTMX（学习页未用）、Sentry 部分配置。`static/css/main.css` 404；`static/js/`、`static/css/` 空目录；`MARKDOWNX_MARKDOWN_EXTENSIONS` 孤配置。

**行动**：明确取舍——要么接线，要么从 requirements/模板中移除，避免误导。

### P2-3 死代码

- `Video` 模型（无任何读写方）、`CellVersion`（只写不读、无恢复端点、无限膨胀）、`rendered_html`（服务端渲染无人消费）、cell handler 的 `render()` 钩子、`video_generator` 整个 app（空文件）、`docker/`、`scripts/` 空目录、`apps/core/` 空壳。
- `AI_CACHE_ENABLED`/`AI_COST_LIMIT_DAILY` 设置无人读取。

### P2-4 异常信息泄露

所有 API 用宽泛 `except Exception as e: return JsonResponse({'error': str(e)}, 400)`：泄露内部异常/堆栈路径，且服务器错误误标 400。位置：[learning/views.py:209-210,261-262,287-288,326-327,352-353,382-383](apps/learning/views.py#L209-L210)、[training/views.py:138](apps/training/views.py#L138)、[chat/views.py:138-142](apps/chat/views.py#L138-L142)、[chat/ai_service.py:130-136](apps/chat/ai_service.py#L130-L136)。

**修复**：统一错误处理助手——`DEBUG` 下返回详情，生产返回通用消息 + 服务端记录日志。

### P2-5 中文标题 slug 冲突

`slugify('中文')` 得空串；第二篇中文标题课程/练习触发 unique 约束 IntegrityError → 500。位置：[learning/models.py:33-36](apps/learning/models.py#L33-L36)、[training/models.py:46-49](apps/training/models.py#L46-L49)。**修复**：空 slug 时用 `uuid4().hex[:8]` 兜底。

### P2-6 模板引用不存在的东西（静默失效）

- `lesson.get_previous`/`get_next`（[lesson_detail.html:323-350](templates/learning/lesson_detail.html#L323-L350)）→ 上下课导航永不渲染 → 补 `Lesson` 方法。
- `progress.completion_percentage`（[lesson_detail.html:202](templates/learning/lesson_detail.html#L202)）→ 进度条恒 0% → 补属性或改字段。
- `can_edit` 未传入 `CourseDetailView`（[course_detail.html:44](templates/learning/course_detail.html#L44)）→ 编辑课程按钮永不渲染。

### P2-7 其余 N+1

- 考试列表逐题 COUNT（[examination/views.py:35-41](apps/examination/views.py#L35-L41)）→ `annotate(Count(...))`。
- 考试答题页/成绩页逐题 `get_specific_question()`（每道题最多 4 次反向 FK 查询）→ prefetch 四个 OneToOne。
- `submit_exam` 答案循环缺 `select_related('question')`。
- 训练提交历史缺 `select_related('exercise')`（[training/views.py:181-184](apps/training/views.py#L181-L184)）。
- `ExerciseDetailView` 模板内 `hints.count`、`exam_interface` 重复调用 `get_total_points()`。

### P2-8 其他正确性/健壮性

- `video_cell` 校验 `source_type in ['manim']`，编辑器提交 `manim_generated`（[lesson_edit.html:349](templates/learning/lesson_edit.html#L349)）→ Manim 视频单元格保存必失败。统一枚举。
- `start_exam` 是状态变更型 GET；attempt_number 并发竞态（[examination/views.py:86-114](apps/examination/views.py#L86-L114)）。
- `Enrollment.completed_at` 在 100% 完成时从不设置（[learning/models.py:234-251](apps/learning/models.py#L234-L251)）。
- `track_cell_execution` 对 JSON 列表读-改-写竞态（[learning/models.py:286-291](apps/learning/models.py#L286-L291)）。
- 两个 notebook 导入命令逻辑重复（`import_notebook.py` vs `load_notebook_data.py`，含重复的 output 提取逻辑），且重跑 `import_notebook` 会因 order 重复炸 IntegrityError；`load_additional_content` 依赖前序命令且异常无友好提示。
- `create_cell` 接受任意 `cell_type` 字符串（choices 仅在表单层校验）→ 非法类型入库。加 `choices` 校验 + 未知 handler 拒绝。
- 考试 `save_answer` 不校验 answer_data 形状/大小；`submit_solution` 不限制代码长度。
- `ExerciseListView` 未要求登录（未登录可看全部练习列表）；训练 app 无发布/草稿概念。
- 训练练习按 `difficulty` 字母序排（advanced < beginner < intermediate）不构成难度递进。
- `Question.get_specific_question` 的 `getattr` 魔法 + 拼写错误（P0-10）说明该模式脆弱，建议改显式映射。
- 依赖过旧：Django 5.0（主流支持已结束）、anthropic==0.40.0（.env 里却用 claude-sonnet-4-5 模型名）。
- `TIME_ZONE='UTC'` 对中文教学应用不合适；UI 中英文混杂。
- `.env.example` 缺 `ANTHROPIC_BASE_URL`（代码在读取）；`.env.example` 的 PostgreSQL DB 配置被 development.py 忽略。

---

## 🟢 P3 — 功能补全与长期优化

0. **项目内 AI 工具调用能力（notebook-reader 接入）**：给 Django 应用内的 AI（聊天助手、后续的智能体）添加 Anthropic tool-use 能力，通过安全的服务端工具调用共享解析器 `apps/core/notebook_parser.py`：
   - 工具集：`list_notebooks`（列出 ClassLib 资料及结构）、`get_notebook_digest`（结构摘要）、`get_notebook_section`（读取某一节完整内容，含代码输出）
   - 要点：文件名白名单校验（防路径穿越）、结果长度截断、噪音单元格剔除、**不再把服务器绝对路径发给 LLM**（顺带修复 P0-7）、聊天历史取最近 20 条（顺带修复 P1-6）、异常信息按 DEBUG 开关脱敏（顺带修复 P2-4）
   - 智能体（Learning/Training/Examination Agent）接线后复用同一工具层
1. **代码执行真隔离（P0-1 的终极形态）**：subprocess + 资源限制起步，Docker 容器为终态（`docker/` 目录已预留）。
2. **AI Agent 接线**：
   - 教师端生成课程单元/练习/考题的管理命令或界面（对应 CLAUDE.md 承诺的 `generate_lesson` 等命令，目前全部不存在）；
   - 作文题 AI 评分（`ExaminationAgent.evaluate_essay_answer` 已写好，当前作文永远 `needs_review`，且 `submit_exam` 在作文未评分时就计算总分/通过与否）；
   - 统一走 `ANTHROPIC_API_BASE_URL`；接入缓存、token 统计、成本上限（设置已就位无人用）。
3. **异步化**：判分/聊天/AI 生成走 Celery（当前聊天同步阻塞、无流式、max_tokens 固定 2000）。
4. **证书生成**：weasyprint/reportlab 已在依赖、`Certificate` 模型已建（含验证码），只差 PDF 生成 + 校验端点；结果页"下载证书"按钮标注"开发中"。
5. **视频生成**：`video_generator` 从零实现（Manim 脚本校验 → Celery 渲染队列 → 存储），或明确砍掉精简依赖。
6. **部署**：Dockerfile + docker-compose、`logs/` 目录、`collectstatic`、Sentry 接线。
7. **体验**：编辑器保存/删除后 `location.reload()` 丢失滚动与撤销状态；拖拽换序需单独点"保存顺序"按钮；`alert()` 反馈；聊天历史无摘要/截断策略（超长对话 token 膨胀）。

---

## 建议实施顺序

```
第 1 阶段（安全止血，约 1-2 天）
  P0-1/2 执行器改造（先上 subprocess 隔离 + 超时，最快）
  P0-3  XSS：json_script 过滤器 + DOMPurify + 聊天界面转义
  P0-4/5 注册白名单 + validate_password + is_safe_url
  P0-6  删除硬编码密码
  P0-12 补权限检查（LessonDetail/Edit、ExamDetail、execute_cell）

第 2 阶段（修复核心功能，约 1 天）
  P0-8/9/10 判分键名 + truefalse 拼写
  P0-11 重排事务（先挪安全区再归位）
  P1-1 考试计时服务端校验
  P1-2 提交原子性
  P1-3 共享单元格改为会话级

第 3 阶段（回归测试，约 1-2 天）
  pytest 配置 + 对以上每个修复写回归测试 + 判分正确性测试

第 4 阶段（体验与性能）
  P1-9 / P2-7 N+1 修复、P1-6 聊天历史、P1-5 随机种子、
  P2-5 slug 冲突、P2-6 死模板引用清理

第 5 阶段（功能与部署）
  AI Agent 接线 → Celery 异步 → 证书 → 视频 → Docker 部署
```

## 备注

- 本审计为静态代码分析（防御性），未做实际渗透；`.env` 中的真实 API key 未在文档中复现，建议尽快轮换。
- 修复时同步更新 CLAUDE.md 中的"Current Implementation Status"，避免文档与代码继续脱节（现状：CLAUDE.md 声称的 RestrictedPython 沙箱、Celery 队列、Docker 隔离、pytest 工作流均与代码不符）。

## 进度记录

- **2026-09-16**：完成第 1 阶段（安全止血）+ 第 2 阶段（核心功能修复）主体
  - ✅ **P0-1/2 已修复**：执行器整体重写为 subprocess 隔离（`python -I` 子进程）+ 强制超时（kill）+ 严格 builtins 白名单（无 `__import__`/`open`/`eval`/`type`/`getattr`，白名单导入 math/random 等）+ AST 禁止下划线属性访问（封堵 `().__class__.__mro__` 类 gadget 链）；预留 RestrictedPython 可选加固层（装上即自动生效）。已验证：import os 被拒、gadget 链被拒、open 被拒、死循环 3 秒被杀、双测试模式正常。**遗留限制**：子进程仍是同一 OS 用户（Docker 为终态）
  - ✅ **P0-3 已修复**：`cells_json|safe` → `json_script`；新增 `escapejs_tick` 过滤器（转义反引号与 `${`）；marked 输出过 DOMPurify（cdnjs 3.1.6）；无 marked 时回退为纯文本转义（不再返回原始 markdown）；聊天界面 `innerHTML` 前统一 `escapeHtml()`（用户消息、AI 回复、推荐资源字段）
  - ✅ **P0-4 已修复**：注册强制 `user_type='student'`（前端移除 Instructor 选项 + 后端白名单）；接入 `validate_password()`（4 个配置好的 validator 生效）
  - ✅ **P0-5 已修复**：登录 `next` 参数经 `url_has_allowed_host_and_scheme` 校验；logout 改为 POST-only（base.html 改为表单按钮）
  - ✅ **P0-12 已修复**：`LessonDetailView` 过滤草稿（instructor/staff 可见）、`LessonEditView` 增加 `UserPassesTestMixin`、`execute_cell` 要求已选课（或 instructor/staff）、`ExamDetailView`/`TakeExamView` 过滤未发布考试、`CourseDetailView` 过滤未发布课程
  - ✅ **P0-8/9/10 已修复**：训练判分读取正确键（`test_results`/`passed_tests`/`total_tests`）+ `tests_total > 0` 守卫（不再 0==0 恒通过）；考试代码题读取 `passed_tests`（不再恒 0 分）；`truefalseavequestion` 拼写修复为显式 accessor 映射
  - ✅ **P0-11 已修复**：单元格插入/删除/重排全部改为「逐行更新」或「两阶段（先 +1,000,000 再归位）」，交换相邻单元格不再撞唯一约束；重排接口校验提交列表是完整排列；`create_cell` 校验 `cell_type` 合法
  - ✅ **P1-1 已修复**：`StudentExam.remaining_seconds()`/`is_timed_out()` 服务端计时（基于 start_time）；`save_answer` 超时拒绝；`take` 页时间来自服务端计算
  - ✅ **P1-2 已修复**：`submit_exam` 整体 `transaction.atomic()` + `select_for_update()`——双击不会重复判分、判分异常回滚不会把学生锁死；`student_profile` 缺失不再 500；`start_exam` 加行锁防 attempt_number 竞态
  - ✅ **P1-3 已修复**：`execute_cell` 不再把学生执行结果写入共享单元格（执行结果只回传前端）
  - ✅ **P1-5 已修复**：考试抽题改用局部 `random.Random(seed)`，不再污染进程全局随机状态
  - ✅ **P2-4 部分修复**：学习 app 全部 API 错误经 `_error_response` 统一脱敏（DEBUG 下才显示详情）+ 服务端日志记录
  - ✅ **回归测试**：新增 28 个测试（执行器 12、账户 4、学习 6、训练 3、聊天 3），加上聊天已有 11 个共 **39 个测试全部通过**；模板冒烟验证（json_script / DOMPurify / logout 表单渲染正常、403 权限生效）
- **2026-09-16**：完成项目内 AI 工具调用能力（P3-0）
  - ✅ 新增 `apps/chat/notebook_tools.py`：3 个 Anthropic tool-use 工具（列出资料/结构摘要/读取节内容），白名单校验文件名、结果截断、剔除噪音单元格
  - ✅ 聊天助手 `ChatAIService` 改为工具循环调用（最多 3 轮），系统提示词不再发送服务器绝对路径（**P0-7 部分修复**）
  - ✅ 聊天历史改为取最近 20 条（**P1-6 修复**）；AI 异常信息按 DEBUG 开关脱敏（**P2-4 部分修复**）
  - ✅ `apps/chat/tests.py` 从空壳改为真实测试（工具执行器 + mock 客户端工具循环）
- **2026-09-16**：完成 notebook 素材接入层
  - ✅ 新增共享解析器 `apps/core/notebook_parser.py`（纯标准库，章节/小节/噪音识别，digest/json/cells 输出，已用真实 notebook 端到端验证）
  - ✅ 新增 Claude Code skill `.claude/skills/notebook-reader/`（注意：`.claude/` 在 .gitignore 中，skill 目前仅本地生效，如需团队共享需调整 .gitignore）
  - ✅ **P0-6 已修复**：`import_notebook` / `load_notebook_data` 不再硬编码密码（改为 `--instructor-password`/`--password` 参数或随机生成并打印一次）
  - ✅ **P2-8 部分修复**：两个导入命令改为共用解析器，消除重复的输出提取/章节检测逻辑；`import_notebook` 重跑改为先清空再导入（修复重复 order 的 IntegrityError）；节检测从写死的 `1.x` 通用化为任意 `X.Y`；修复 `load_notebook_data` 的 `Classlib` 路径大小写（Windows 下碰巧可用，Linux 下会找不到文件）
