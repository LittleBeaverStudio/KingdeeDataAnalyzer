from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd


FIELD_ALIASES = {
    "purchase_org": ["采购组织", "FPurchaseOrgId"],
    "order_no": ["订单编号", "FBillNo"],
    "order_date": ["日期", "订单日期", "FDate"],
    "supplier": ["供应商名称", "FSUPPLIERNAME"],
    "material": ["物料名称", "FMATERIALNAME"],
    "delivery_date": ["交货日期", "FDELIVERYDATE"],
    "currency": ["结算币别", "FCurrencyId"],
    "order_qty": ["订货数量", "FOrderQty"],
    "order_amount": ["价税合计", "FOrderAmount"],
    "receive_qty": ["收料数量", "FReceiveQty"],
    "receive_amount": ["收料金额", "FReceiveAmount"],
    "stockin_qty": ["入库数量", "FImportQty"],
    "stockin_amount": ["入库金额", "FImportAmount"],
    "return_qty": ["退料数量", "FReturnQty"],
    "return_amount": ["退料金额", "FReturnAmount"],
    "payable_qty": ["应付数量", "FPAYQTY"],
    "payable_amount": ["应付金额", "FPAYAMOUNT"],
    "preinvoice_amount": ["先开票金额", "FPREINVOICEAMOUNT"],
    "invoice_amount": ["开票金额", "FINVOICEAMOUNT"],
    "prepay_amount": ["预付金额", "FRECPAYBILLAMOUNT"],
    "settled_amount": ["已结算金额", "FPAYBILLAMOUNT"],
    "settlement_adjustment": ["结算调整金额", "FSETADJAMOUNT"],
    "payment_writeoff": ["付款核销金额", "FPAYWRITOFFAMOUNT"],
    "special_writeoff": ["特殊冲销金额", "FSPEWOFFAMOUNT"],
}


