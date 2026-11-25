# 个人工作台（Flask + SQLite）

单机版个人知识库与运维记录工具，覆盖工作记录、学习笔记、待办、日记、习惯打卡、Bug 追踪、命令速查、崩溃分析、错误码速查、打印日志分析、驱动/协议/机型管理、发版记录等场景。

- 后端：Flask 3 + SQLite，无外部数据库依赖
- 前端：服务端渲染 Jinja2 模板，纯 CSS 深色霓虹主题，**不依赖任何 CDN 与前端框架**
- 部署：Linux 用 gunicorn，Windows 用 waitress，配置自动适配
- 数据：单文件 SQLite，支持全库 JSON 导入导出与回收站

---

## 一、快速开始

### 1. 环境要求

| 项目 | 版本 |
|---|---|
| Python | 3.9+（实测 3.11.6） |
| Flask | 3.0 ~ 3.x（实测 3.1.3） |
| SQLite | Python 内置（实测 3.42.0） |

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

`requirements.txt` 内容与说明：

```
Flask>=3.0,<4.0
Markdown>=3.4,<4.0
requests>=2.28,<3.0                                    # 仅 verify_app.py --http 体检用，可选
gunicorn>=21.0; platform_system != "Windows"           # Linux/macOS 生产服务器
waitress>=3.0; platform_system == "Windows"            # Windows 生产服务器
```

### 3. 初始化登录口令

首次部署必须设置口令，否则无法登录：

```bash
# 方式一：指定口令
python3 app.py --set-password 你的密码

# 方式二：随机生成（会打印一次，请自行保存）
python3 app.py --set-password
```

口令以 SHA-256 哈希写入 `auth.json`，明文不落盘。同一个文件里还会自动生成：

| 字段 | 用途 |
|---|---|
| `password_hash` | 登录口令的 SHA-256 |
| `api_token` | 40 字符 API 令牌，供脚本与接口调用 |
| `secret_key` | 会话签名密钥，首次启动自动生成并持久化 |
| `notify_webhook` / `notify_enabled` | Webhook 通知配置 |

> `auth.json` 权限为 `600`，且已在 `.gitignore` 中排除，**禁止提交到仓库**。

### 4. 启动

```bash
# 开发/单机运行（自动建表）
python3 app.py

# 访问
http://127.0.0.1:8000
```

`app.py` 直接运行时会按平台自动选择服务器：

- **Windows**：优先用 waitress（`threads=8`），未安装则回退 Flask 开发服务器
- **Linux/macOS**：用 Flask 内置服务器；生产环境请改用 gunicorn（见下节）

---

## 二、路径与配置

### 零配置路径探测

所有数据路径由 `shared.py` 的 `_auto_path()` 自动决定，**换机器直接能跑，无需设置环境变量**。查找顺序：

```
项目目录内  →  上一级目录  →  项目目录内新建
```

上一级目录用于兼容旧布局（数据库放在 `/root/workbench.db`、快照放在 `/root/db_backups`），命中后自动沿用，无需手工迁移。

| 变量 | 默认位置 | 说明 |
|---|---|---|
| `DB_PATH` | `workbench.db` | SQLite 主库 |
| `BACKUP_DIR` | `backups/` | JSON 导出归档 |
| `SNAPSHOT_DIR` | `db_backups/` | 导入前的数据库快照 |
| `IMPORT_TMP_DIR` | `tmp_import/` | 按表导入的预演临时文件 |
| `AUTH_FILE` | `auth.json` | 固定位于项目目录内 |

### 可选环境变量

| 变量 | 作用 |
|---|---|
| `WORKBENCH_LOG_DIR` | gunicorn 访问/错误日志目录，默认项目目录 |
| `WORKBENCH_BASE` | `verify_app.py` 的扫描根目录，默认脚本所在目录 |

### 数据库特性

连接建立时自动设置：

```sql
PRAGMA busy_timeout = 5000;   -- 瞬时写冲突不直接报错
PRAGMA journal_mode = WAL;    -- 提升读写并发
PRAGMA synchronous = NORMAL;
```

---

