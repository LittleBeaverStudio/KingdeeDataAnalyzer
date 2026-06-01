from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from data_loader import KingdeeDataLoader
from inventory_analyzer import InventoryAnalyzer
from purchase_order_analyzer import PurchaseOrderAnalyzer
from purchase_order_report_builder import PurchaseOrderReportBuilder
from report_builder import ReportBuilder
from sales_outstock_analyzer import SalesOutstockAnalyzer
from sales_outstock_report_builder import SalesOutstockReportBuilder


def main() -> int:
    parser = argparse.ArgumentParser(description="KingdeeDataAnalyzer 财务经营分析工具")
    parser.add_argument("--type", choices=["inventory", "purchase", "sales", "finance"], default="inventory", help="分析类型：inventory / purchase / sales")
    parser.add_argument("--start", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--org", help="组织编码")
    parser.add_argument("--excel", help="直接读取已导出的 Excel 文件，跳过金蝶导出")
    parser.add_argument("--json", help="直接读取 analysis_result.json，重新生成报告")
    parser.add_argument("--output-dir", default="outputs", help="报告输出目录")
    parser.add_argument("--pdf", action="store_true", help="兼容旧参数：不再直接生成 PDF，请在 HTML 中点击“打印 / 另存为 PDF”")
    parser.add_argument("--open", action="store_true", help="生成后用系统默认浏览器打开 HTML")
    args = parser.parse_args()

    if args.type == "finance":
        raise SystemExit("当前版本已支持 inventory/purchase/sales；finance 后续扩展。")

    base_dir = Path(__file__).resolve().parent
    output_dir = (base_dir / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.json:
        result = json.loads(Path(args.json).read_text(encoding="utf-8"))
    else:
        start, end = _resolve_dates(args.start, args.end, args.type)
        loader = KingdeeDataLoader()
        if args.type == "inventory":
            if args.excel:
                summary_df, detail_df = loader.load_inventory_from_excel(args.excel)
                source_excel = Path(args.excel).resolve()
            else:
                summary_df, detail_df, source_excel = loader.load_inventory(start, end, args.org)

            analyzer = InventoryAnalyzer(summary_df, detail_df)
            result = analyzer.analyze(org_name=args.org or "Excel导入", period_str=f"{start} ~ {end}")
            result["source_excel"] = str(source_excel)
            analyzer.save_json(output_dir / "analysis_result.json")
        elif args.type == "purchase":
            if args.excel:
                detail_df = loader.load_purchase_orders_from_excel(args.excel)
                source_excel = Path(args.excel).resolve()
            else:
                detail_df, source_excel = loader.load_purchase_orders(start, end, args.org)

            analyzer = PurchaseOrderAnalyzer(detail_df)
            result = analyzer.analyze(org_name=args.org or "Excel导入", period_str=f"{start} ~ {end}")
            result["source_excel"] = str(source_excel)
            analyzer.save_json(output_dir / "purchase_order_analysis_result.json")
        else:
            if args.excel:
                detail_df = loader.load_sales_outstock_from_excel(args.excel)
                source_excel = Path(args.excel).resolve()
            else:
                detail_df, source_excel = loader.load_sales_outstock(start, end, args.org)

            analyzer = SalesOutstockAnalyzer(detail_df)
            result = analyzer.analyze(org_name=args.org or "Excel导入", period_str=f"{start} ~ {end}")
            result["source_excel"] = str(source_excel)
            analyzer.save_json(output_dir / "sales_outstock_analysis_result.json")

    if args.type == "purchase":
        builder = PurchaseOrderReportBuilder(result)
    elif args.type == "sales":
        builder = SalesOutstockReportBuilder(result)
    else:
        builder = ReportBuilder(result)
    stamp = date.today().strftime("%Y%m%d")
    prefix = {"purchase": "purchase_order", "sales": "sales_outstock"}.get(args.type, "inventory")
    excel_path = builder.generate_excel(output_dir / f"{prefix}_details_{stamp}.xlsx")
    html_path = builder.generate_html(output_dir / f"{prefix}_report_{stamp}.html", excel_path=excel_path)
    if args.open:
        _open_file(html_path)

    print(f"HTML报告: {html_path}")
    print(f"明细Excel: {excel_path}")
    if args.pdf:
        print("PDF报告: 已取消程序直出；请打开 HTML 后点击“打印 / 另存为 PDF”。")

    print()
    print(builder.generate_summary_markdown())
    return 0


def _resolve_dates(start: str | None, end: str | None, report_type: str = "inventory") -> tuple[str, str]:
    if start and end:
        return start, end

    today = date.today()
    if report_type in ("purchase", "sales"):
        return start or today.replace(month=1, day=1).isoformat(), end or today.isoformat()

    first_this_month = today.replace(day=1)
    last_month_end = first_this_month - timedelta(days=1)
    start_default = last_month_end.replace(day=1).isoformat()
    end_default = last_month_end.isoformat()
    return start or start_default, end or end_default


def _open_file(path: Path) -> None:
    import os
    import platform
    import subprocess

    system = platform.system()
    if system == "Windows":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif system == "Darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


if __name__ == "__main__":
    raise SystemExit(main())
