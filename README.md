![License](https://img.shields.io/github/license/LittleBeaverStudio/KingdeeDataExporter?label=license)
# kingdee-data-analyzer

一个基于 `KingdeeDataExporter` 导出数据的金蝶云星空经营分析 Skill。当前支持：

- 库存收发存分析报告
- 采购订单执行分析报告
- 销售出库分析报告

输出形式统一为：

- 可直接打开和分享的 HTML 报告
- 全量明细 Excel
- 可复用的结构化 JSON

HTML 报告内置“打印 / 另存为 PDF”按钮。直接生成 PDF 已取消，浏览器另存为 PDF 的版式更稳定。

## 前置条件

请先安装并配置 `KingdeeDataExporter`。

`KingdeeDataAnalyzer` 不直接维护金蝶账号配置，而是调用同级目录中的：

```text
../KingdeeDataExporter/data_exporter.py
```

因此推荐目录结构如下：

```text
KingdeeDataExporter_V1.5.1/
  KingdeeDataExporter/
    config.py
    data_exporter.py
    SKILL.md
  KingdeeDataAnalyzer/
    analyzer.py
    SKILL.md
```

`KingdeeDataExporter/config.py` 需要已经填写好 `KINGDEE_CONFIG`。不要把真实账号密码提交到公开仓库。

## 安装依赖

在 `KingdeeDataAnalyzer` 目录执行：

```bash
python -m pip install -r requirements.txt
```

同时确保 `KingdeeDataExporter` 的依赖也已安装：

```bash
cd ../KingdeeDataExporter
python -m pip install -r requirements.txt
```

## 快速开始

以下命令均在 `KingdeeDataAnalyzer` 目录执行。

### 库存收发存分析

```bash
python analyzer.py --type inventory
```

默认期间为上一个完整自然月。该报告会调用：

- `HS_INOUTSTOCKSUMMARYRPT` / 存货收发存汇总表
- `HS_NoDimInOutStockDetailRpt` / 存货收发存明细表

### 采购订单执行分析

```bash
python analyzer.py --type purchase
```

默认期间为今年 1 月 1 日至运行当天。该报告会调用：

- `PUR_PurchaseOrderDetailRpt` / 采购订单执行明细表

核心口径：

- 未结算金额 = 应付金额 - 已结算金额

### 销售出库分析

```bash
python analyzer.py --type sales
```

默认期间为今年 1 月 1 日至运行当天。该报告会调用：

- `SAL_OutStockInvoiceRpt` / 销售出库开票跟踪表

核心口径：

- 未结算金额 = 应收金额 - 收款结算金额
- 未结算金额保留原始差额，允许为负数
- 未结算金额明细按单据编号汇总，一张单据一行

## 指定期间和组织

如果需要分析任意期间，可以显式传入日期：

```bash
python analyzer.py --type sales --start 2026-01-01 --end 2026-06-01
```

如果不传 `--org`，会交给 `KingdeeDataExporter` 登录后自动解析组织。若要指定组织：

```bash
python analyzer.py --type sales --start 2026-01-01 --end 2026-06-01 --org 101
```

多个组织或 `all` 是否可用，取决于 `KingdeeDataExporter` 当前配置和金蝶权限。

当导出结果包含多个组织时，采购订单分析和销售出库分析会从源数据中的采购组织/销售组织字段汇总有数据的组织名称，并显示在报告头部。

## 从已有 Excel 生成报告

如果数据已经通过 `KingdeeDataExporter` 导出，可以跳过接口调用：

```bash
python analyzer.py --type purchase --excel "path/to/export.xlsx" --start 2026-01-01 --end 2026-06-01 --org 101
```

这种方式适合调试报告版式或复用历史导出数据。

## 输出文件

默认输出到 `KingdeeDataAnalyzer/outputs/`，文件名格式如下：

```text
inventory_report_YYYYMMDD.html
inventory_details_YYYYMMDD.xlsx
analysis_result.json

purchase_order_report_YYYYMMDD.html
purchase_order_details_YYYYMMDD.xlsx
purchase_order_analysis_result.json

sales_outstock_report_YYYYMMDD.html
sales_outstock_details_YYYYMMDD.xlsx
sales_outstock_analysis_result.json
```

也可以指定输出目录：

```bash
python analyzer.py --type sales --output-dir outputs_sales
```

## 文件结构

```text
KingdeeDataAnalyzer/
  README.md
  SKILL.md
  requirements.txt
  analyzer.py
  data_loader.py
  inventory_analyzer.py
  report_builder.py
  purchase_order_analyzer.py
  purchase_order_report_builder.py
  sales_outstock_analyzer.py
  sales_outstock_report_builder.py
```> ⚠️ 本工具仅在你自有金蝶环境的授权范围内使用，使用者自行负责凭据保管与数据合规。
