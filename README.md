# Python 教学平台（TeachingSpace）

面向 Python 编程教学的交互式学习系统：Jupyter 式笔记本课堂、自动判分训练、限时考试与证书，内置多模型 AI 助手与**知识点驱动的**内容生成能力。

当前版本：1.4.0（优化方案 v2 全部条目已完成归档，v3 路线图见 OPTIMIZATION_PLAN.md）

## 📚 文档

| 文档 | 读者 | 内容 |
|------|------|------|
| [用户说明手册](docs/USER_MANUAL.md) | 学生 / 教师 / 管理员 | 三大课堂使用、知识点库、AI 助手、证书、FAQ、故障排查 |
| [程序员说明手册](docs/DEVELOPER_MANUAL.md) | 开发与维护工程师 | 架构、环境搭建、配置全表、核心系统设计、测试、部署、开发规范 |
| [CLAUDE.md](CLAUDE.md) | AI 编程助手（Claude Code） | 项目上下文与工作约定 |
| [CHANGELOG.md](CHANGELOG.md) | 所有人 | 版本发布记录 |
| [OPTIMIZATION_PLAN.md](OPTIMIZATION_PLAN.md) | 开发工程师 | 优化路线图（v2 归档 + v3 规划、技术债登记与执行记录） |

## ✨ 功能总览

### 🎓 学习课堂
Jupyter 式笔记本界面：文本（Markdown + LaTeX）/ 代码（**真实 Jupyter 内核会话**——变量跨单元格持久、matplotlib 富输出、执行计数）/ 图片 / 视频四种单元格；拖拽排序、版本历史恢复；选课与进度跟踪（含学习时长心跳统计）；ClassLib notebook 一键导入；JSON / Markdown / ipynb / PDF 导出。

### 💪 训练课堂
编程练习自动判分（stdin/stdout 与函数式双模式）、渐进提示（积分惩罚）、防刷积分系统、提交历史、学习日历热力图、积分排行榜；教师可**手动创建 / 编辑 / 删除**练习（删除有提交历史保护），或 **AI 生成草稿 → 审阅 → 创建**（沙箱验证 + 反馈修复循环）、详情页 AI 修改、**按知识点生成**（批量逐知识点出题）。

### 📝 考试课堂
限时考试（**服务端强制计时**，刷新不清零）、四种题型（选择/判断/编程/简答）、答案自动保存、原子化交卷、AI 辅助评分、**教师评阅控制台**（简答打分自动重算总分）、题目**手动编辑**与 AI 修改、整卷代码题沙箱验证、题库 JSON 导入导出、自动组卷、**PDF 证书 + 在线验证码查询**。

### 🧭 知识点库（课程内容的结构化索引）
每门课程拥有自己的**知识点库**：教师一键 **AI 提炼**（接地链：单元文本 → ClassLib 素材 → 无素材时模型通识自主发挥）+ 人工审核增删改；习题与考题**绑定知识点**；考试关联课程后 **AI 生成整卷按知识点一题一知识点**——重复题从机理上消除。

### 💬 AI 学习助手与内容生成
- 聊天助手**查询平台真实课程资料作答**（Anthropic tool-use，兼容推理模型思考块），渐进式渲染回答，素材小节级推荐，超长对话自动摘要；
- **DeepSeek Harness 架构**：planner / worker / grader 角色路由 + 每角色回退链 + 推理模型兼容层（temperature 重试 / 思考块 / JSON 容错）+ **Skill 参数化旋钮**（AI_SKILL_PARAMS 三层配置）+ AI 审计看板（24h 失败率/成本）；
- AI 生成课程大纲 / 章节规划 / 单元内容（**异步任务 + 前端轮询 + 重试退避**）、练习、考题（草稿审核制）、Manim 视频脚本；成本跟踪与日限额。

### 🛡️ 安全
- 学生代码在**隔离沙箱**中执行：subprocess（默认）或 Docker 容器（网络禁用、资源受限、只读文件系统），builtins 白名单 + AST 私有属性拦截 + 可选 RestrictedPython + 强制超时；
- 注册越权防护、开放重定向修复、登录限流（5 次锁定）、接口级限流（提交/AI 生成/内核执行）、全链路 XSS 消毒（DOMPurify / json_script / 转义）、生产安全头（HSTS/SSL 重定向/CSRF trusted origins）。

## 🚀 快速开始

```bash
git clone https://github.com/besttea/TeachingSpace.git
cd TeachingSpace

python -m venv venv
venv\Scripts\activate            # Windows；Linux/macOS: source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env             # 按注释填写（AI 密钥等）
python manage.py migrate --settings=config.settings.development
python manage.py createsuperuser --settings=config.settings.development
python manage.py runserver --settings=config.settings.development
```

访问 http://localhost:8000 ｜ 管理后台 http://localhost:8000/admin

可选组件（详见程序员手册）：

```bash
# 完整 OS 级代码隔离（Docker 沙箱）
docker build -f docker/sandbox/Dockerfile -t teaching-space-sandbox .
# .env 中设 CODE_EXECUTION_BACKEND=docker

# 生产异步判分 / AI 生成（Celery + Redis）
celery -A config worker -l info

# 全栈编排（web + celery + redis + postgres）
docker compose up -d
```

## 🧪 测试与质量

```bash
pytest -q                          # 363 个测试：沙箱逃逸、判分、权限、XSS、AI 工具循环、知识点管道、证书、真实 Manim 渲染（slow 标记）等
ruff check apps config             # lint（CI 强制）
pytest -m "not slow" --cov=apps/code_runner --cov=apps/learning \
    --cov=apps/training --cov=apps/examination   # 核心模块覆盖率（CI ≥80% 门禁，当前 85%）
```

CI（GitHub Actions）：fast job（ruff + 快速测试 + 覆盖率门禁 + pip-audit）+ slow job（真实 Manim 渲染）。本地提交前可用 `pre-commit`（.pre-commit-config.yaml）。

## 🛠 技术栈

Django 5 · Bootstrap 5 · Alpine.js · Marked.js + DOMPurify · KaTeX · SortableJS ｜ SQLite/PostgreSQL ｜ Anthropic SDK（多 provider：Claude / DeepSeek / 代理）· Celery + Redis ｜ Manim + FFmpeg ｜ reportlab（中文证书/导出）｜ ipykernel（真实内核）｜ Docker（沙箱/内核/应用镜像）｜ pytest + ruff + pytest-cov + GitHub Actions

## 📁 结构速览

```
apps/accounts      认证与角色          apps/chat          AI 助手（工具调用 + ClassLib 扫描）
apps/learning      学习课堂 + 知识点库   apps/ai_agents     AI Harness + Skills + 旋钮配置 + 审计
apps/training      训练课堂            apps/code_runner   沙箱执行（subprocess/Docker）
apps/examination   考试课堂 + 证书     apps/video_generator  Manim 校验/渲染/缩略图
apps/core          共享工具（解析器/限流/中间件/缓存）
config/            设置/路由/Celery    ClassLib/          教学素材 notebook（<分类>/<notebook>.ipynb）
docker/            沙箱/内核/应用镜像   docs/              本手册文档
scripts/           部署与备份脚本
```

## 路线图

- v3 优化路线图（知识点生态深化、学习分析、题目质量校准、通知系统等）见 [OPTIMIZATION_PLAN.md](OPTIMIZATION_PLAN.md)

## 许可证与致谢

MIT License。UI 组件来自 Bootstrap；Markdown 渲染 Marked.js；数学渲染 KaTeX；开发辅助来自 Claude AI。

- GitHub: [@besttea](https://github.com/besttea)
- Email: best-tea@163.com
