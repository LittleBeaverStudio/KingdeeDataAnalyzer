from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


TEXT_COLUMNS = {"期间", "单据日期", "单据编号", "业务类型", "单据类型", "物料编码", "物料名称", "物料分组", "仓库"}


class InventoryAnalyzer:
    """Inventory analysis for Kingdee stock in/out summary and detail reports."""

    def __init__(self, summary_df: pd.DataFrame, detail_df: pd.DataFrame | None = None):
        self.summary_df = self._normalize(summary_df)
        self.detail_df = self._normalize(detail_df) if detail_df is not None else None
        self.result: dict = {}
        self.forecast_months: list[str] = []
        self.inactive_materials: list[dict] = []

    def analyze(self, org_name: str = "未知组织", period_str: str = "") -> dict:
        monthly_trend = self._calc_monthly_trend()
        self.forecast_months = self._next_months(monthly_trend, 3)
        material_forecasts = self._calc_material_stats()
        procurement = self._calc_procurement_suggestions(material_forecasts)
        total_forecast = self._calc_total_forecast(monthly_trend)

        self.result = {
            "organization": org_name,
            "period": period_str,
            "forecast_months": self.forecast_months,
            "monthly_trend": monthly_trend,
            "total_forecast": total_forecast,
            "doc_type_breakdown": self._calc_doc_type_breakdown(),
            "material_forecasts": material_forecasts,
            "inactive_material_summary": self._calc_inactive_material_summary(),
            "inactive_materials": self.inactive_materials,
            "procurement_suggestions": procurement,
            "group_forecasts": self._calc_group_forecasts(material_forecasts),
            "trend_summary": self._calc_trend_summary(material_forecasts),
            "procurement_summary_by_priority": self._calc_procurement_summary(procurement, "priority"),
            "procurement_summary_by_action": self._calc_procurement_summary(procurement, "purchase_timing"),
            "method_notes": self._method_notes(),
        }
        self.result["summary"] = self._calc_summary(monthly_trend, total_forecast, procurement)
        return self.result

    def save_json(self, filepath: str | Path) -> Path:
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with filepath.open("w", encoding="utf-8") as f:
            json.dump(self.result, f, ensure_ascii=False, indent=2)
        return filepath

    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]
        for col in df.columns:
            if col in TEXT_COLUMNS:
                continue
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        return df

    def _calc_monthly_trend(self) -> dict:
        if self.detail_df is not None and not self.detail_df.empty and "期间" in self.detail_df.columns:
            df = self.detail_df.copy()
            df["期间"] = df["期间"].map(self._period_label)
            return self._monthly_from_df(df)

        df = self.summary_df.copy()
        if "期间" in df.columns:
            df["期间"] = df["期间"].map(self._period_label)
            return self._monthly_from_df(df)

        return {
            "合计": {
                "income_qty": self._sum(df, "收入数量"),
                "income_amt": self._sum(df, "收入金额"),
                "qty": self._sum(df, "发出数量"),
                "amount": self._sum(df, "发出金额"),
            }
        }

    def _monthly_from_df(self, df: pd.DataFrame) -> dict:
        grouped = df.groupby("期间", dropna=True).agg(
            income_qty=("收入数量", "sum"),
            income_amt=("收入金额", "sum"),
            qty=("发出数量", "sum"),
            amount=("发出金额", "sum"),
        )
        return {str(period): {k: self._round(v) for k, v in row.to_dict().items()} for period, row in grouped.sort_index().iterrows()}

    def _calc_doc_type_breakdown(self) -> list[dict]:
        if self.detail_df is None or self.detail_df.empty or "单据类型" not in self.detail_df.columns:
            return []

        df = self.detail_df.copy()
        df["期间"] = df["期间"].map(self._period_label) if "期间" in df.columns else "合计"
        total_out = self._sum(df, "发出数量")
        current_period = sorted(df["期间"].dropna().astype(str).unique())[-1] if "期间" in df.columns else "合计"

        groups = (
            df.groupby(["单据类型", "业务类型"], dropna=False)["发出数量"]
            .sum()
            .reset_index()
            .sort_values("发出数量", ascending=False)
        )
        rows = []
        for _, row in groups.iterrows():
            doc_type = str(row.get("单据类型", "") or "未分类")
            biz_type = str(row.get("业务类型", "") or "未分类")
            qty = float(row.get("发出数量", 0) or 0)
            mask = (df["单据类型"].astype(str) == doc_type) & (df["业务类型"].astype(str) == biz_type)
            by_month = df[mask].groupby("期间")["发出数量"].sum() if "期间" in df.columns else pd.Series(dtype=float)
            recent = by_month.tail(3)
            current = float(by_month.get(current_period, 0))
            rows.append(
                {
                    "doc_type": doc_type,
                    "biz_type": biz_type,
                    "total_12m": self._round(qty),
                    "pct": self._round(qty / total_out * 100, 1) if total_out else 0,
                    "avg_monthly": self._round(qty / max(len(by_month), 1), 1),
                    "ma3": self._round(recent.mean() if len(recent) else 0, 1),
                    "current_month_val": self._round(current),
                    "current_month_pct": self._round(current / total_out * 100, 1) if total_out else 0,
                }
            )
        return rows

    def _calc_material_stats(self) -> list[dict]:
        source = self.detail_df if self.detail_df is not None and not self.detail_df.empty else self.summary_df
        monthly = self._material_monthly(source)
        summary = self._material_summary()
        materials = []

        for code, row in summary.iterrows():
            out_qty = float(row.get("发出数量", 0) or 0)
            if out_qty <= 0:
                self.inactive_materials.append(
                    {
                        "code": str(code),
                        "name": str(row.get("物料名称", "")),
                        "group": str(row.get("物料分组", "未分类") or "未分类"),
                        "end_qty": self._round(row.get("期末数量", 0)),
                        "end_amt": self._round(row.get("期末金额", 0)),
                        "income_total_12m": self._round(row.get("收入数量", 0)),
                        "income_amt_total_12m": self._round(row.get("收入金额", 0)),
                    }
                )
                continue
            series = monthly.get(str(code), pd.Series(dtype=float))
            forecast_pack = self._forecast_series(series)
            ma3 = float(series.tail(3).mean()) if len(series) else out_qty / 12
            long_avg = out_qty / max(len(series), 1)
            materials.append(
                {
                    "code": str(code),
                    "name": str(row.get("物料名称", "")),
                    "group": str(row.get("物料分组", "未分类") or "未分类"),
                    "total_12m": self._round(out_qty),
                    "avg_monthly": self._round(long_avg, 2),
                    "ma3": self._round(ma3, 2),
                    "recent_6m_total": self._round(float(series.tail(6).sum()) if len(series) else out_qty),
                    "forecast": forecast_pack["forecast"],
                    "forecast_components": forecast_pack["components"],
                    "forecast_total": self._round(sum(forecast_pack["forecast"].values()), 2),
                    "forecast_method": forecast_pack["method"],
                    "trend": self._trend_label(series),
                    "income_total_12m": self._round(row.get("收入数量", 0)),
                    "income_amt_total_12m": self._round(row.get("收入金额", 0)),
                    "out_amt_total_12m": self._round(row.get("发出金额", 0)),
                    "end_qty": self._round(row.get("期末数量", 0)),
                    "end_amt": self._round(row.get("期末金额", 0)),
                }
            )

        materials.sort(key=lambda x: x["total_12m"], reverse=True)
        for idx, item in enumerate(materials, 1):
            item["rank"] = idx
        self.inactive_materials.sort(key=lambda x: float(x.get("end_amt", 0) or 0), reverse=True)
        return materials

    def _calc_inactive_material_summary(self) -> dict:
        count = len(self.inactive_materials)
        end_qty = sum(float(x.get("end_qty", 0) or 0) for x in self.inactive_materials)
        end_amt = sum(float(x.get("end_amt", 0) or 0) for x in self.inactive_materials)
        stocked = sum(1 for x in self.inactive_materials if float(x.get("end_qty", 0) or 0) > 0)
        return {
            "material_count": count,
            "stocked_count": stocked,
            "end_qty": self._round(end_qty, 1),
            "end_amt": self._round(end_amt, 1),
        }

    def _material_monthly(self, df: pd.DataFrame) -> dict[str, pd.Series]:
        if df is None or df.empty or "物料编码" not in df.columns:
            return {}
        work = df.copy()
        if "期间" not in work.columns:
            work["期间"] = "合计"
        work["期间"] = work["期间"].map(self._period_label)
        pivot = work.pivot_table(index="期间", columns="物料编码", values="发出数量", aggfunc="sum").fillna(0)
        return {str(code): pivot[code].sort_index() for code in pivot.columns}

    def _material_summary(self) -> pd.DataFrame:
        df = self.summary_df.copy()
        if "物料编码" not in df.columns:
            raise ValueError("汇总表缺少“物料编码”列，无法进行库存分析。")
        agg = {
            "物料名称": "first",
            "物料分组": "first",
            "收入数量": "sum",
            "收入金额": "sum",
            "发出数量": "sum",
            "发出金额": "sum",
            "期末数量": "sum",
            "期末金额": "sum",
        }
        available = {k: v for k, v in agg.items() if k in df.columns}
        return df.groupby("物料编码", dropna=False).agg(available)

    def _calc_procurement_suggestions(self, materials: list[dict]) -> list[dict]:
        rows = []
        for item in materials:
            avg_monthly = float(item["avg_monthly"])
            if avg_monthly < 1:
                continue
            daily = avg_monthly / 30
            current_stock = float(item.get("end_qty", 0) or 0)
            days = current_stock / daily if daily > 0 else 9999
            demand_std = max(abs(float(item.get("ma3", 0)) - avg_monthly), avg_monthly * 0.25)
            safety_stock = 1.64 * demand_std
            reorder_point = avg_monthly + safety_stock
            suggested = max(0, item["forecast_total"] + safety_stock - current_stock)
            suggested = math.ceil(suggested / 10) * 10 if suggested > 0 else 0

            if days <= 45:
                priority = "紧急"
            elif days <= 90:
                priority = "关注"
            elif days <= 180:
                priority = "正常"
            else:
                priority = "充裕"

            if suggested > 0 and days <= 45:
                timing = "立即采购"
            elif suggested > 0 and days <= 90:
                timing = "近期采购"
            elif suggested > 0:
                timing = "按计划补货"
            elif days <= 45:
                timing = "人工复核"
            else:
                timing = "暂缓采购"

            rows.append(
                {
                    "code": item["code"],
                    "name": item["name"],
                    "group": item["group"],
                    "current_stock": self._round(current_stock),
                    "current_end_amt": self._round(item.get("end_amt", 0)),
                    "avg_monthly_consumption": self._round(avg_monthly, 1),
                    "avg_daily_consumption": self._round(daily, 2),
                    "days_of_supply": self._round(days, 1),
                    "safety_stock": self._round(safety_stock, 1),
                    "reorder_point": self._round(reorder_point, 1),
                    "forecast_total": self._round(item["forecast_total"], 1),
                    "suggested_order_qty": int(suggested),
                    "purchase_timing": timing,
                    "priority": priority,
                }
            )

        priority_order = {"紧急": 0, "关注": 1, "正常": 2, "充裕": 3}
        rows.sort(key=lambda x: (-x["suggested_order_qty"], priority_order[x["priority"]], x["days_of_supply"]))
        for idx, row in enumerate(rows, 1):
            row["rank"] = idx
        return rows

    def _calc_total_forecast(self, monthly_trend: dict) -> dict:
        values = [v["qty"] for _, v in sorted(monthly_trend.items()) if isinstance(v.get("qty"), (int, float))]
        holt = self._forecast_values(values, method="holt")
        recent = self._forecast_values(values, method="recent")
        long_avg = self._forecast_values(values, method="long_avg")
        ensemble = [max(0, holt[i] * 0.35 + recent[i] * 0.45 + long_avg[i] * 0.20) for i in range(3)]
        return {
            "holt": self._month_dict(holt),
            "recent_ma": self._month_dict(recent),
            "long_avg": self._month_dict(long_avg),
            "ensemble": self._month_dict(ensemble),
        }

    def _calc_group_forecasts(self, materials: list[dict]) -> list[dict]:
        groups: dict[str, dict] = {}
        for item in materials:
            group = item.get("group") or "未分类"
            groups.setdefault(group, {"group": group, "total_12m": 0, "forecast": {m: 0 for m in self.forecast_months}})
            groups[group]["total_12m"] += item["total_12m"]
            for month, value in item["forecast"].items():
                groups[group]["forecast"][month] = groups[group]["forecast"].get(month, 0) + value
        rows = list(groups.values())
        for row in rows:
            row["total_12m"] = self._round(row["total_12m"])
            row["forecast"] = {k: self._round(v, 1) for k, v in row["forecast"].items()}
        return sorted(rows, key=lambda x: x["total_12m"], reverse=True)

    def _calc_trend_summary(self, materials: list[dict]) -> list[dict]:
        labels = ["上升", "平稳", "下降"]
        rows = []
        for label in labels:
            subset = [m for m in materials if label in str(m.get("trend", ""))]
            rows.append(
                {
                    "trend": label,
                    "material_count": len(subset),
                    "total_12m": self._round(sum(m.get("total_12m", 0) for m in subset)),
                    "forecast_total": self._round(sum(m.get("forecast_total", 0) for m in subset)),
                }
            )
        return rows

    def _calc_procurement_summary(self, procurement: list[dict], key: str) -> list[dict]:
        if not procurement:
            return []
        df = pd.DataFrame(procurement)
        grouped = df.groupby(key, dropna=False).agg(
            material_count=("code", "count"),
            suggested_order_qty=("suggested_order_qty", "sum"),
            forecast_total=("forecast_total", "sum"),
        )
        order = {
            "紧急": 0,
            "关注": 1,
            "正常": 2,
            "充裕": 3,
            "立即采购": 0,
            "近期采购": 1,
            "按计划补货": 2,
            "人工复核": 3,
            "暂缓采购": 4,
        }
        rows = []
        for name, row in grouped.reset_index().iterrows():
            label = row[key]
            rows.append(
                {
                    key: str(label),
                    "material_count": int(row["material_count"]),
                    "suggested_order_qty": int(row["suggested_order_qty"]),
                    "forecast_total": self._round(row["forecast_total"], 1),
                    "sort_order": order.get(str(label), 99),
                }
            )
        return sorted(rows, key=lambda x: x["sort_order"])

    def _calc_summary(self, monthly_trend: dict, total_forecast: dict, procurement: list[dict]) -> dict:
        qtys = {k: float(v.get("qty", 0)) for k, v in monthly_trend.items()}
        income_qty = sum(float(v.get("income_qty", 0)) for v in monthly_trend.values())
        income_amt = sum(float(v.get("income_amt", 0)) for v in monthly_trend.values())
        out_amt = sum(float(v.get("amount", 0)) for v in monthly_trend.values())
        total_qty = sum(qtys.values())
        months = max(len(qtys), 1)
        ensemble = total_forecast.get("ensemble", {})
        forecast_total = sum(ensemble.values())
        sorted_qty = sorted(qtys.items(), key=lambda x: x[1])
        return {
            "total_income_12m": self._round(income_qty, 1),
            "total_income_amt_12m": self._round(income_amt, 1),
            "total_qty_12m": self._round(total_qty, 1),
            "total_out_amt_12m": self._round(out_amt, 1),
            "avg_monthly": self._round(total_qty / months, 1),
            "peak_month": max(qtys, key=qtys.get) if qtys else "",
            "peak_value": self._round(max(qtys.values()) if qtys else 0),
            "trough_month": sorted_qty[0][0] if sorted_qty else "",
            "trough_value": self._round(sorted_qty[0][1] if sorted_qty else 0),
            "forecast_total": self._round(forecast_total, 1),
            "forecast_avg_monthly": self._round(forecast_total / 3, 1),
            "trend_direction": "上升" if len(qtys) >= 2 and list(qtys.values())[-1] >= list(qtys.values())[0] else "下降",
            "procurement_summary": {
                "urgent_count": sum(1 for p in procurement if p["priority"] == "紧急"),
                "watch_count": sum(1 for p in procurement if p["priority"] == "关注"),
                "total_suggested_order_qty": int(sum(p["suggested_order_qty"] for p in procurement)),
            },
        }

    def _forecast_series(self, series: pd.Series) -> dict:
        values = [float(v) for v in series.tolist()]
        holt = self._forecast_values(values, method="holt")
        recent = self._forecast_values(values, method="recent")
        long_avg = self._forecast_values(values, method="long_avg")

        clean = [max(0, float(v)) for v in values if pd.notna(v)]
        recent_3 = clean[-3:] if len(clean) >= 3 else clean
        recent_6 = clean[-6:] if len(clean) >= 6 else clean
        recent_avg = float(np.mean(recent_3)) if recent_3 else 0
        active_recently = sum(recent_6) > 0

        forecast_values = []
        for idx in range(3):
            value = holt[idx] * 0.25 + recent[idx] * 0.55 + long_avg[idx] * 0.20
            if active_recently and recent_avg > 0:
                value = max(value, recent_avg * 0.5)
            forecast_values.append(max(0, value))

        return {
            "forecast": self._month_dict(forecast_values),
            "components": {
                "holt": self._month_dict(holt),
                "recent_ma": self._month_dict(recent),
                "long_avg": self._month_dict(long_avg),
                "recent_floor": self._round(recent_avg * 0.5 if active_recently else 0, 1),
            },
            "method": "保守集成预测：Holt趋势25% + 近3月均值55% + 长期月均20%；近期仍有消耗时设置近3月均值50%的预测下限。",
        }

    def _forecast_values(self, values: list[float], method: str) -> list[float]:
        clean = [max(0, float(v)) for v in values if pd.notna(v)]
        if not clean:
            clean = [0]
        if method == "long_avg":
            avg = float(np.mean(clean))
            return [avg, avg, avg]
        if method == "recent":
            recent = clean[-3:] if len(clean) >= 3 else clean
            avg = float(np.mean(recent))
            trend = (recent[-1] - recent[0]) / max(len(recent) - 1, 1) if len(recent) > 1 else 0
            return [max(0, avg + trend * 0.25 * (i + 1)) for i in range(3)]

        level = clean[0]
        trend = clean[1] - clean[0] if len(clean) > 1 else 0
        alpha, beta = 0.25, 0.10
        for value in clean[1:]:
            prev = level
            level = alpha * value + (1 - alpha) * (level + trend)
            trend = beta * (level - prev) + (1 - beta) * trend
        return [max(0, level + trend * (i + 1)) for i in range(3)]

    def _month_dict(self, values: list[float]) -> dict:
        return {month: self._round(values[idx], 1) for idx, month in enumerate(self.forecast_months)}

    def _trend_label(self, series: pd.Series) -> str:
        if len(series) < 2:
            return "→ 平稳"
        first = float(series.head(3).mean())
        last = float(series.tail(3).mean())
        if last > first * 1.15:
            return "↑ 上升"
        if last < first * 0.85:
            return "↓ 下降"
        return "→ 平稳"

    def _method_notes(self) -> dict:
        return {
            "forecast": [
                "单物料预测采用保守集成预测：Holt趋势25% + 近3月均值55% + 长期月均20%。",
                "Holt趋势使用双指数平滑：先维护水平值 level 和趋势值 trend。每个月更新 level = α×本月消耗 + (1-α)×(上月level+上月trend)，trend = β×(level-上月level) + (1-β)×上月trend。本报告取 α=0.25、β=0.10，再用 level + trend×未来期数 得到未来月份趋势值。",
                "近3月均值反映最新业务节奏，长期月均用于防止短期波动过度影响预测，Holt用于识别趋势。",
                "如果近6个月仍有消耗，则未来单月预测不低于近3月均值的50%，避免仍在消耗的物料被趋势外推压到0。",
                "如果近6个月完全无消耗，才允许预测降至0。",
            ],
            "procurement": [
                "日均消耗 = 月均消耗 / 30。",
                "可撑天数 = 当前库存 / 日均消耗。",
                "安全库存 = max(|近3月均值 - 月均消耗|, 月均消耗25%) × 1.64，约对应90%服务水平。",
                "再订点 = 月均消耗 × 1个月采购提前期 + 安全库存。",
                "建议采购量 = max(0, 未来3个月预测消耗 + 安全库存 - 当前库存)，并按10的倍数向上取整。",
                "采购标签优先由建议采购量决定：建议采购量为0时不显示立即采购；若库存风险很高但预测需求不足，则标记为人工复核。",
            ],
        }

    def _next_months(self, monthly_trend: dict, count: int) -> list[str]:
        labels = sorted([k for k in monthly_trend if re_match_month(k)])
        if labels:
            last = pd.Period(labels[-1], freq="M")
        else:
            last = pd.Period(pd.Timestamp.today(), freq="M")
        return [str(last + i) for i in range(1, count + 1)]

    def _period_label(self, value) -> str:
        text = str(value).strip()
        if not text or text.lower() == "nan":
            return ""
        if re_match_month(text):
            return text[:7]
        numeric = pd.to_numeric(text, errors="coerce")
        if pd.notna(numeric):
            num = int(numeric)
            if 1 <= num <= 12:
                return f"{num:02d}"
            text = str(num)
        parsed = pd.to_datetime(text, errors="coerce")
        if pd.notna(parsed):
            return parsed.strftime("%Y-%m")
        return text

    def _sum(self, df: pd.DataFrame, col: str) -> float:
        if col not in df.columns:
            return 0.0
        return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())

    def _round(self, value, digits: int = 2):
        try:
            value = float(value)
            if math.isnan(value) or math.isinf(value):
                return 0
            rounded = round(value, digits)
            return int(rounded) if digits == 0 else rounded
        except Exception:
            return 0


def re_match_month(text: str) -> bool:
    return isinstance(text, str) and len(text) >= 7 and text[4] == "-" and text[:4].isdigit() and text[5:7].isdigit()
