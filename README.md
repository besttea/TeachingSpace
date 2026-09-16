# Python 教学平台（TeachingSpace）

面向 Python 编程教学的交互式学习系统：Jupyter 式笔记本课堂、自动判分训练、限时考试与证书，内置多模型 AI 助手与内容生成能力。

当前版本：1.2.0

## 📚 文档

| 文档 | 读者 | 内容 |
|------|------|------|
| [用户说明手册](docs/USER_MANUAL.md) | 学生 / 教师 / 管理员 | 三大课堂使用、AI 助手、证书、FAQ、故障排查 |
| [程序员说明手册](docs/DEVELOPER_MANUAL.md) | 开发与维护工程师 | 架构、环境搭建、配置全表、核心系统设计、测试、部署、开发规范 |
| [CLAUDE.md](CLAUDE.md) | AI 编程助手（Claude Code） | 项目上下文与工作约定 |
| [CHANGELOG.md](CHANGELOG.md) | 所有人 | 版本发布记录 |
| [OPTIMIZATION_PLAN.md](OPTIMIZATION_PLAN.md) | 开发工程师 | 安全审计与优化方案（含进度记录） |

## ✨ 功能总览

### 🎓 学习课堂

Jupyter 式笔记本界面：文本（Markdown + LaTeX）/ 代码（沙箱执行）/ 图片 / 视频四种单元格；拖拽排序、版本快照；选课与学习进度跟踪；ClassLib notebook 一键导入。

### 💪 训练课堂

编程练习自动判分（stdin/stdout 与函数式双模式）、渐进提示（积分惩罚）、防刷积分系统、提交历史。

### 📝 考试课堂

限时考试（**服务端强制计时**，刷新不清零）、四种题型（选择/判断/编程/简答）、答案自动保存、原子化交卷、AI 辅助评分、**PDF 证书 + 在线验证码查询**。

### 💬 AI 学习助手与内容生成

- 聊天助手可**查询平台真实课程资料**作答（Anthropic tool-use），并推荐学习资源；
- 多模型支持：Claude / DeepSeek / 自定义代理一键切换（`AI_PROVIDER`）；
- AI 生成课程单元 / 练习 / 考题（草稿审核制）/ Manim 视频脚本，含成本跟踪与日限额。

### 🛡️ 安全

- 学生代码在**隔离沙箱**中执行：subprocess（默认）或 Docker 容器（网络禁用、资源受限、只读文件系统），双重防护（builtins 白名单 + AST 私有属性拦截 + 可选 RestrictedPython），强制超时；
- 注册越权防护、开放重定向修复、全链路 XSS 消毒（DOMPurify / json_script / 转义）。

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

# 生产异步判分（Celery + Redis）
celery -A config worker -l info
```

## 🧪 测试

```bash
python -m pytest    # 69 个测试：沙箱逃逸、判分、权限、XSS、AI 工具循环、证书、真实 Manim 渲染等
```

## 🛠 技术栈

Django 5.2 · Bootstrap 5 · Alpine.js · Marked.js + DOMPurify · KaTeX · SortableJS ｜ SQLite/PostgreSQL ｜ Anthropic SDK（多 provider）· Celery + Redis ｜ Manim + FFmpeg ｜ reportlab（中文证书）｜ Docker（沙箱）｜ pytest

## 📁 结构速览

```
apps/accounts      认证与角色          apps/chat          AI 助手（工具调用）
apps/learning      学习课堂            apps/ai_agents     AI 智能体 + 成本跟踪
apps/training      训练课堂            apps/code_runner   沙箱执行（subprocess/Docker）
apps/examination   考试课堂 + 证书     apps/video_generator  Manim 校验与渲染
apps/core          共享解析器          ClassLib/          教学素材 notebook
config/            设置/路由/Celery    docs/              本手册文档
```

## 路线图

- 🚧 单元格版本恢复前端 UI（后端 API 已就绪）
- 🚧 聊天流式响应
- 📋 视频缩略图与 CDN 存档
- 📋 讨论区、排行榜等社区功能

## 许可证与致谢

MIT License。UI 组件来自 Bootstrap；Markdown 渲染 Marked.js；数学渲染 KaTeX；开发辅助来自 Claude AI。

- GitHub: [@besttea](https://github.com/besttea)
- Email: best-tea@163.com
