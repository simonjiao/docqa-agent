# 项目调试跟踪

## 2026-05-28 OCR 中文语言包

运行文档问答原型时，项目默认 OCR 语言为 `HanS+eng`。本机初始 Tesseract 语言列表只有英文相关语言，强制重新 OCR 中文扫描 PDF 时会缺少中文识别能力。

## 调试记录

- 时间：2026-05-28 09:00 CST
- 工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`
- 现象：启动前检查发现 Tesseract 只包含 `eng`、`osd`、`snum`。
- 检查命令：

```bash
tesseract --list-langs
```

- 初始结果摘要：

```text
eng
osd
snum
```

## 原因

本机已安装 Tesseract 主程序，但未安装额外语言数据包。中文 OCR 需要 `chi_sim`、`chi_tra` 或 `script/HanS` 等语言数据。

## 处理

通过 Homebrew 查询并安装额外语言包：

```bash
brew info tesseract-lang
brew install tesseract-lang
```

安装结果摘要：

```text
tesseract-lang 4.1.0
installed to /opt/homebrew/Cellar/tesseract-lang/4.1.0
```

相关版本：

```text
tesseract 5.5.2
tesseract-lang 4.1.0
libunistring 1.4.2
```

## 验证

安装后再次检查语言列表：

```bash
tesseract --list-langs | rg 'chi|Han|eng|osd|snum'
```

确认可用语言包括：

```text
chi_sim
chi_sim_vert
chi_tra
chi_tra_vert
eng
osd
script/HanS
script/HanS_vert
script/HanT
script/HanT_vert
snum
```

使用现有样例页面图做一次不落盘 OCR 验证：

```bash
tesseract 'storage/GBT1568-2008键技术条件-e724ad081078fa41/pages/page-3.png' stdout -l chi_sim+eng --psm 6
```

输出能正常识别中文正文，例如：

```text
本标准规定了除花键外的各种键的技术要求,验收检查、标志与包装。
```

## 后续运行建议

默认运行可以继续使用：

```bash
./run.sh
```

如果 `HanS+eng` 在某些环境下不可用，改用简体中文语言包启动：

```bash
OCR_LANG=chi_sim+eng ./run.sh
```

如需强制用新语言包重新生成 OCR 缓存：

```bash
FORCE_REPROCESS=1 OCR_LANG=chi_sim+eng ./run.sh
```

注意：`storage/` 是本地运行缓存目录。提交前应检查是否有不希望提交的 OCR 缓存或上传文档。

## 2026-05-28 提交后运行服务

用户要求生成一次提交并运行程序。

调试记录：

- 时间：2026-05-28 09:05 CST
- 工作目录：`/Users/simon/ai-agents/docqa_agent_prototype`
- 提交前验证命令：

```bash
.venv/bin/python -m pytest -q
```

- 结果摘要：

```text
6 passed, 5 warnings
```

- 生成提交：

```bash
git commit -m "Add project debug trace guidance"
```

- 初次后台启动尝试：

```bash
nohup env OCR_LANG=chi_sim+eng STORAGE_DIR=./storage .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload > /tmp/docqa_agent_prototype_uvicorn.log 2>&1 &
```

- 现象：HTTP 探针返回 `000`，`/api/load-sample` 没有 JSON 输出，8000 端口未监听；日志文件为空。
- 处理：改用前台命令验证应用本身可启动，确认问题不在应用导入或接口逻辑。

```bash
env OCR_LANG=chi_sim+eng STORAGE_DIR=./storage .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- 验证结果：

```text
GET / -> 200
POST /api/load-sample -> 200
```

后续运行建议：后台运行时优先不带 `--reload`，避免本地后台启动行为受 reloader 进程管理影响；开发调试需要热加载时再前台运行 `./run.sh`。

## 2026-05-28 使用 tmux 运行服务

用户要求使用 `tmux` 运行程序。

处理命令：

```bash
tmux new-session -d -s docqa_agent_prototype -c /Users/simon/ai-agents/docqa_agent_prototype 'OCR_LANG=chi_sim+eng STORAGE_DIR=./storage .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000'
```

验证命令：

```bash
curl -s -o /tmp/docqa_index.html -w '%{http_code}\n' http://127.0.0.1:8000/
curl -s -X POST http://127.0.0.1:8000/api/load-sample
lsof -iTCP:8000 -sTCP:LISTEN -n -P
```

结果摘要：

```text
GET / -> 200
POST /api/load-sample -> 200
127.0.0.1:8000 is listening, PID 72086
```

查看 tmux 窗口和日志：

```bash
tmux list-windows -t docqa_agent_prototype
tmux capture-pane -pt docqa_agent_prototype:1.1 -S -80
```

注意：该 session 的窗口编号为 `1`，pane 编号为 `1`；使用 `docqa_agent_prototype:0` 会报 `can't find window: 0`。