## 三、生产部署

### 1. Linux / systemd

创建 `/etc/systemd/system/workbench.service`：

```ini
[Unit]
Description=Personal Workbench (Flask + Gunicorn)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/workbench
ExecStartPre=/usr/bin/python3 -c "import app; app.init_db()"
ExecStart=/usr/local/bin/gunicorn -c /root/workbench/gunicorn.conf.py app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启用：

```bash
systemctl daemon-reload
systemctl enable --now workbench
systemctl status workbench --no-pager
```

> 查看单元配置时**务必加 `--no-pager`**，否则会进入 less 分页并卡在 `(END)`，表现为终端无响应（此时按 `q` 或发 `Ctrl+C` 退出）。

### 2. gunicorn 配置

`gunicorn.conf.py` 关键项：

```python
bind     = "0.0.0.0:8000"
workers  = 2
threads  = 2
timeout  = 60
loglevel = "info"
proc_name = "workbench"
```

日志路径默认落在项目目录，可用 `WORKBENCH_LOG_DIR` 改到别处。

> **多 worker 与会话**：会话密钥持久化在 `auth.json` 的 `secret_key` 字段，两个 worker 共用同一密钥，重启后已登录会话依然有效。首次启动会加文件锁写入，避免多进程同时生成不同密钥。

### 3. Windows

```bat
pip install -r requirements.txt
python app.py --set-password 你的密码
python app.py
```

自动使用 waitress 监听 `0.0.0.0:8000`。也可注册为任务计划程序实现开机自启。

### 4. 反向代理（可选）

置于 Nginx 之后时，把 `proxy_pass http://127.0.0.1:8000;` 指向本服务即可，注意透传 `Host` 与 `X-Forwarded-For` 头，便于日志定位来源。

---

## 四、定时任务

两个脚本均为跨平台纯 Python 实现（替代原先的 `.sh`），路径自动探测，Linux timer 与 Windows 任务计划程序都能直接调用。

### 1. 每日数据备份 `backup.py`

```bash
python3 backup.py
```

- 调用 `/api/export` 导出全库 JSON，按时间戳归档到 `BACKUP_DIR`
- 自动保留最近 **30** 份，更早的滚动删除
- 依赖 `auth.json` 中的 `api_token` 鉴权

Linux timer 示例（每日 03:20，随机延迟 5 分钟内）：

```ini
[Timer]
OnCalendar=*-*-* 03:20:00
RandomizedDelaySec=300
Persistent=true
```

### 2. 打印耗材巡检 `printer_probe.py`

```bash
python3 printer_probe.py
```

- 调用 `/api/printers/probe_all`，通过 SNMP 读取耗材余量与总页数
- 库中没有配置 IP 的打印机时直接跳过并打印 `SKIP: no printer with ip configured`
- 耗材不足由服务端触发 Webhook 通知

Linux timer 示例（每小时，随机延迟 2 分钟）：

```ini
[Timer]
OnCalendar=hourly
RandomizedDelaySec=120
Persistent=true
```

启用：

```bash
systemctl enable --now workbench-backup.timer
systemctl enable --now workbench-printer-probe.timer
systemctl list-timers --no-pager
```

---

## 五、功能模块

| 分类 | 页面 | 说明 |
|---|---|---|
| 通用 | `/` `/work` `/study` `/todo` `/diary` `/habit` | 概览、工作记录、学习笔记（间隔复习）、待办、日记、习惯打卡 |
| 知识 | `/bugs` `/roadmap` `/snippets` `/compile_errors` `/perf` | Bug 追踪、学习路线、代码片段、编译错误、性能优化 |
| 速查 | `/commands` `/error_codes` `/log_analysis` `/crashes` | 命令速查、错误码、日志模式、崩溃分析 |
| 打印 | `/printers` `/drivers` `/protocols` `/test_matrix` | 机型库、驱动、协议、测试矩阵（SNMP 巡检） |
| 阅读 | `/books` `/interview` `/releases` | 读书进度、面试题（复习曲线）、发版记录 |
| 统计 | `/analytics` `/report/weekly` `/review/weekly` | 数据统计、周报、每周回顾 |
| 管理 | `/history` `/recycle` `/settings` `/import` `/search` | 变更历史、回收站、设置、数据导入、全局搜索 |
| 运维 | `/status` | 服务健康与数据库状态看板 |

