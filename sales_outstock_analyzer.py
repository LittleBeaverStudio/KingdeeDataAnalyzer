from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


FIELD_ALIASES = {
    "sale_org": ["销售组织", "FSALEORGNAME"],
    "bill_no": ["单据编号", "编号", "FBILLNO"],
    "bill_type": ["单据类型", "FBILLTYPENAME"],
    "bill_date": ["日期", "FDate"],
    "salesperson": ["销售员", "FSALESNAME"],
    "customer": ["客户名称", "FCUSTOMERNAME"],
    "material": ["物料名称", "FMATERIALNAME"],
    "qty": ["数量", "FREALQTY"],
    "price": ["单价", "FPrice"],
    "amount": ["金额", "FALLAMOUNT"],
    "is_free": ["是否赠品", "FISFREE"],
    "receivable_qty": ["应收数量", "FRECQTY"],
    "receivable_amount": ["应收金额", "FRECAMOUNT"],
    "adjustment_amount": ["调整金额", "FWriteOffAmount"],
    "invoice_qty": ["开票数量", "FINVOECEQTY"],
    "invoice_amount": ["开票金额", "FINVOECEAMOUNT"],
    "receipt_settlement_amount": ["结算金额", "收款结算金额", "FRECEIPTAMOUNT"],
    "settlement_adjustment": ["结算调整金额", "FJSWRITEOFFAMOUNT"],
    "special_writeoff": ["特殊冲销金额", "FChargeOffAmount"],
}


