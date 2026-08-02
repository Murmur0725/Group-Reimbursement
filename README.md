# Notion 报销工具

从 Notion 报销数据库批量处理附件，并提供本地 Web 后台做同步、查询与操作。

- **CLI**：直连 Notion，适合一次性批处理（PDF / 发票 / 下载）
- **Web**：先同步到本地 SQLite，再在页面上查询、改状态、批量处理

---

## 项目框架

```text
CLI / 浏览器
    │
    ▼
app/main.py                 # 唯一入口：菜单、CLI 子命令、启动 Web
    │
    ├─ services/cli_batch   # CLI：Notion 直连批处理（不依赖本地 DB）
    │
    └─ web/app.py           # FastAPI 装配
           │
           ├─ routes_*      # 页面与表单
           └─ services/*    # 同步 / 查询 / 状态回写 / Web 批处理
                  │
                  ├─ db/    # SQLite
                  └─ 共享工具：notion_client / downloader / pdf_service / invoice_*
```

两条业务轨道：

| 轨道 | 数据源 | 入口 | 典型用途 |
| --- | --- | --- | --- |
| CLI | Notion 实时查询 | `python -m app.main pdf\|fapiao\|download` | 按状态批量下载、出 PDF、整理发票 |
| Web | SQLite（先 sync） | `python -m app.main web` → `http://127.0.0.1:8000` | 看板、清单搜索、状态回写、后台批处理 |

### 目录说明

```text
Group-Reimbursement/
├─ app/
│  ├─ main.py                      # 入口：交互菜单 / 子命令 / 启动 Web
│  ├─ config.py                    # .env 与路径配置
│  ├─ logging_config.py
│  ├─ notion_client.py             # Notion API 封装
│  ├─ downloader.py                # 附件下载
│  ├─ pdf_service.py               # PDF 生成 / 合并 / 文件名
│  ├─ invoice_parser.py            # 发票文本解析
│  ├─ invoice_to_delivery.py       # 发货单 Excel
│  ├─ cleanup.py                   # 清理 downloads / output_pdfs / data
│  ├─ db/                          # SQLite
│  │  ├─ database.py
│  │  └─ models.py                 # 记录 / 版本 / 状态事件 / 同步 / 附件
│  ├─ schemas/
│  │  └─ reimbursement.py          # 同步用 DTO
│  ├─ services/
│  │  ├─ cli_batch.py              # CLI Notion 直连批处理
│  │  ├─ notion_sync.py            # Notion → SQLite 全量同步
│  │  ├─ record_domain.py          # hash / version / status event 原语
│  │  ├─ status_update.py          # 状态回写 Notion + 本地审计
│  │  ├─ processing.py             # Web 侧 PDF / 发票 / 下载编排
│  │  ├─ batch_jobs.py             # 后台异步批任务（复用 processing）
│  │  ├─ record_queries.py         # 清单筛选与金额搜索
│  │  ├─ dashboard.py              # 看板统计
│  │  ├─ notion_archive.py         # 可选 done 归档
│  │  └─ scheduler.py              # 可选定时同步
│  └─ web/
│     ├─ app.py                    # FastAPI 应用
│     ├─ routes_dashboard.py       # /
│     ├─ routes_records.py         # /records
│     ├─ routes_sync.py            # /sync
│     ├─ routes_actions.py         # 状态更新 / 批处理动作
│     ├─ routes_downloads.py       # 本地文件下载
│     ├─ templates/
│     └─ static/
├─ data/                           # 运行时数据（勿提交）
│  ├─ downloads/
│  ├─ output_pdfs/
│  ├─ fapiao/
│  └─ reimbursement.db
├─ docs/                           # 本地规划草稿（已加入 .gitignore）
├─ scripts/clear_data.py
├─ tests/
├─ .env.example
├─ README.md
├─ pyproject.toml
└─ uv.lock
```

Notion 常见字段：`名称`、`状态`、`文件和媒体`、`编号`、`金额`、`申请人`、`报销给谁`、`备注`。

---

## 1. 安装依赖

```bash
uv sync
```

需要 Python 3.12+，以及可访问外网（Notion API、附件下载）。

---

## 2. 配置 Notion Integration

