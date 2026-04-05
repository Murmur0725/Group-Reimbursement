# Notion 报销附件下载与 PDF 工具

这是一个 Python 工具，用来从 **Notion 报销数据库** 中批量下载「文件和媒体」附件，并按记录生成 A4 PDF。  
目前适配的场景是：Notion 中有一个报销数据库，字段大致为：

- 名称（`名称`）
- 状态（`状态`）
- 文件和媒体（`文件和媒体`）
- 编号（`编号`，可选，用来给 PDF 命名和打标）

工具支持两种模式：

- **pdf 模式**：下载附件 → 合并成 PDF → 更新 Notion 状态
- **download 模式**：只下载附件到本地，不生成 PDF、不改状态

还内置了一个清理命令，可以一键删除历史下载和生成的 PDF。

当前项目结构：

```text
Group-Reimbursement/
├─ app/
│  ├─ __init__.py
│  ├─ main.py
│  ├─ config.py
│  ├─ notion_client.py
│  ├─ downloader.py
│  ├─ pdf_service.py
│  └─ cleanup.py
├─ data/
│  ├─ downloads/
│  └─ output_pdfs/
├─ tests/
│  ├─ test_config.py
│  ├─ test_downloader.py
│  └─ test_pdf_service.py
├─ .env
├─ .env.example
├─ README.md
├─ pyproject.toml
└─ uv.lock
```

---

## 1. 安装依赖

在项目根目录执行：

```bash
uv sync
```

> 需要 Python 3.12+，并且可以访问外网（调用 Notion API 与下载附件）。

---

## 2. 配置 Notion Integration

1. 打开 [Notion My Integrations](https://www.notion.so/my-integrations)  
2. 点击 **New integration** 创建一个集成（例如命名为 `group_rebustement`）  
3. 创建完成后，在集成详情页里复制 **Internal Integration Secret**（以 `ntn_` 开头）  
4. 打开你的报销数据库页面  
5. 在页面右上角点击 `...` → **集成 / Connections / Connect to**  
6. 选择你刚才创建的集成，并确认已连接

> 只有把数据库页面与这个集成连接起来，下面的脚本才能读取和更新数据。

---

## 3. 获取数据库 ID

1. 在 Notion 中打开你的报销数据库（表格视图）  
2. 将鼠标移动到表格右上角，点击「在新页面中打开」或对应的 ↗ 图标  
3. 此时浏览器地址会类似：

   ```text
   https://www.notion.so/xxxxxx/表格名称-30399adbdb7b80fe9af4c9eb0dadad40
   ```

4. 记下最后那串 32 位字符：

   ```text
   30399adbdb7b80fe9af4c9eb0dadad40
   ```

这就是数据库的 **Database ID**，稍后会写进 `.env` 的 `NOTION_PAGE_ID`。

---

## 4. 配置 `.env`

在项目根目录创建 `.env`（或基于 `.env.example` 修改），示例：

```ini
NOTION_TOKEN=ntn_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx        # 集成的 Secret
NOTION_PAGE_ID=30399adbdb7b80fe9af4c9eb0dadad40      # 数据库 ID

# 和你 Notion 数据库字段名称完全一致（包括中英文、标点）
STATUS_PROPERTY_NAME=状态
NUMBER_PROPERTY_NAME=编号
NAME_PROPERTY_NAME=名称
FILES_PROPERTY_NAME=文件和媒体

# 仅处理状态为这个值的条目，例如「1-发票+购买记录」
STATUS_TO_PROCESS=1-发票+购买记录

# 处理完成后要更新成的状态值
STATUS_PROCESSED=2-已处理

# 运行模式：pdf（默认，生成 PDF 并更新状态）或 download（只下载文件）
MODE=pdf
```

注意：

- `STATUS_PROPERTY_NAME`、`NUMBER_PROPERTY_NAME`、`NAME_PROPERTY_NAME`、`FILES_PROPERTY_NAME` 必须和数据库里的列名一模一样
- `STATUS_TO_PROCESS` 和 `STATUS_PROCESSED` 必须和「状态」这个 Select 的选项名字完全一致

---

## 5. 运行工具

### 5.1 生成 PDF 并更新 Notion 状态（默认）

在根目录执行：

```bash
uv run python -m app.main
```

行为：

- 查询数据库中「状态」等于 `STATUS_TO_PROCESS` 的所有条目
- 下载每条记录的「文件和媒体」附件（支持图片、PDF）
- 为每条记录生成一个独立的 A4 PDF，文件名大致为：

  ```text
  编号_名称.pdf
  ```

- 生成的 PDF 保存到：

  ```text
  ./data/output_pdfs/
  ```

- 将对应条目的「状态」更新为 `STATUS_PROCESSED`

### 5.2 只下载附件，不生成 PDF

将 `.env` 中的 `MODE` 改为：

```ini
MODE=download
```

然后运行：

```bash
uv run python -m app.main
```

行为：

- 只下载「文件和媒体」里的附件到 `./data/downloads/` 目录
- 不生成 `data/output_pdfs`，也不会修改 Notion 的状态

---

## 6. 清理历史下载和 PDF

工具内置了一个简单的清理命令，会删除：

- `./data/downloads/`
- `./data/output_pdfs/`

在项目根目录执行任意一种写法均可：

```bash
uv run python -m app.main clearup
uv run python -m app.main clear
uv run python -m app.main "clear up"
```

如果目录不存在，会打印：

```text
No data/downloads or data/output_pdfs directory to remove.
```

---

## 7. 常见问题

- **提示 “Cannot find the database / Integration is NOT connected”**
  - 检查 `.env` 里的 `NOTION_PAGE_ID` 是否是数据库 ID，而不是普通页面 ID
  - 检查数据库页面右上角是否已连接到当前使用的 Integration
  - 确认 `NOTION_TOKEN` 来自这个 Integration 的 Secret

- **状态没有更新**
  - 确认 `STATUS_PROPERTY_NAME` 是数据库中状态列的真实列名
  - 确认 `STATUS_PROCESSED` 对应的选项在 Notion 中存在，名称完全一致

---

有任何运行时终端报错，把完整输出贴出来，就可以根据提示进一步排查。 
