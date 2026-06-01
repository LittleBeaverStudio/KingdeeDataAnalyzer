from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd


INVENTORY_SUMMARY_FORM = "HS_INOUTSTOCKSUMMARYRPT"
INVENTORY_DETAIL_FORM = "HS_NoDimInOutStockDetailRpt"
PURCHASE_ORDER_DETAIL_FORM = "PUR_PurchaseOrderDetailRpt"
SALES_OUTSTOCK_INVOICE_FORM = "SAL_OutStockInvoiceRpt"

SHEET_NAME_MAP = {
    INVENTORY_SUMMARY_FORM: "存货收发存汇总表",
    INVENTORY_DETAIL_FORM: "存货收发存明细表",
    PURCHASE_ORDER_DETAIL_FORM: "采购订单执行明细表",
    SALES_OUTSTOCK_INVOICE_FORM: "销售出库开票跟踪表",
}


class KingdeeDataLoader:
    """Load Kingdee inventory report data from exporter output or an existing Excel file."""

    def __init__(self, exporter_path: str | os.PathLike | None = None):
        if exporter_path:
            self.exporter_path = Path(exporter_path)
        else:
            self.exporter_path = Path(__file__).resolve().parent.parent / "KingdeeDataExporter" / "data_exporter.py"

        if not self.exporter_path.exists():
            raise FileNotFoundError(f"未找到 KingdeeDataExporter 脚本: {self.exporter_path}")

    def load_inventory(self, start_date: str, end_date: str, org_number: str | None) -> tuple[pd.DataFrame, pd.DataFrame | None, Path]:
        excel_path = self.export_inventory_excel(start_date, end_date, org_number)
        summary_df, detail_df = self.load_inventory_from_excel(excel_path)
        return summary_df, detail_df, excel_path

    def load_purchase_orders(self, start_date: str, end_date: str, org_number: str | None) -> tuple[pd.DataFrame, Path]:
        excel_path = self.export_purchase_order_excel(start_date, end_date, org_number)
        return self.load_purchase_orders_from_excel(excel_path), excel_path

    def load_sales_outstock(self, start_date: str, end_date: str, org_number: str | None) -> tuple[pd.DataFrame, Path]:
        excel_path = self.export_sales_outstock_excel(start_date, end_date, org_number)
        return self.load_sales_outstock_from_excel(excel_path), excel_path

    def export_inventory_excel(self, start_date: str, end_date: str, org_number: str | None) -> Path:
        forms = f"{INVENTORY_SUMMARY_FORM},{INVENTORY_DETAIL_FORM}"
        return self._export_excel(forms, start_date, end_date, org_number, "kingdee_inventory_")

    def export_purchase_order_excel(self, start_date: str, end_date: str, org_number: str | None) -> Path:
        return self._export_excel(PURCHASE_ORDER_DETAIL_FORM, start_date, end_date, org_number, "kingdee_purchase_order_")

    def export_sales_outstock_excel(self, start_date: str, end_date: str, org_number: str | None) -> Path:
        return self._export_excel(SALES_OUTSTOCK_INVOICE_FORM, start_date, end_date, org_number, "kingdee_sales_outstock_")

    def _export_excel(self, forms: str, start_date: str, end_date: str, org_number: str | None, temp_prefix: str) -> Path:
        with tempfile.TemporaryDirectory(prefix=temp_prefix) as tmp_dir:
            tmp_path = Path(tmp_dir)
            before = set(tmp_path.glob("*.xlsx"))
            cmd = [
                sys.executable,
                str(self.exporter_path),
                "--start",
                start_date,
                "--end",
                end_date,
                "--only",
                forms,
                "--no-wechat",
            ]
            if org_number:
                cmd[cmd.index("--only"):cmd.index("--only")] = ["--org", str(org_number)]

            result = subprocess.run(
                cmd,
                cwd=tmp_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                raise RuntimeError("金蝶数据导出失败:\n" + (result.stderr or result.stdout))

            exported = self._find_exported_excel(tmp_path, result.stdout, before)
            if not exported:
                raise FileNotFoundError("金蝶导出完成，但未找到生成的 Excel 文件。")

            output_dir = Path(__file__).resolve().parent / "outputs"
            output_dir.mkdir(exist_ok=True)
            target = output_dir / exported.name
            if target.exists():
                target = output_dir / f"{exported.stem}_{os.getpid()}{exported.suffix}"
            shutil.move(str(exported), str(target))
            return target

    def load_inventory_from_excel(self, excel_path: str | os.PathLike) -> tuple[pd.DataFrame, pd.DataFrame | None]:
        excel_path = Path(excel_path)
        if not excel_path.exists():
            raise FileNotFoundError(f"未找到 Excel 文件: {excel_path}")

        sheets = pd.read_excel(excel_path, sheet_name=None)
        summary_df = self._pick_sheet(sheets, INVENTORY_SUMMARY_FORM)
        detail_df = self._pick_sheet(sheets, INVENTORY_DETAIL_FORM, required=False)

        if summary_df is None or summary_df.empty:
            raise ValueError(f"Excel 中未找到有效的 {SHEET_NAME_MAP[INVENTORY_SUMMARY_FORM]} 数据。")

        return self._clean_dataframe(summary_df), self._clean_dataframe(detail_df) if detail_df is not None else None

    def load_purchase_orders_from_excel(self, excel_path: str | os.PathLike) -> pd.DataFrame:
        excel_path = Path(excel_path)
        if not excel_path.exists():
            raise FileNotFoundError(f"未找到 Excel 文件: {excel_path}")

        sheets = pd.read_excel(excel_path, sheet_name=None)
        df = self._pick_sheet(sheets, PURCHASE_ORDER_DETAIL_FORM, required=False)
        if df is None:
            df = self._pick_purchase_sheet(sheets)
        if df is None or df.empty:
            available = ", ".join(sheets.keys())
            raise ValueError(f"Excel 中未找到有效的采购订单执行明细表。可用工作表: {available}")
        return self._clean_dataframe(df)

    def load_sales_outstock_from_excel(self, excel_path: str | os.PathLike) -> pd.DataFrame:
        excel_path = Path(excel_path)
        if not excel_path.exists():
            raise FileNotFoundError(f"未找到 Excel 文件: {excel_path}")

        sheets = pd.read_excel(excel_path, sheet_name=None)
        df = self._pick_sheet(sheets, SALES_OUTSTOCK_INVOICE_FORM, required=False)
        if df is None:
            df = self._pick_alias_sheet(
                sheets,
                aliases=("销售出库开票跟踪", "销售出库明细", "OutStockInvoice", "SAL_OutStockInvoiceRpt"),
                field_keys=("应收金额", "结算金额", "FRECAMOUNT", "FRECEIPTAMOUNT"),
            )
        if df is None or df.empty:
            available = ", ".join(sheets.keys())
            raise ValueError(f"Excel 中未找到有效的销售出库开票跟踪表。可用工作表: {available}")
        return self._clean_dataframe(df)

    def _pick_sheet(self, sheets: dict[str, pd.DataFrame], form_id: str, required: bool = True) -> pd.DataFrame | None:
        target = SHEET_NAME_MAP[form_id]
        for name, df in sheets.items():
            if name == form_id or target in str(name):
                return df
        if required:
            available = ", ".join(sheets.keys())
            raise ValueError(f"未找到工作表 {target}。可用工作表: {available}")
        return None

    def _pick_purchase_sheet(self, sheets: dict[str, pd.DataFrame]) -> pd.DataFrame | None:
        aliases = ("采购订单执行明细", "PurchaseOrderDetail", "PUR_PurchaseOrderDetailRpt")
        for name, df in sheets.items():
            if any(alias.lower() in str(name).lower() for alias in aliases):
                return df
        if len(sheets) == 1:
            return next(iter(sheets.values()))
        for df in sheets.values():
            joined = "|".join(str(c) for c in df.columns)
            if any(key in joined for key in ("应付金额", "已结算金额", "FPAYAMOUNT", "FPAYBILLAMOUNT")):
                return df
        return None

    def _pick_alias_sheet(self, sheets: dict[str, pd.DataFrame], aliases: tuple[str, ...], field_keys: tuple[str, ...]) -> pd.DataFrame | None:
        for name, df in sheets.items():
            if any(alias.lower() in str(name).lower() for alias in aliases):
                return df
        if len(sheets) == 1:
            return next(iter(sheets.values()))
        for df in sheets.values():
            joined = "|".join(str(c) for c in df.columns)
            if any(key in joined for key in field_keys):
                return df
        return None

    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]
        df = df.dropna(how="all")
        for col in df.columns:
            if df[col].dtype == object:
                cleaned = df[col].astype(str).str.replace(",", "", regex=False).str.strip()
                numeric = pd.to_numeric(cleaned, errors="coerce")
                if numeric.notna().mean() >= 0.7:
                    df[col] = numeric
        return df

    def _find_exported_excel(self, output_dir: Path, stdout: str, before: set[Path]) -> Path | None:
        path_pattern = re.compile(r"([A-Za-z]:\\[^\r\n]+?\.xlsx|/[^\r\n]+?\.xlsx)")
        for match in path_pattern.findall(stdout or ""):
            candidate = Path(match.strip())
            if candidate.exists():
                return candidate

        files = [p for p in output_dir.glob("*.xlsx") if p not in before]
        if not files:
            files = list(output_dir.glob("*.xlsx"))
        return max(files, key=lambda p: p.stat().st_mtime) if files else None
