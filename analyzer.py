from __future__ import annotations

import argparse
import json
import re
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from data_loader import KingdeeDataLoader
from inventory_analyzer import InventoryAnalyzer
from purchase_order_analyzer import PurchaseOrderAnalyzer
from purchase_order_report_builder import PurchaseOrderReportBuilder
from report_builder import ReportBuilder
from sales_outstock_analyzer import SalesOutstockAnalyzer
from sales_outstock_report_builder import SalesOutstockReportBuilder


APP_VERSION = "2026-06-12"
RELEASES_API_URL = "https://api.github.com/repos/LittleBeaverStudio/KingdeeDataAnalyzer/releases/latest"
RELEASES_PAGE_URL = "https://github.com/LittleBeaverStudio/KingdeeDataAnalyzer/releases/latest"


def main() -> int:
    parser = argparse.ArgumentParser(description="KingdeeDataAnalyzer 财务经营分析工具")
    parser.add_argument("--type", choices=["inventory", "purchase", "sales", "finance"], default="inventory", help="分析类型：inventory / purchase / sales")
    parser.add_argument("--start", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--org", help="组织编码")
    parser.add_argument("--exporter", help="data_exporter.py 路径；未指定时自动查找同级导出 Skill")
    parser.add_argument("--excel", help="直接读取已导出的 Excel 文件，跳过金蝶导出")
    parser.add_argument("--json", help="直接读取 analysis_result.json，重新生成报告")
    parser.add_argument("--output-dir", default="outputs", help="报告输出目录")
    parser.add_argument("--pdf", action="store_true", help="兼容旧参数：不再直接生成 PDF，请在 HTML 中点击“打印 / 另存为 PDF”")
    parser.add_argument("--open", action="store_true", help="生成后用系统默认浏览器打开 HTML")
    parser.add_argument("--check-update", action="store_true", help="只检查是否有新版本，不执行分析")
    parser.add_argument("--no-update-check", action="store_true", help="关闭启动时自动检查更新")
    args = parser.parse_args()

    update_info = None
    if not args.no_update_check:
        update_info = check_for_update()
        print_update_notice(update_info)

    if args.check_update:
        if not update_info:
            print(f"当前已是最新版本: {APP_VERSION}")
        return 0

    if args.type == "finance":
        raise SystemExit("当前版本已支持 inventory/purchase/sales；finance 后续扩展。")

    base_dir = Path(__file__).resolve().parent
    output_dir = (base_dir / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.json:
        result = json.loads(Path(args.json).read_text(encoding="utf-8"))
    else:
        start, end = _resolve_dates(args.start, args.end, args.type)
        loader = KingdeeDataLoader(args.exporter)
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


def _version_sort_key(version: str | None) -> list[tuple[int, int | str]]:
    text = str(version or "").strip().lstrip("vV")
    parts = re.split(r"[^0-9A-Za-z]+", text)
    key: list[tuple[int, int | str]] = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part.lower()))
    return key


def is_newer_version(latest_version: str, current_version: str) -> bool:
    return _version_sort_key(latest_version) > _version_sort_key(current_version)


def check_for_update(timeout: int = 3) -> dict[str, str] | None:
    """检查 GitHub 最新 Release。失败时静默返回 None，不影响分析。"""
    try:
        request = urllib.request.Request(
            RELEASES_API_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"KingdeeDataAnalyzer/{APP_VERSION}",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                return None
            data = json.loads(response.read().decode("utf-8"))
        latest_version = str(data.get("tag_name") or "").strip()
        if not latest_version:
            return None
        release_url = data.get("html_url") or RELEASES_PAGE_URL
        if is_newer_version(latest_version, APP_VERSION):
            return {
                "current_version": APP_VERSION,
                "latest_version": latest_version,
                "url": release_url,
            }
    except Exception:
        return None
    return None


def print_update_notice(update_info: dict[str, str] | None) -> None:
    if not update_info:
        return
    print("=" * 60)
    print("发现 KingdeeDataAnalyzer 新版本")
    print(f"当前版本: {update_info['current_version']}")
    print(f"最新版本: {update_info['latest_version']}")
    print(f"更新地址: {update_info['url']}")
    print("=" * 60)


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
