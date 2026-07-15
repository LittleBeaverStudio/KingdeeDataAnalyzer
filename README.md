# 金蝶云星空经营数据分析 Skill

读取金蝶云星空导出的 Excel，自动生成清晰、可分享的经营分析报告。面向库存、采购、销售和财务人员，命令与说明均以中文使用场景为主。

## ✨ 当前支持

| 分析类型 | 主要内容 | 命令参数 |
| --- | --- | --- |
| 库存分析 | 收发存趋势、物料预测、采购建议 | `--type inventory` |
| 采购分析 | 收料率、入库率、结算率、逾期未收料 | `--type purchase` |
| 销售分析 | 出库、开票率、结算率、未结算金额 | `--type sales` |

每次分析会生成：

- 🌐 独立 HTML 报告：直接打开、分享或打印为 PDF
- 📊 全量明细 Excel：保留分析明细和计算说明
- 🧱 结构化 JSON：方便重新生成报告或接入其他流程

## 🚀 快速开始

### 1. 安装依赖

```bash
python -m pip install -r requirements.txt
```

### 2. 选择数据来源

有两种方式：

1. 使用已有 Excel，最简单，不需要连接金蝶。
2. 调用 `kingdee-data-exporter` 实时导出后再分析。

## 📄 从已有 Excel 分析

库存分析：

```bash
python analyzer.py --type inventory --excel "D:/data/金蝶导出.xlsx" --start 2026-01-01 --end 2026-06-30
```

采购分析：

```bash
python analyzer.py --type purchase --excel "D:/data/金蝶导出.xlsx" --start 2026-01-01 --end 2026-06-30
```

销售分析：

```bash
python analyzer.py --type sales --excel "D:/data/金蝶导出.xlsx" --start 2026-01-01 --end 2026-06-30
```

从 Excel 分析时，不要求安装 `kingdee-data-exporter`。

## 🔄 实时导出并分析

先安装并配置：

```text
https://github.com/LittleBeaverStudio/KingdeeDataExporter
```

程序会自动查找同级目录中的这两种名称：

```text
kingdee-data-exporter/
KingdeeDataExporter/
```

推荐目录结构：

```text
skills/
├── kingdee-data-exporter/
│   ├── SKILL.md
│   ├── config.py
│   └── data_exporter.py
└── kingdee-data-analyzer/
    ├── SKILL.md
    └── analyzer.py
```

如果安装位置不同，使用 `--exporter` 指定脚本：

```bash
python analyzer.py --type inventory --exporter "D:/skills/kingdee-data-exporter/data_exporter.py"
```

也可以设置环境变量 `KINGDEE_DATA_EXPORTER`。

### 常用命令

库存分析默认取上一个完整自然月：

```bash
python analyzer.py --type inventory
```

采购和销售分析默认取本年截至今天：

```bash
python analyzer.py --type purchase
python analyzer.py --type sales
```

指定期间和组织：

```bash
python analyzer.py --type sales --start 2026-01-01 --end 2026-06-30 --org ORG001
```

生成后自动打开报告：

```bash
python analyzer.py --type sales --open
```

## 📦 输出文件

默认写入 `outputs/`：

```text
库存：
  inventory_report_YYYYMMDD.html
  inventory_details_YYYYMMDD.xlsx
  analysis_result.json

采购：
  purchase_order_report_YYYYMMDD.html
  purchase_order_details_YYYYMMDD.xlsx
  purchase_order_analysis_result.json

销售：
  sales_outstock_report_YYYYMMDD.html
  sales_outstock_details_YYYYMMDD.xlsx
  sales_outstock_analysis_result.json
```

指定其他输出目录：

```bash
python analyzer.py --type sales --output-dir outputs_sales
```

程序不再直接生成 PDF。打开 HTML 后点击“打印 / 另存为 PDF”，版式通常更稳定。

## 🧮 关键口径

### 库存

- 建议采购量 = 未来 3 个月预测 + 安全库存 - 当前库存，小于 0 时按 0。
- 对仍有消耗的物料设置预测下限，避免下降趋势直接预测为 0。

### 采购

- 未结算金额 = 应付金额 - 已结算金额。
- 收料率 = 收料数量 / 订货数量。
- 入库率 = 入库数量 / 订货数量。
- 结算率 = 已结算金额 / 应付金额。
- 交货日期已过且仍有未收料数量，视为逾期未收料。

### 销售

- 未结算金额 = 应收金额 - 收款结算金额，可能为负数。
- 未开票金额 = 应收金额 - 开票金额。
- 开票率 = 开票金额 / 应收金额。
- 结算率 = 收款结算金额 / 应收金额。

## 🤖 让 AI 工具识别这个 Skill

仓库采用“一个仓库一个 Skill”的通用结构，`SKILL.md` 位于根目录：

```text
KingdeeDataAnalyzer/
├── SKILL.md
├── README.md
├── analyzer.py
├── data_loader.py
├── *_analyzer.py
├── *_report_builder.py
└── requirements.txt
```

支持 GitHub Skill 扫描的工具可以直接使用：

```text
https://github.com/LittleBeaverStudio/KingdeeDataAnalyzer
```

示例任务：

```text
请使用 kingdee-data-analyzer，分析这份金蝶 Excel 的采购执行情况，并生成 HTML 和 Excel 报告。
```

### ClawHub 特别说明

ClawHub 的网页 GitHub 导入器目前只扫描“登录用户本人拥有”的公开、非 Fork 仓库，不扫描 GitHub Organization 仓库。本仓库属于 `LittleBeaverStudio` Organization，因此不会出现在网页导入列表中，这不是目录结构问题。

可以在仓库根目录直接发布：

```bash
npx clawhub publish . --slug kingdee-data-analyzer --version 1.0.0
```

也可以把仓库镜像到当前登录用户本人名下的公开、非 Fork 仓库，再使用 GitHub 导入功能。

### SkillHub / 其他管理器

能递归扫描 `SKILL.md` 的管理器可以直接识别本仓库。上传 ZIP 时，确认解压后的根目录中包含 `SKILL.md` 和所有 Python 文件。

## 🛠️ 常见问题

### 提示找不到 `data_exporter.py`

- 安装 `kingdee-data-exporter`；或
- 用 `--exporter` 指定路径；或
- 设置环境变量 `KINGDEE_DATA_EXPORTER`。

### 已经有 Excel，为什么还要导出器

新版本从已有 Excel 分析时不再需要导出器。直接使用 `--excel` 即可。

### 只想重新生成报告

使用已有 JSON：

```bash
python analyzer.py --type inventory --json outputs/analysis_result.json
```

### 检查新版本

```bash
python analyzer.py --check-update
```

> 本工具仅用于你有权访问的数据。请妥善保管金蝶凭据和导出的经营数据。
