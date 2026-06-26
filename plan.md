# 课程论文提交系统 - 实现计划

**Goal:** 为25人班级搭建一个课程论文提交与管理网站，同学可上传论文，学委可在后台查看统计、未交名单、下载论文。
**Architecture:** Python Flask + SQLite 单文件应用，前后端不分离，模板渲染HTML。
**Tech Stack:** Python 3.11, Flask, SQLite, Jinja2, Bootstrap 5 (CDN).

---

## Task 1: 项目初始化与依赖

**Objective:** 创建项目结构，安装依赖。

**Files:**
- Create: `app.py` (主应用)
- Create: `requirements.txt`
- Create: `templates/` 目录
- Create: `static/` 目录
- Create: `uploads/` 目录

**Step 1:** 写 `requirements.txt`
```
Flask==3.0.0
Werkzeug==3.0.1
```

**Step 2:** 安装依赖
```bash
pip install -r requirements.txt
```

**Step 3:** 验证安装
```bash
python -c "import flask; print(flask.__version__)"
```

---

## Task 2: 数据库模型与初始化

**Objective:** 创建SQLite数据库和表结构。

**Files:**
- Modify: `app.py` (添加数据库初始化代码)

**Step 1:** 在 `app.py` 顶部添加数据库初始化函数

**Step 2:** 创建表：
- `courses`: id, name, deadline (TEXT)
- `students`: id, name, student_id (TEXT, unique)
- `submissions`: id, student_id, course_id, title, filename, submit_time

**Step 3:** 初始化5门课程和25名学生数据

**Step 4:** 运行 `python app.py` 验证数据库创建成功

---

## Task 3: 同学上传页面

**Objective:** 创建论文上传表单页面。

**Files:**
- Create: `templates/upload.html`
- Modify: `app.py` (添加 `/` 路由)

**Step 1:** 创建 `upload.html` 模板：
- Bootstrap 5 表单
- 字段：姓名、学号、课程（下拉）、论文标题、文件上传
- 文件限制：.pdf, .doc, .docx, .zip, .rar
- 提交成功提示

**Step 2:** 添加 `GET /` 路由渲染表单

**Step 3:** 添加 `POST /submit` 路由处理上传：
- 验证姓名学号是否在学生表
- 验证是否重复提交（同一学生+同一课程）
- 保存文件到 `uploads/course_name/`
- 插入提交记录到数据库
- 返回成功页面

**Step 4:** 运行测试上传

---

## Task 4: 管理后台登录

**Objective:** 添加简单的密码保护。

**Files:**
- Create: `templates/login.html`
- Modify: `app.py` (添加 `/admin` 和 `/admin/login` 路由)

**Step 1:** 创建 `login.html` 模板

**Step 2:** 添加 `GET /admin` 路由：检查session，未登录跳登录页

**Step 3:** 添加 `POST /admin/login` 路由：验证密码（硬编码或环境变量）

**Step 4:** 添加 `GET /admin/logout` 路由

**Step 5:** 测试登录流程

---

## Task 5: 管理后台控制台

**Objective:** 创建学委管理主页面。

**Files:**
- Create: `templates/dashboard.html`
- Modify: `app.py` (添加 `/admin/dashboard` 路由)

**Step 1:** 创建 `dashboard.html`：
- 顶部：5门课程卡片（课程名、截止时间、已交人数/总人数）
- 中间：课程选择下拉
- 下方：提交详情表格（姓名、学号、论文标题、提交时间、文件链接）
- 未交名单区域（可复制）

**Step 2:** 添加路由查询数据：
- 每门课的提交统计
- 已交学生列表
- 未交学生列表（全班减去已交）

**Step 3:** 测试数据展示

---

## Task 6: 论文打包下载

**Objective:** 一键下载某课程所有论文。

**Files:**
- Modify: `app.py` (添加 `/admin/download/<course_id>` 路由)

**Step 1:** 添加路由：
- 查询该课程所有提交记录
- 打包 `uploads/course_name/` 目录为 zip
- 返回 zip 文件下载

**Step 2:** 在 `dashboard.html` 添加下载按钮

**Step 3:** 测试下载功能

---

## Task 7: 样式美化

**Objective:** 让页面看起来专业整洁。

**Files:**
- Create: `static/style.css`
- Modify: `templates/upload.html`
- Modify: `templates/login.html`
- Modify: `templates/dashboard.html`

**Step 1:** 添加自定义CSS：
- 简洁的白色背景
- 卡片式布局
- 状态颜色（已交绿色、未交红色）
- 响应式设计

**Step 2:** 测试各页面显示效果

---

## Task 8: 部署准备

**Objective:** 配置生产环境运行。

**Files:**
- Modify: `app.py` (添加 `if __name__ == '__main__'` 配置)
- Create: `Procfile` (Render/Railway部署用)
- Create: `.gitignore`

**Step 1:** 配置生产环境变量（SECRET_KEY, ADMIN_PASSWORD）

**Step 2:** 创建 `Procfile`:
```
web: gunicorn app:app
```

**Step 3:** 更新 `requirements.txt` 添加 gunicorn

**Step 4:** 创建 `.gitignore` 排除 uploads/ 和 __pycache__/

**Step 5:** 本地测试生产模式运行

---

## 验证清单

- [ ] 同学能成功上传论文
- [ ] 重复提交同一课程被阻止
- [ ] 管理后台能登录
- [ ] 控制台显示正确统计
- [ ] 未交名单准确
- [ ] 能打包下载论文
- [ ] 页面样式整洁

---

**Ready to execute using subagent-driven-development.**
