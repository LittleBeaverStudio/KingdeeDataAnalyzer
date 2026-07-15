---
name: kingdee-data-analyzer
description: 金蝶云星空经营数据分析技能。用于读取 kingdee-data-exporter 导出的 Excel，或自动调用导出技能获取数据，完成库存收发存、采购订单执行和销售出库开票分析，并生成可分享的 HTML 报告、全量明细 Excel 和结构化 JSON。当用户提到金蝶库存分析、采购执行、逾期未收料、销售出库、开票率、结算率、未结算金额或经营分析报告时使用。
---

# 金蝶云星空经营数据分析

使用本技能把金蝶云星空导出数据整理成便于查看和分享的经营分析报告。

## 当前能力

- `inventory`：库存收发存、趋势预测和采购建议
- `purchase`：采购订单执行、收料/入库/结算情况和逾期未收料
- `sales`：销售出库、开票、收款结算和未结算金额

每次分析生成：

- 独立 HTML 报告，可直接打开、分享或打印为 PDF
- 全量明细 Excel
- 结构化 JSON，便于后续复用

## 工作原则

1. 先确认用户要分析的类型、期间和组织。
2. 有现成 Excel 时优先使用 `--excel`，无需连接金蝶或安装导出技能。
3. 需要实时取数时，使用同级的 `kingdee-data-exporter`。
4. 不展示无关的业务明细、账号密码或其他敏感信息。
5. 报告生成后说明完整路径，并核对输出文件是否存在。

## 安装依赖

在技能目录中执行：

```bash
python -m pip install -r requirements.txt
```

实时取数还需要安装并配置 `kingdee-data-exporter`。程序会自动查找以下同级目录：

- `kingdee-data-exporter/`
- `KingdeeDataExporter/`

也可以用 `--exporter` 或环境变量 `KINGDEE_DATA_EXPORTER` 指定 `data_exporter.py` 的完整路径。

## 从实时数据生成报告

库存分析，默认分析上一个完整自然月：

```bash
python analyzer.py --type inventory
```

采购分析，默认分析本年截至今天：

```bash
python analyzer.py --type purchase
```

销售分析，默认分析本年截至今天：

```bash
python analyzer.py --type sales
```

指定期间和组织：

```bash
python analyzer.py --type sales --start 2026-01-01 --end 2026-06-30 --org ORG001
```

指定导出脚本：

```bash
python analyzer.py --type purchase --exporter "D:/skills/kingdee-data-exporter/data_exporter.py"
```

## 从已有 Excel 生成报告

```bash
python analyzer.py --type inventory --excel "D:/data/金蝶导出.xlsx" --start 2026-01-01 --end 2026-06-30
```

读取现有 Excel 时不要求 `kingdee-data-exporter` 存在。

## 复用 JSON 重新生成报告

```bash
python analyzer.py --type inventory --json outputs/analysis_result.json
```

仅调整报告版式或重新导出时使用，避免重复取数和计算。

## 输出文件

默认写入 `outputs/`：

- 库存：`inventory_report_*.html`、`inventory_details_*.xlsx`、`analysis_result.json`
- 采购：`purchase_order_report_*.html`、`purchase_order_details_*.xlsx`、`purchase_order_analysis_result.json`
- 销售：`sales_outstock_report_*.html`、`sales_outstock_details_*.xlsx`、`sales_outstock_analysis_result.json`

使用 `--output-dir` 可以指定输出目录，使用 `--open` 可以生成后打开 HTML。

## 口径说明

### 库存

- 建议采购量 = `未来 3 个月预测 + 安全库存 - 当前库存`，小于 0 时按 0。
- 有持续消耗的物料会设置预测下限，避免下降趋势直接预测为 0。
- 建议采购量为 0 时，不标记为“立即采购”。

### 采购

- 未结算金额 = 应付金额 - 已结算金额；风险统计中小于 0 时按 0。
- 收料率 = 收料数量 / 订货数量。
- 入库率 = 入库数量 / 订货数量。
- 结算率 = 已结算金额 / 应付金额。
- 交货日期早于报告日且未收料数量大于 0，视为逾期未收料。

### 销售

- 未结算金额 = 应收金额 - 收款结算金额，保留原始差额，可能为负数。
- 未开票金额 = 应收金额 - 开票金额。
- 开票率 = 开票金额 / 应收金额。
- 结算率 = 收款结算金额 / 应收金额。
- 未结算明细按单据编号汇总，一张单据一行。

## 结果检查

1. 检查 HTML、Excel 和 JSON 是否成功生成。
2. 抽查报告总额与 Excel 明细汇总是否一致。
3. 数据为空时核对期间、组织、工作表名称和导出权限。
4. 需要 PDF 时打开 HTML，使用浏览器“打印 / 另存为 PDF”。