### 三个联动特性

**1. 命令使用频次**

命令列表支持 `sort=hot` 按使用次数排序，页面顶部聚合「常用命令」前 6 条。复制命令时异步上报计数：

```
POST /api/commands/<id>/use   →  use_count + 1，写入 last_used
```

**2. 错误码三表关联**

`crashes` 与 `log_patterns` 均带 `error_code_id`，与 `error_codes` 双向展示：崩溃/日志页显示错误码徽章，错误码页显示「N 条崩溃 / N 条日志」并可跳转。

**3. 崩溃日志自动解析**

崩溃页支持粘贴原始日志自动提取结构化字段：

```
POST /api/crashes/parse   { "raw": "...日志全文..." }
```

识别能力：

- 信号：`SIGSEGV`/`SIGABRT`/`SIGBUS`/`SIGFPE`/`SIGILL`，兼容 `Segmentation fault`、`Aborted`、`core dumped`、`EXCEPTION_ACCESS_VIOLATION`
- 模块：优先取出现次数最多的源文件名，否则取顶层帧前缀
- 堆栈帧：解析 `#N 0x... in func` 格式，保留前 8 帧
- 错误码候选：`SC542`、`49.4C02`、`E123`、`ERR1` 等格式
- 根因提示：空指针、数组越界、堆损坏、栈溢出、除零、断言失败、依赖缺失、竞态死锁

---

## 六、API 与鉴权

### 登录态

浏览器会话基于签名 Cookie。会话密钥取自 `auth.json` 的 `secret_key`，多 worker 共享。

### 脚本调用

非浏览器场景使用 API Token，通过请求头传递：

```bash
TOKEN=$(python3 -c "import json;print(json.load(open('auth.json'))['api_token'])")

curl -H "X-API-Token: $TOKEN" http://127.0.0.1:8000/api/stats
curl -H "X-API-Token: $TOKEN" -X POST http://127.0.0.1:8000/api/commands/1/use
```

鉴权逻辑：`session` 已登录 **或** `X-API-Token` 匹配（常量时间比较）即放行；`/api/` 路径未授权返回 `401 JSON`，普通页面重定向到 `/login`。

### 令牌轮换

设置页提供「重新生成 Token」按钮，对应 `POST /api/settings/token/regenerate`。轮换后需同步更新所有调用方。

---

## 七、数据备份与恢复

| 操作 | 入口 | 说明 |
|---|---|---|
| 全库导出 | `GET /api/export` | 输出 JSON，含 28 张表 |
| 按表导入 | `/import` | 先预演比对差异，确认后写入 |
| 导入快照 | `SNAPSHOT_DIR` | 每次导入前自动快照，可回滚 |
| 删除留档 | `/recycle` | 删除进入回收站，支持还原与彻底清除 |
| 变更历史 | `/history` | 记录增删改操作 |

导入约束：

- `IMPORT_TABLES` 定义 28 张表的可导入字段白名单
- 预演临时文件存活 `IMPORT_TTL_SECONDS = 3600` 秒
- 导入前自动快照到 `SNAPSHOT_DIR`

---

## 八、开发与验证

### 代码结构

| 文件 | 职责 |
|---|---|
| `app.py` | 主应用：建表 SCHEMA、通用模块路由、错误码/日志分析、导入导出、会话密钥 |
| `shared.py` | 共享层：路径探测、数据库连接、鉴权装饰器、Webhook 通知 |
| `knowledge.py` | 知识库蓝图：Bug、路线、片段、编译错误、性能、命令、崩溃、读书、面试、发版 |
| `admin.py` | 管理蓝图：变更历史、回收站、设置 |
| `printer.py` | 打印蓝图：机型、驱动、协议、测试矩阵、SNMP 探针 |
| `backup.py` | 每日 JSON 备份脚本 |
| `printer_probe.py` | 打印耗材巡检脚本 |
| `verify_app.py` | 静态体检与 HTTP 回归脚本 |
| `gunicorn.conf.py` | 生产服务器配置 |
| `templates/` | 36 个 Jinja2 模板 |
| `static/style.css` | 全站样式（CSS 变量驱动的深色主题，含亮色覆盖） |