1. 打开 [Notion My Integrations](https://www.notion.so/my-integrations)
2. 创建 Integration，复制 **Internal Integration Secret**（`ntn_` 开头）
3. 打开报销数据库页面 → `...` → **Connections** → 连接该 Integration

---

## 3. 获取数据库 ID

打开数据库「在新页面中打开」后，地址类似：

```text
https://www.notion.so/xxxxxx/表格名称-30399adbdb7b80fe9af4c9eb0dadad40
```

最后 32 位即 Database ID，写入 `.env` 的 `NOTION_PAGE_ID`。

---

## 4. 配置 `.env`

复制 `.env.example` 为 `.env`：

```ini
NOTION_TOKEN=ntn_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NOTION_PAGE_ID=30399adbdb7b80fe9af4c9eb0dadad40

STATUS_PROPERTY_NAME=状态
NUMBER_PROPERTY_NAME=编号
NAME_PROPERTY_NAME=名称
AMOUNT_PROPERTY_NAME=金额
APPLICANT_PROPERTY_NAME=申请人
REIMBURSE_TO_PROPERTY_NAME=报销给谁
REMARK_PROPERTY_NAME=备注
FILES_PROPERTY_NAME=文件和媒体

# CLI：只处理该状态
STATUS_TO_PROCESS=1-发票+购买记录
# CLI pdf 模式处理完成后写入的状态
STATUS_PROCESSED=2-已处理

MODE=pdf
FAPIAO_DIR=data/fapiao

# 可选
# ENABLE_BACKEND_SCHEDULER=0
# ENABLE_NOTION_DONE_ARCHIVE=0
```

注意：属性名、状态选项名必须与 Notion 完全一致；不要提交 `.env`。

---

## 5. 启动 Web 后台（推荐）

```bash
uv run python -m app.main web
```

等价：

```bash
uv run python -m app.main server
# 或
.venv/bin/python -m uvicorn app.web.app:app --host 127.0.0.1 --port 8000
```

浏览器打开：http://127.0.0.1:8000

| 路径 | 功能 |
| --- | --- |
| `/` | 看板 |
| `/records` | 报销清单（金额精确 / ±1 / ±2 搜索） |
| `/sync` | 同步管理（Notion → SQLite） |

首次使用先在「同步管理」执行一次同步。

> 项目在 iCloud 目录时，冷启动可能较慢。

---

## 6. CLI 用法

交互菜单：

```bash
uv run python -m app.main
```

```text
  0. quit                  - 退出
  1. pdf                   - 下载附件并生成合并 PDF，更新 Notion 状态
  2. fapiao                - 下载发票 PDF 并生成发货单 Excel
  3. download              - 只下载附件，不生成 PDF
  4. cleanup               - 清理 downloads 和 output_pdfs
  5. clear-data            - 清空整个 data 目录
  6. invoice-to-delivery   - 从现有发票生成发货单 Excel
  7. web                   - 启动本地报销后台
```

也可直接：

```bash
uv run python -m app.main pdf
uv run python -m app.main fapiao
uv run python -m app.main download
uv run python -m app.main web
```

### pdf

- 查询 `STATUS_TO_PROCESS` 条目 → 下载附件 → 生成 A4 PDF 到 `data/output_pdfs/`
- 合并为 `merged_all.pdf` → 状态改为 `STATUS_PROCESSED`

### fapiao

- 只保留 PDF 到 `data/fapiao/`
- 生成 `发票发货单整理_YYYY-MM-DD_HH-MM-SS.xlsx`
- 不改 Notion 状态

### download

- 附件保存到 `data/downloads/`，不生成 PDF、不改状态

### invoice-to-delivery

```bash
uv run python -m app.main invoice-to-delivery
# 或指定路径
uv run python -m app.main invoice-to-delivery /path/to/fapiao /path/to/output.xlsx
```

---

## 7. 清理数据

```bash
uv run python -m app.main cleanup          # 清理 downloads + output_pdfs
uv run scripts/clear_data.py --dry-run     # 预览清空 data/
uv run scripts/clear_data.py --yes         # 清空 data/（含本地库）
```

---

## 8. 常见问题

- **Cannot find the database / Integration not connected**  
  检查 `NOTION_PAGE_ID` 是否为数据库 ID，以及 Integration 是否已连接。

- **状态没有更新**  
  确认 `STATUS_PROPERTY_NAME`、`STATUS_PROCESSED` 与 Notion 选项名完全一致。

- **Web 打不开**  
  确认终端仍有 `Uvicorn running on http://127.0.0.1:8000`；关掉终端会一并停服。

- **清单是空的**  
  先到 `/sync` 执行一次同步。

---

有运行时报错时，把完整终端输出贴出来即可继续排查。
