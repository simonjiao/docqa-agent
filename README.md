# 智能文档问答 Agent 原型

这是一个面向技术笔试作业的最小可运行原型。目标不是做完整商业系统，而是把“扫描 PDF 识别、可检索知识库、问答证据、自检、人工复核”串成一个可以演示和迭代的闭环。

## 1. 原型能力

- Web 交互：左侧查看 PDF 页面图像，右侧查看 OCR 行级识别结果、疑似表格区域、验证结果。
- PDF 策略判断：自动识别文本层 PDF、扫描 PDF、混合 PDF，并选择解析策略。
- OCR 识别：默认使用 Tesseract，语言为 `HanS+eng`，适配中文扫描件与英文/数字混排。
- 表格候选区：基于页面横竖线检测表格区域，供后续表格 OCR 与人工复核。
- RAG 检索：使用 TF-IDF 字符 n-gram 建立轻量索引，不依赖外部 API。
- 问答输出：默认采用抽取式答案，返回来源页码和片段；证据不足时拒答。
- 多流程验证：包括文档识别验证、检索验证、答案依据验证、LLM 验证占位、人工验证记录。
- 可复现测试：提供单元测试和评估脚本，覆盖正文、表格、无答案问题。

## 2. 快速启动

### 2.1 安装系统 OCR

Linux 示例：

```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-script-hans
```

如果本机 Tesseract 语言包名称不是 `HanS`，可以通过以下命令查看：

```bash
tesseract --list-langs
```

然后设置环境变量，例如：

```bash
export OCR_LANG=chi_sim+eng
export OCR_DPI=120
export OCR_TIMEOUT=30
```

### 2.2 安装 Python 依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2.3 启动 Web 原型

```bash
./run.sh
```

浏览器打开：

```text
http://localhost:8000
```

可以点击“加载样例 PDF”，或上传新的 PDF。项目包内保留了样例识别缓存，便于快速演示；如需强制重新 OCR，可设置 `FORCE_REPROCESS=1` 或清空 `storage/`。

## 3. 代码结构

```text
app/
  main.py                 FastAPI 接口与页面入口
  core/
    pdf_probe.py          PDF 类型判断与解析策略选择
    ocr.py                页面渲染、OCR、表格候选区域检测
    chunker.py            条款/正文分块
    retrieval.py          TF-IDF 检索
    qa.py                 抽取式问答与拒答逻辑
    validators.py         文档识别、检索、答案、LLM、人工验证
    storage.py            文档、识别结果、复核记录持久化
  web/
    templates/index.html  Web 页面
    static/app.js         前端交互
    static/style.css      样式
docs/
  architecture.md         架构说明
  validation_workflow.md  验证流程说明
  demo_script.md          演示脚本
  debug_trace.md          调试过程跟踪记录
scripts/
  evaluate.py             样例问题评估脚本
tests/
  pytest 单元测试
AGENTS.md                 项目协作规则与调试跟踪要求
```

## 4. 处理流程

1. 上传 PDF。
2. `pdf_probe` 判断是否有文本层、是否属于扫描件。
3. 页面渲染为 PNG。
4. OCR 识别正文、条款编号、数字、英文。
5. 检测疑似表格区域。
6. 以页码和行号为粒度构建 chunk。
7. 根据用户问题检索相关证据。
8. 生成答案，返回页码和片段。
9. 执行自检：证据分数、答案和证据重合度、无答案保护。
10. 前端支持人工确认、退回或标记不确定，并保存复核记录。

## 5. 验证流程

原型集成了三层验证：

- 文档识别过程验证：OCR 平均置信度、文本密度、表格候选区域。
- LLM/答案验证：默认不开启外部模型，但保留 `llm_validation` 阶段；实际项目中可接入模型判断“证据是否支持答案、是否需要拒答、表格是否遗漏”。
- 人工验证：Web 页面中可对答案做通过、退回修正、不确定记录，形成审计轨迹。

## 6. 示例问题

建议演示至少 5 个问题：

1. 本标准规定了什么范围？
2. 键的抗拉强度要求是多少？
3. 表 1 中合格质量水平 AQL 和哪些检查项目有关？
4. 包装箱或盒外表面应有哪些标志？
5. 该标准是否规定了电机噪声测试？

第 5 个问题应触发无答案保护。

## 7. 测试

```bash
pytest -q
```

运行评估脚本：

```bash
python scripts/evaluate.py --sample
```

## 8. 当前取舍与限制

- 为保证可复现，默认不依赖外部 LLM API；答案生成采用抽取式策略。
- 表格识别实现为“表格区域检测 + OCR 文本”，不是完整单元格结构恢复；这是本原型的主要迭代点。
- OCR 结果受 Tesseract 语言包、DPI、扫描质量影响；低置信度页面会进入人工复核。默认 `OCR_DPI=120`、`OCR_TIMEOUT=30`，防止扫描噪声导致识别过程长时间阻塞。
- 轻量检索使用 TF-IDF，适合原型和小规模文档；生产可替换为向量索引、BM25 + embedding 混合检索。

## 9. AI 使用说明模板

本项目允许使用 AI 辅助开发，但结果需要自己负责。建议在提交时如实说明：

- 使用 AI 辅助梳理架构、生成样板代码、设计测试用例。
- 对生成代码进行了本地运行、单元测试和人工阅读。
- 对 OCR 和问答结果设置了自检与人工复核，不把 AI 输出直接作为最终事实。
- 未提交 API Key、账号密码或其他敏感信息。