class SalesOutstockAnalyzer:
    """Analyze Kingdee sales outstock invoice tracking data."""

    def __init__(self, detail_df: pd.DataFrame):
        self.raw_df = detail_df.copy()
        self.df = self._normalize(detail_df)
        self.result: dict = {}

    def analyze(self, org_name: str = "未知组织", period_str: str = "") -> dict:
        detail = self.df.copy()
        self.result = {
            "organization": org_name,
            "period": period_str,
            "summary": self._summary(detail),
            "monthly_trend": self._monthly_trend(detail),
            "bill_type_summary": self._group_top(detail, "bill_type", "单据类型"),
            "salesperson_summary": self._group_top(detail, "salesperson", "销售员"),
            "material_summary": self._group_top(detail, "material", "物料"),
            "customer_summary": self._group_top(detail, "customer", "客户"),
            "unsettled_details": self._bill_unsettled_details(detail),
            "detail_rows": self._detail_rows(detail),
            "method_notes": self._method_notes(),
        }
        return self.result

    def save_json(self, filepath: str | Path) -> Path:
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(json.dumps(self.result, ensure_ascii=False, indent=2), encoding="utf-8")
        return filepath

    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        work = df.copy()
        work.columns = [str(c).strip() for c in work.columns]
        mapped = pd.DataFrame(index=work.index)
        for target, aliases in FIELD_ALIASES.items():
            source = self._find_column(work, aliases)
            mapped[target] = work[source] if source else "" if target in self._text_fields() else 0

        for col in self._numeric_fields():
            mapped[col] = pd.to_numeric(mapped[col].astype(str).str.replace(",", "", regex=False).str.strip(), errors="coerce").fillna(0)
        for col in self._text_fields():
            mapped[col] = mapped[col].fillna("").astype(str).str.strip()
        mapped["bill_date"] = pd.to_datetime(mapped["bill_date"], errors="coerce")
        mapped["bill_month"] = mapped["bill_date"].dt.strftime("%Y.%m").fillna("未识别")
        mapped["unsettled_amount"] = mapped["receivable_amount"] - mapped["receipt_settlement_amount"]
        mapped["uninvoiced_amount"] = (mapped["receivable_amount"] - mapped["invoice_amount"]).clip(lower=0)
        mapped["unsettled_qty"] = (mapped["receivable_qty"] - mapped["invoice_qty"]).clip(lower=0)
        mapped["invoice_rate"] = self._safe_div(mapped["invoice_amount"], mapped["receivable_amount"])
        mapped["settlement_rate"] = self._safe_div(mapped["receipt_settlement_amount"], mapped["receivable_amount"])
        mapped["receivable_rate"] = self._safe_div(mapped["receivable_amount"], mapped["amount"])
        mapped["avg_price"] = self._safe_div(mapped["amount"], mapped["qty"])
        return mapped

    def _find_column(self, df: pd.DataFrame, aliases: list[str]) -> str | None:
        normalized = {self._compact(c): c for c in df.columns}
        for alias in aliases:
            key = self._compact(alias)
            if key in normalized:
                return normalized[key]
        for alias in aliases:
            key = self._compact(alias)
            for col in df.columns:
                if key and key in self._compact(col):
                    return col
        return None

    def _compact(self, value: object) -> str:
        return str(value).lower().replace(" ", "").replace("_", "").replace("（", "(").replace("）", ")")

    def _summary(self, df: pd.DataFrame) -> dict:
        receivable = self._sum(df, "receivable_amount")
        invoice = self._sum(df, "invoice_amount")
        settled = self._sum(df, "receipt_settlement_amount")
        unsettled = self._sum(df, "unsettled_amount")
        amount = self._sum(df, "amount")
        qty = self._sum(df, "qty")
        return {
            "line_count": int(len(df)),
            "bill_count": int(df["bill_no"].replace("", pd.NA).dropna().nunique()),
            "customer_count": int(df["customer"].replace("", pd.NA).dropna().nunique()),
            "salesperson_count": int(df["salesperson"].replace("", pd.NA).dropna().nunique()),
            "material_count": int(df["material"].replace("", pd.NA).dropna().nunique()),
            "qty": qty,
            "amount": amount,
            "receivable_qty": self._sum(df, "receivable_qty"),
            "receivable_amount": receivable,
            "invoice_amount": invoice,
            "receipt_settlement_amount": settled,
            "unsettled_amount": unsettled,
            "uninvoiced_amount": self._sum(df, "uninvoiced_amount"),
            "settlement_adjustment": self._sum(df, "settlement_adjustment"),
            "special_writeoff": self._sum(df, "special_writeoff"),
            "invoice_rate": self._round(invoice / receivable * 100 if receivable else 0, 1),
            "settlement_rate": self._round(settled / receivable * 100 if receivable else 0, 1),
            "unsettled_ratio": self._round(unsettled / receivable * 100 if receivable else 0, 1),
            "avg_price": self._round(amount / qty if qty else 0, 2),
        }

    def _monthly_trend(self, df: pd.DataFrame) -> list[dict]:
        grouped = df.groupby("bill_month", dropna=False).agg(
            qty=("qty", "sum"),
            amount=("amount", "sum"),
            receivable_amount=("receivable_amount", "sum"),
            invoice_amount=("invoice_amount", "sum"),
            receipt_settlement_amount=("receipt_settlement_amount", "sum"),
            unsettled_amount=("unsettled_amount", "sum"),
        )
        rows = []
        for month, row in grouped.sort_index().iterrows():
            rows.append({"month": str(month), **{k: self._round(v, 2) for k, v in row.to_dict().items()}})
        return rows

    def _group_top(self, df: pd.DataFrame, key: str, fallback: str) -> list[dict]:
        work = df.copy()
        work[key] = work[key].replace("", f"未识别{fallback}")
        grouped = work.groupby(key, dropna=False).agg(
            bill_count=("bill_no", "nunique"),
            line_count=("bill_no", "size"),
            qty=("qty", "sum"),
            amount=("amount", "sum"),
            receivable_amount=("receivable_amount", "sum"),
            invoice_amount=("invoice_amount", "sum"),
            receipt_settlement_amount=("receipt_settlement_amount", "sum"),
            unsettled_amount=("unsettled_amount", "sum"),
            uninvoiced_amount=("uninvoiced_amount", "sum"),
        )
        rows = []
        grouped["abs_unsettled_amount"] = grouped["unsettled_amount"].abs()
        for name, row in grouped.sort_values(["abs_unsettled_amount", "receivable_amount"], ascending=False).head(50).iterrows():
            receivable = float(row.get("receivable_amount", 0) or 0)
            rows.append(
                {
                    "name": str(name),
                    "bill_count": int(row.get("bill_count", 0) or 0),
                    "line_count": int(row.get("line_count", 0) or 0),
                    "qty": self._round(row.get("qty", 0)),
                    "amount": self._round(row.get("amount", 0), 2),
                    "receivable_amount": self._round(receivable, 2),
                    "invoice_amount": self._round(row.get("invoice_amount", 0), 2),
                    "receipt_settlement_amount": self._round(row.get("receipt_settlement_amount", 0), 2),
                    "unsettled_amount": self._round(row.get("unsettled_amount", 0), 2),
                    "uninvoiced_amount": self._round(row.get("uninvoiced_amount", 0), 2),
                    "invoice_rate": self._round(float(row.get("invoice_amount", 0) or 0) / receivable * 100 if receivable else 0, 1),
                    "settlement_rate": self._round(float(row.get("receipt_settlement_amount", 0) or 0) / receivable * 100 if receivable else 0, 1),
                    "unsettled_ratio": self._round(float(row.get("unsettled_amount", 0) or 0) / receivable * 100 if receivable else 0, 1),
                }
            )
        return rows

    def _bill_unsettled_details(self, df: pd.DataFrame) -> list[dict]:
        work = df.copy()
        work["bill_no"] = work["bill_no"].replace("", "未识别单据")
        grouped = work.groupby("bill_no", dropna=False).agg(
            bill_date=("bill_date", "min"),
            bill_type=("bill_type", "first"),
            salesperson=("salesperson", "first"),
            customer=("customer", "first"),
            line_count=("bill_no", "size"),
            qty=("qty", "sum"),
            amount=("amount", "sum"),
            receivable_amount=("receivable_amount", "sum"),
            invoice_amount=("invoice_amount", "sum"),
            receipt_settlement_amount=("receipt_settlement_amount", "sum"),
            unsettled_amount=("unsettled_amount", "sum"),
            uninvoiced_amount=("uninvoiced_amount", "sum"),
        )
        grouped["abs_unsettled_amount"] = grouped["unsettled_amount"].abs()
        rows = []
        for bill_no, row in grouped.sort_values(["abs_unsettled_amount", "receivable_amount"], ascending=False).head(100).iterrows():
            receivable = float(row.get("receivable_amount", 0) or 0)
            bill_date = row.get("bill_date")
            rows.append(
                {
                    "bill_no": str(bill_no),
                    "bill_date": bill_date.strftime("%Y-%m-%d") if pd.notna(bill_date) else "",
                    "bill_type": str(row.get("bill_type", "") or ""),
                    "salesperson": str(row.get("salesperson", "") or ""),
                    "customer": str(row.get("customer", "") or ""),
                    "line_count": int(row.get("line_count", 0) or 0),
                    "qty": self._round(row.get("qty", 0)),
                    "amount": self._round(row.get("amount", 0), 2),
                    "receivable_amount": self._round(receivable, 2),
                    "invoice_amount": self._round(row.get("invoice_amount", 0), 2),
                    "receipt_settlement_amount": self._round(row.get("receipt_settlement_amount", 0), 2),
                    "unsettled_amount": self._round(row.get("unsettled_amount", 0), 2),
                    "uninvoiced_amount": self._round(row.get("uninvoiced_amount", 0), 2),
                    "settlement_rate": self._round(float(row.get("receipt_settlement_amount", 0) or 0) / receivable if receivable else 0, 4),
                }
            )
        return rows

    def _detail_rows(self, df: pd.DataFrame) -> list[dict]:
        fields = [
            "sale_org",
            "bill_no",
            "bill_type",
            "bill_date",
            "salesperson",
            "customer",
            "material",
            "qty",
            "price",
            "amount",
            "is_free",
            "receivable_qty",
            "receivable_amount",
            "adjustment_amount",
            "invoice_qty",
            "invoice_amount",
            "receipt_settlement_amount",
            "settlement_adjustment",
            "special_writeoff",
            "unsettled_amount",
            "uninvoiced_amount",
            "invoice_rate",
            "settlement_rate",
        ]
        rows = []
        for _, row in df.iterrows():
            item = {}
            for field in fields:
                value = row.get(field)
                if field == "bill_date":
                    item[field] = value.strftime("%Y-%m-%d") if pd.notna(value) else ""
                elif field in self._numeric_fields() or field in ("unsettled_amount", "uninvoiced_amount", "invoice_rate", "settlement_rate"):
                    item[field] = self._round(value, 4 if field.endswith("_rate") else 2)
                else:
                    item[field] = "" if pd.isna(value) else str(value)
            rows.append(item)
        return rows

    def _method_notes(self) -> list[str]:
        return [
            "未结算金额 = 应收金额 - 收款结算金额；该字段按原始差额保留，可能为负数。",
            "未开票金额 = 应收金额 - 开票金额；用于观察出库后开票推进情况。",
            "开票率 = 开票金额 / 应收金额；结算率 = 收款结算金额 / 应收金额；未结算占比 = 未结算金额 / 应收金额。",
            "单据类型、销售员、物料、客户维度默认按未结算金额绝对值和应收金额降序，便于同时识别待结算和超结算/退货影响。",
            "是否赠品来自金蝶原始字段，赠品行仍纳入数量统计；金额与应收金额以金蝶报表实际返回值为准。",
        ]

    def _numeric_fields(self) -> set[str]:
        return {
            "qty",
            "price",
            "amount",
            "receivable_qty",
            "receivable_amount",
            "adjustment_amount",
            "invoice_qty",
            "invoice_amount",
            "receipt_settlement_amount",
            "settlement_adjustment",
            "special_writeoff",
        }

    def _text_fields(self) -> set[str]:
        return {"sale_org", "bill_no", "bill_type", "salesperson", "customer", "material", "is_free"}

    def _safe_div(self, numerator: pd.Series, denominator: pd.Series) -> pd.Series:
        numerator = pd.to_numeric(numerator, errors="coerce").fillna(0)
        denominator = pd.to_numeric(denominator, errors="coerce").fillna(0)
        result = numerator.div(denominator.where(denominator != 0))
        return result.fillna(0).astype(float)

    def _sum(self, df: pd.DataFrame, col: str) -> float:
        return self._round(df[col].sum() if col in df.columns else 0, 2)

    def _round(self, value, digits: int = 2) -> float:
        try:
            result = round(float(value or 0), digits)
        except Exception:
            result = 0.0
        if digits == 0:
            return int(result)
        return result
