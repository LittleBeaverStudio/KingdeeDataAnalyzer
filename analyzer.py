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


APP_VERSION = "2026-10-19"
RELEASES_API_URL = "https://api.github.com/repos/LittleBeaverStudio/KingdeeDataAnalyzer/releases/latest"
RELEASES_PAGE_URL = "https://github.com/LittleBeaverStudio/KingdeeDataAnalyzer/releases/latest"

# 与 exporter 的 --save-query 共用同一份模板文件；这里只读「组织 / 期间」，不碰凭据。
QUERIES_PATH = Path.home() / ".workbuddy" / "kingdee" / "queries.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="KingdeeDataAnalyzer 财务经营分析工具")
    parser.add_argument("--type", choices=["inventory", "purchase", "sales", "finance"], default="inventory", help="分析类型：inventory / purchase / sales")
    parser.add_argument("--start", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--org", help="组织编码")
    parser.add_argument("--query", help="复用 exporter 已保存的查询模板（只取其中的组织与期间；导出内容仍由 --type 决定）")
    parser.add_argument("--exporter", help="data_exporter.py 路径；未指定时自动查找同级导出 Skill")
    parser.add_argument("--export-timeout", type=int, default=3600, help="实时导出的最长等待秒数，默认 3600")
    parser.add_argument("--excel", help="直接读取已导出的 Excel 文件，跳过金蝶导出")
    parser.add_argument("--json", help="直接读取 analysis_result.json，重新生成报告")
    parser.add_argument("--output-dir", default="outputs", help="报告输出目录")
    parser.add_argument("--pdf", action="store_true", help="兼容旧参数：不再直接生成 PDF，请在 HTML 中点击“打印 / 另存为 PDF”")
    parser.add_argument("--open", action="store_true", help="生成后用系统默认浏览器打开 HTML")
    parser.add_argument("--check-update", action="store_true", help="检查是否有新版本（仅此选项会访问 GitHub），不执行分析")
    args = parser.parse_args()

    if args.export_timeout <= 0:
        parser.error("--export-timeout 必须大于 0")

    if args.check_update:
        update_info = check_for_update()
        if update_info:
            print_update_notice(update_info)
        else:
            print(f"未发现新版本（当前版本: {APP_VERSION}；网络不可用时也会得到此结果）")
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
        org = args.org

        # --query：复用 exporter 的查询模板。只取「组织 / 期间」，
        # 不把 --query 原样传给 exporter —— 否则 analyzer 默认的 --start/--end
        # 会在 exporter 端覆盖模板的 period，模板等于白存。
        if args.query:
            tpl = load_query_template(args.query)
            if tpl:
                if not org and tpl.get("org"):
                    org = str(tpl["org"])
                if not args.start and not args.end:
                    period = str(tpl.get("period") or "").strip()
                    rng = period_to_dates(period) if period else None
                    if rng:
                        start, end = rng
                    elif tpl.get("start") and tpl.get("end"):
                        start, end = str(tpl["start"]), str(tpl["end"])
                print(f"已应用查询模板「{args.query}」：期间 {start} ~ {end}"
                      + (f"，组织 {org}" if org else ""))

        loader = KingdeeDataLoader(args.exporter, export_timeout=args.export_timeout)
        if args.type == "inventory":
            if args.excel:
                summary_df, detail_df = loader.load_inventory_from_excel(args.excel)
                source_excel = Path(args.excel).resolve()
            else:
                summary_df, detail_df, source_excel = loader.load_inventory(start, end, org)

            analyzer = InventoryAnalyzer(summary_df, detail_df)
            result = analyzer.analyze(org_name=org or "Excel导入", period_str=f"{start} ~ {end}")
            result["source_excel"] = str(source_excel)
            analyzer.save_json(output_dir / "analysis_result.json")
        elif args.type == "purchase":
            if args.excel:
                detail_df = loader.load_purchase_orders_from_excel(args.excel)
                source_excel = Path(args.excel).resolve()
            else:
                detail_df, source_excel = loader.load_purchase_orders(start, end, org)

            analyzer = PurchaseOrderAnalyzer(detail_df)
            result = analyzer.analyze(org_name=org or "Excel导入", period_str=f"{start} ~ {end}")
            result["source_excel"] = str(source_excel)
            analyzer.save_json(output_dir / "purchase_order_analysis_result.json")
        else:
            if args.excel:
                detail_df = loader.load_sales_outstock_from_excel(args.excel)
                source_excel = Path(args.excel).resolve()
            else:
                detail_df, source_excel = loader.load_sales_outstock(start, end, org)

            analyzer = SalesOutstockAnalyzer(detail_df)
            result = analyzer.analyze(org_name=org or "Excel导入", period_str=f"{start} ~ {end}")
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


def load_query_template(name: str) -> dict | None:
    """读取 exporter 的查询模板（只读 org/期间，不读凭据）。"""
    if not QUERIES_PATH.is_file():
        print(f"[WARN] 未找到查询模板文件 {QUERIES_PATH}，按命令行参数继续。")
        return None
    try:
        data = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] 无法解析查询模板：{exc}")
        return None
    tpl = data.get(name) if isinstance(data, dict) else None
    if not isinstance(tpl, dict):
        available = ", ".join(data) if isinstance(data, dict) and data else "（无）"
        print(f"[WARN] 未找到查询模板「{name}」，按命令行参数继续。可用：{available}")
        return None
    return tpl


def period_to_dates(period: str) -> tuple[str, str] | None:
    """相对期间 → (start, end)；口径与 exporter 的 --period 保持一致。"""
    if not period:
        return None
    s = str(period).strip().lower()
    today = date.today()

    if "~" in s:
        a, b = (x.strip() for x in s.split("~", 1))
        if re.match(r"\d{4}-\d{2}-\d{2}$", a) and re.match(r"\d{4}-\d{2}-\d{2}$", b):
            return a, b

    m = re.match(r"^(\d{4})-(\d{2})$", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        first = date(y, mo, 1)
        last = (date(y, mo + 1, 1) - timedelta(days=1)) if mo < 12 else (date(y + 1, 1, 1) - timedelta(days=1))
        return first.isoformat(), last.isoformat()

    def month_bounds(y, mo):
        first = date(y, mo, 1)
        last = (date(y, mo + 1, 1) - timedelta(days=1)) if mo < 12 else (date(y + 1, 1, 1) - timedelta(days=1))
        return first, last

    if s in ("last-month", "上月"):
        first, last = month_bounds(*((today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)))
        return first.isoformat(), last.isoformat()
    if s in ("this-month", "本月"):
        first, last = month_bounds(today.year, today.month)
        return first.isoformat(), last.isoformat()
    if s in ("last-quarter", "上季"):
        q = (today.month - 1) // 3
        if q == 0:
            y, q = today.year - 1, 4
        else:
            y = today.year
        first = date(y, (q - 1) * 3 + 1, 1)
        last = date(y, q * 3 + 1, 1) - timedelta(days=1)
        return first.isoformat(), last.isoformat()
    if s in ("this-quarter", "本季"):
        q = (today.month - 1) // 3 + 1
        first = date(today.year, (q - 1) * 3 + 1, 1)
        last = (date(today.year + 1, 1, 1) - timedelta(days=1)) if q == 4 else (date(today.year, q * 3 + 1, 1) - timedelta(days=1))
        return first.isoformat(), last.isoformat()
    if s in ("last-year", "去年"):
        return f"{today.year - 1}-01-01", f"{today.year - 1}-12-31"
    if s in ("this-year", "今年"):
        return f"{today.year}-01-01", f"{today.year}-12-31"
    return None


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