class PurchaseOrderAnalyzer:
    """Analyze Kingdee purchase order execution detail data."""

    def __init__(self, detail_df: pd.DataFrame):
        self.raw_df = detail_df.copy()
        self.df = self._normalize(detail_df)
        self.result: dict = {}

    def analyze(self, org_name: str = "未知组织", period_str: str = "") -> dict:
        detail = self.df.copy()
        self.result = {
            "organization": self._organization_label(org_name),
            "period": period_str,
            "summary": self._summary(detail),
            "monthly_trend": self._monthly_trend(detail),
            "supplier_unsettled": self._group_top(detail, "supplier", "供应商"),
            "material_execution": self._group_top(detail, "material", "物料"),
            "purchaser_execution": self._group_top(detail, "purchase_org", "采购组织"),
            "overdue_unreceived": self._overdue_unreceived(detail),
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
        for col in ("order_date", "delivery_date"):
            mapped[col] = pd.to_datetime(mapped[col], errors="coerce")
        for col in self._text_fields():
            mapped[col] = mapped[col].fillna("").astype(str).str.strip()

        mapped["unsettled_amount"] = (mapped["payable_amount"] - mapped["settled_amount"]).clip(lower=0)
        mapped["unreceived_qty"] = (mapped["order_qty"] - mapped["receive_qty"]).clip(lower=0)
        mapped["unstocked_qty"] = (mapped["order_qty"] - mapped["stockin_qty"]).clip(lower=0)
        mapped["receive_rate"] = self._safe_div(mapped["receive_qty"], mapped["order_qty"])
        mapped["stockin_rate"] = self._safe_div(mapped["stockin_qty"], mapped["order_qty"])
        mapped["settlement_rate"] = self._safe_div(mapped["settled_amount"], mapped["payable_amount"])
        mapped["order_month"] = mapped["order_date"].dt.strftime("%Y.%m").fillna("未识别")
        mapped["delivery_overdue"] = (mapped["delivery_date"].notna()) & (mapped["delivery_date"].dt.date < date.today()) & (mapped["unreceived_qty"] > 0)
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
        order_amount = self._sum(df, "order_amount")
        payable_amount = self._sum(df, "payable_amount")
        settled_amount = self._sum(df, "settled_amount")
        unsettled_amount = self._sum(df, "unsettled_amount")
        return {
            "line_count": int(len(df)),
            "order_count": int(df["order_no"].replace("", pd.NA).dropna().nunique()),
            "supplier_count": int(df["supplier"].replace("", pd.NA).dropna().nunique()),
            "material_count": int(df["material"].replace("", pd.NA).dropna().nunique()),
            "order_qty": self._sum(df, "order_qty"),
            "receive_qty": self._sum(df, "receive_qty"),
            "stockin_qty": self._sum(df, "stockin_qty"),
            "order_amount": order_amount,
            "payable_amount": payable_amount,
            "settled_amount": settled_amount,
            "unsettled_amount": unsettled_amount,
            "unsettled_ratio": self._round(unsettled_amount / payable_amount * 100 if payable_amount else 0, 1),
            "receive_rate": self._round(self._sum(df, "receive_qty") / self._sum(df, "order_qty") * 100 if self._sum(df, "order_qty") else 0, 1),
            "stockin_rate": self._round(self._sum(df, "stockin_qty") / self._sum(df, "order_qty") * 100 if self._sum(df, "order_qty") else 0, 1),
            "settlement_rate": self._round(settled_amount / payable_amount * 100 if payable_amount else 0, 1),
            "overdue_line_count": int(df["delivery_overdue"].sum()),
            "overdue_unreceived_qty": self._sum(df[df["delivery_overdue"]], "unreceived_qty"),
        }

    def _monthly_trend(self, df: pd.DataFrame) -> list[dict]:
        grouped = df.groupby("order_month", dropna=False).agg(
            order_amount=("order_amount", "sum"),
            payable_amount=("payable_amount", "sum"),
            settled_amount=("settled_amount", "sum"),
            unsettled_amount=("unsettled_amount", "sum"),
            order_qty=("order_qty", "sum"),
            receive_qty=("receive_qty", "sum"),
        )
        rows = []
        for month, row in grouped.sort_index().iterrows():
            rows.append({"month": str(month), **{k: self._round(v, 2) for k, v in row.to_dict().items()}})
        return rows

    def _group_top(self, df: pd.DataFrame, key: str, fallback: str) -> list[dict]:
        work = df.copy()
        work[key] = work[key].replace("", f"未识别{fallback}")
        grouped = work.groupby(key, dropna=False).agg(
            order_count=("order_no", "nunique"),
            line_count=("order_no", "size"),
            order_qty=("order_qty", "sum"),
            receive_qty=("receive_qty", "sum"),
            stockin_qty=("stockin_qty", "sum"),
            order_amount=("order_amount", "sum"),
            payable_amount=("payable_amount", "sum"),
            settled_amount=("settled_amount", "sum"),
            unsettled_amount=("unsettled_amount", "sum"),
            unreceived_qty=("unreceived_qty", "sum"),
        )
        rows = []
        for name, row in grouped.sort_values("unsettled_amount", ascending=False).head(50).iterrows():
            payable = float(row.get("payable_amount", 0) or 0)
            order_qty = float(row.get("order_qty", 0) or 0)
            rows.append(
                {
                    "name": str(name),
                    "order_count": int(row.get("order_count", 0) or 0),
                    "line_count": int(row.get("line_count", 0) or 0),
                    "order_qty": self._round(row.get("order_qty", 0)),
                    "receive_qty": self._round(row.get("receive_qty", 0)),
                    "stockin_qty": self._round(row.get("stockin_qty", 0)),
                    "order_amount": self._round(row.get("order_amount", 0), 2),
                    "payable_amount": self._round(payable, 2),
                    "settled_amount": self._round(row.get("settled_amount", 0), 2),
                    "unsettled_amount": self._round(row.get("unsettled_amount", 0), 2),
                    "unsettled_ratio": self._round(float(row.get("unsettled_amount", 0) or 0) / payable * 100 if payable else 0, 1),
                    "receive_rate": self._round(float(row.get("receive_qty", 0) or 0) / order_qty * 100 if order_qty else 0, 1),
                    "unreceived_qty": self._round(row.get("unreceived_qty", 0)),
                }
            )
        return rows

    def _overdue_unreceived(self, df: pd.DataFrame) -> list[dict]:
        rows = df[df["delivery_overdue"]].sort_values(["unreceived_qty", "unsettled_amount"], ascending=False).head(50)
        return self._detail_rows(rows)

    def _detail_rows(self, df: pd.DataFrame) -> list[dict]:
        fields = [
            "purchase_org",
            "order_no",
            "order_date",
            "supplier",
            "material",
            "delivery_date",
            "currency",
            "order_qty",
            "receive_qty",
            "stockin_qty",
            "unreceived_qty",
            "order_amount",
            "payable_amount",
            "settled_amount",
            "unsettled_amount",
            "receive_rate",
            "settlement_rate",
        ]
        rows = []
        for _, row in df.iterrows():
            item = {}
            for field in fields:
                value = row.get(field)
                if field in ("order_date", "delivery_date"):
                    item[field] = value.strftime("%Y-%m-%d") if pd.notna(value) else ""
                elif field in self._numeric_fields() or field.endswith("_rate") or field in ("unsettled_amount", "unreceived_qty", "unstocked_qty"):
                    item[field] = self._round(value, 4 if field.endswith("_rate") else 2)
                else:
                    item[field] = "" if pd.isna(value) else str(value)
            rows.append(item)
        return rows

    def _method_notes(self) -> list[str]:
        return [
            "未结算金额 = 应付金额 - 已结算金额；若计算结果小于0，按0计入未结算风险，避免超额结算抵减其他订单。",
            "收料率 = 收料数量 / 订货数量；入库率 = 入库数量 / 订货数量；结算率 = 已结算金额 / 应付金额。",
            "逾期未收料按交货日期早于报告生成日且未收料数量大于0识别，用于提示交付执行风险。",
            "供应商、物料、采购组织排行默认按未结算金额降序，便于优先关注资金占用与待结算事项。",
        ]

    def _organization_label(self, fallback: str) -> str:
        orgs = [
            str(x).strip()
            for x in self.df.get("purchase_org", pd.Series(dtype=str)).dropna().unique().tolist()
            if str(x).strip()
        ]
        if orgs:
            return "、".join(sorted(orgs))
        return fallback or "自动识别组织"

    def _numeric_fields(self) -> set[str]:
        return {
            "order_qty",
            "order_amount",
            "receive_qty",
            "receive_amount",
            "stockin_qty",
            "stockin_amount",
            "return_qty",
            "return_amount",
            "payable_qty",
            "payable_amount",
            "preinvoice_amount",
            "invoice_amount",
            "prepay_amount",
            "settled_amount",
            "settlement_adjustment",
            "payment_writeoff",
            "special_writeoff",
        }

    def _text_fields(self) -> set[str]:
        return {"purchase_org", "order_no", "supplier", "material", "currency"}

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
