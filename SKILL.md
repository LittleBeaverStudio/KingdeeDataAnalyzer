---
name: kingdee-data-analyzer
description: Kingdee Cloud business data analysis skill. Use when Codex needs to analyze data exported by kingdee-data-exporter and generate shareable inventory, purchase order, sales outstock, or finance reports. Current modules are inventory analysis, purchase order execution analysis, and sales outstock invoice tracking analysis, all producing standalone HTML summary reports and full-detail Excel workbooks.
---

# Kingdee Data Analyzer

Use this skill to turn KingdeeDataExporter output into business analysis reports. Current modules are inventory analysis, purchase order execution analysis, and sales outstock invoice tracking analysis. Financial statement analysis is a reserved extension point.

## Inventory Analysis Workflow

Run from the `KingdeeDataAnalyzer` folder.

### From Kingdee live export

```bash
python analyzer.py --type inventory --start 2025-06-01 --end 2026-05-31 --org 101
```

This calls sibling `../KingdeeDataExporter/data_exporter.py` with:

- `HS_INOUTSTOCKSUMMARYRPT` / 存货收发存汇总表
- `HS_NoDimInOutStockDetailRpt` / 存货收发存明细表

The generated Excel is saved under `outputs/`, then analyzed.

### From an existing Excel export

```bash
python analyzer.py --type inventory --excel "path/to/export.xlsx" --start 2025-06-01 --end 2026-05-31 --org 101
```

Use this for debugging or when the data has already been exported.

### Rebuild a report from JSON

```bash
python analyzer.py --json outputs/analysis_result.json
```

Use this when only the report layout needs to be repeated.

## Outputs

Reports are written to `outputs/` by default:

- `analysis_result.json`: structured analysis result for downstream use.
- `inventory_report_YYYYMMDD.html`: standalone summary report. It embeds all data, so it can be opened directly or shared without a local web server.
- `inventory_details_YYYYMMDD.xlsx`: full-detail workbook with monthly trend, doc type breakdown, all material forecasts, all procurement suggestions, summary statistics, and calculation notes.

The HTML report contains a print button, so users can open it in a browser and save as PDF. Direct PDF generation was intentionally removed because browser print output is more faithful to the HTML layout.

## Purchase Order Analysis Workflow

Run from the `KingdeeDataAnalyzer` folder.

### From Kingdee live export

```bash
python analyzer.py --type purchase --start 2026-01-01 --end 2026-06-01 --org 101
```

If `--start` and `--end` are omitted, purchase order analysis defaults to the current year-to-date period.

This calls sibling `../KingdeeDataExporter/data_exporter.py` with:

- `PUR_PurchaseOrderDetailRpt` / 采购订单执行明细表

### From an existing Excel export

```bash
python analyzer.py --type purchase --excel "path/to/export.xlsx" --start 2026-01-01 --end 2026-06-01 --org 101
```

### Purchase Order Outputs

- `purchase_order_analysis_result.json`: structured purchase order analysis result.
- `purchase_order_report_YYYYMMDD.html`: standalone summary report.
- `purchase_order_details_YYYYMMDD.xlsx`: full-detail workbook with summary, monthly trend, supplier ranking, material ranking, overdue unreceived lines, full detail, and calculation notes.

### Purchase Order Method Notes

- 未结算金额 = 应付金额 - 已结算金额；小于0时按0计入未结算风险。
- 收料率 = 收料数量 / 订货数量。
- 入库率 = 入库数量 / 订货数量。
- 结算率 = 已结算金额 / 应付金额。
- 逾期未收料按交货日期早于报告生成日且未收料数量大于0识别。

## Sales Outstock Analysis Workflow

Run from the `KingdeeDataAnalyzer` folder.

### From Kingdee live export

```bash
python analyzer.py --type sales --start 2026-01-01 --end 2026-06-01 --org 101
```

If `--start` and `--end` are omitted, sales analysis defaults to the current year-to-date period.

This calls sibling `../KingdeeDataExporter/data_exporter.py` with:

- `SAL_OutStockInvoiceRpt` / 销售出库开票跟踪表

### From an existing Excel export

```bash
python analyzer.py --type sales --excel "path/to/export.xlsx" --start 2026-01-01 --end 2026-06-01 --org 101
```

### Sales Outstock Outputs

- `sales_outstock_analysis_result.json`: structured sales outstock analysis result.
- `sales_outstock_report_YYYYMMDD.html`: standalone summary report.
- `sales_outstock_details_YYYYMMDD.xlsx`: full-detail workbook with summary, monthly trend, bill type, salesperson, material, customer, unsettled details, full detail, and calculation notes.

### Sales Outstock Method Notes

- 未结算金额 = 应收金额 - 收款结算金额；该字段按原始差额保留，可能为负数。
- 未开票金额 = 应收金额 - 开票金额。
- 开票率 = 开票金额 / 应收金额。
- 结算率 = 收款结算金额 / 应收金额。
- 未结算金额明细按单据编号汇总，一张单据一行；重点统计维度包括单据类型、销售员、物料名称和客户。

## Inventory Method Notes

- Material forecast uses a conservative ensemble: Holt trend 25%, recent 3-month average 55%, and long-term monthly average 20%.
- If a material still has consumption in the latest 6 months, each future month is floored at 50% of its recent 3-month average. This prevents active materials from being forecast to zero only because the Holt trend is falling.
- Suggested order quantity is `max(0, next 3 months forecast + safety stock - current stock)`, rounded up to a multiple of 10.
- Purchase timing is driven by suggested order quantity first. If suggested quantity is 0, the report does not label it as "立即采购"; low-stock/no-demand conflicts are labeled for manual review.

## Module Files

- `data_loader.py`: calls KingdeeDataExporter or reads an existing Excel file.
- `inventory_analyzer.py`: calculates inventory trends, forecasts, and procurement suggestions.
- `purchase_order_analyzer.py`: calculates purchase order execution, settlement, and overdue unreceived metrics.
- `sales_outstock_analyzer.py`: calculates sales outstock, invoice, receipt settlement, unsettled amount, and dimension summaries.
- `report_builder.py`: creates inventory standalone HTML output and full-detail Excel workbooks.
- `purchase_order_report_builder.py`: creates purchase order standalone HTML output and full-detail Excel workbooks.
- `sales_outstock_report_builder.py`: creates sales outstock standalone HTML output and full-detail Excel workbooks.
- `analyzer.py`: command-line entry point and orchestration.

## Extension Notes

Keep future modules behind a clear `--type` value, such as `finance`. Reuse the same pattern:

1. Load source tables through `data_loader.py`.
2. Put business calculations in a focused analyzer module.
3. Return JSON-serializable results.
4. Generate standalone HTML and full-detail Excel through report builders; use browser print/save-as-PDF for sharing.