### 自动化体检

```bash
# 仅静态检查（模板端点、未定义全局名、路由统计）
python3 verify_app.py

# 额外跑一遍页面 HTTP 回归
python3 verify_app.py --http
```

预期输出：

```
模板端点有效性      OK
模块未定义全局名    OK（5 个模块）
路由统计            110 条（app 56 / knowledge 37 / admin 12 / printer 5）
页面回归            34 个页面全部 200
结果: ALL PASSED
```

新增路由后请重跑此脚本，比对路由数是否符合预期，避免拆分蓝图时意外丢失。

### 主题切换

深色为默认主题。右上角图标可切到亮色，选择记录在 `localStorage['wb-theme']`，刷新后保持。全站配色由 `style.css` 顶部的 CSS 变量驱动，改 `--accent` 系列即可整体换色。

---

## 九、发布流程

```bash
# 1. 本地验证
git status --porcelain
python3 verify_app.py --http

# 2. 提交
git add -A
git commit -m "feat: 变更说明"

# 3. 推送
git push origin master
```

约定：

- 提交前必须 `verify_app.py --http` 全绿
- **不要提交** `auth.json`、`INITIAL_PASSWORD.txt`、`*.log`、`__pycache__/`、`*.pyc`（已在 `.gitignore`）
- 数据库默认在仓库外（如 `/root/workbench.db`），若移入项目目录同样需忽略
- 网络不稳时推送可放到后台并轮询日志：

```bash
nohup git push origin master > /tmp/push.log 2>&1 &
tail -f /tmp/push.log
```

### 升级部署

```bash
cd /root/workbench
git pull origin master
pip install -r requirements.txt      # 依赖有变更时
systemctl restart workbench          # 模板改动必须重启（Jinja 缓存）
systemctl is-active workbench
python3 verify_app.py --http
```

---

## 十、运维注意事项

1. **`systemctl show` / `status` 必须加 `--no-pager`**，否则卡在 less 分页。
2. **模板改动后必须重启服务**，Jinja 模板有缓存，否则页面不更新。
3. **`/login` 无失败次数限制**，公网暴露前请确保来源 IP 受限，或自行增加限流。
4. **密码重置**：忘记口令时执行 `python3 app.py --set-password 新口令`，无需停服。
5. **数据库备份**：除每日 JSON 备份外，重要变更前建议 `cp workbench.db db_backups/pre_xxx.db`。
6. **WAL 文件**：`workbench.db-wal` 与 `-shm` 属正常伴随文件，复制数据库时三者一并处理，或先执行 `PRAGMA wal_checkpoint(TRUNCATE)`。
7. **敏感信息**：`auth.json` 含 `api_token` 与 `secret_key`，`INITIAL_PASSWORD.txt` 含明文初始口令，均不可外泄或提交仓库。

---

## 十一、常见问题

**Q：访问页面一直跳回登录页？**

A：确认 `auth.json` 中有 `secret_key` 字段且权限正常。若为旧版本升级且产生过多个不同密钥，删除该字段后重启一次即可重新生成统一密钥。

**Q：接口返回 `{"ok": false, "error": "unauthorized"}`？**

A：脚本调用需要 `X-API-Token` 请求头，值取 `auth.json` 的 `api_token`。

**Q：`database is locked`？**

A：已启用 WAL 与 5 秒 `busy_timeout`。若持续出现，检查是否有长事务或其他进程独占数据库文件。

**Q：模板改了没生效？**

A：`systemctl restart workbench`。服务运行中不会自动重载模板。

**Q：Windows 上 gunicorn 装不上？**

A：正常，`requirements.txt` 已用环境标记跳过，Windows 使用 waitress。

---

## 许可证

个人自用项目，未声明开源许可证。如需引用请先联系作者。
