---
name: kingdee-data-analyzer
slug: kingdee-data-analyzer
displayName: 金蝶云星空经营分析
version: 1.2.1
description: 金蝶云星空经营数据分析技能。仅当用户明确要求分析金蝶云星空或 K3 Cloud 的库存、采购订单、销售出库、开票、结算等经营数据时使用；可读取 kingdee-data-exporter 导出的 Excel，也可自动调用同级导出技能实时取数，并生成 HTML 报告、全量明细 Excel 和结构化 JSON。
license: 小河狸非转售许可 1.0（企业内部使用免费，转售收费需授权）
---

## 许可与使用范围

本 Skill 采用「小河狸工作室非转售许可 1.0」，完整条款见本目录 `LICENSE` 文件。

- ✅ **免费使用**：
  - 个人学习、研究或个人事务；
  - **企业内部使用**——某一组织（无论是否为营利单位）为**其自身**业务运营而使用，包括内部办公、内部财务与会计处理、内部管理与报表、内部系统集成；同一控股关联实体使用视同内部使用。
- ✅ 可为上述用途自行修改本 Skill。
- ❌ **须另行取得书面授权**：对外销售、出租、许可；集成进对外收费的产品或服务；托管 / SaaS / 代运营；打包进收费课程、付费社群或付费安装包；收费的实施与咨询培训；**以及利用本 Skill 向任何第三方交付成果或提供服务**（含代理记账、为客户提供账目或报表服务等）。
- 📌 **区分标准只有一条**：**是否以本 Skill 向本组织之外的第三方交付成果或提供服务**。仅为自身业务使用 → 免费；向第三方交付或服务 → 需授权。
- 📌 再分发须保留本许可、版权声明与来源：小河狸工作室 LittleBeaverStudio · https://littlebeaver.top

**商业授权申请**：https://littlebeaver.top （邮箱 yk.niu@outlook.com）


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

## 权限与行为声明

运行本技能前请知悉其能力范围：

- **本地文件读写**：读取输入的 Excel/JSON；在 `outputs/` 写入 HTML 报告、明细 Excel 和分析 JSON。
- **子进程执行**：实时取数时以子进程调用同级或 `--exporter` 指定的 `kingdee-data-exporter/data_exporter.py`。执行前会核验文件名和 `SKILL.md` 身份，并打印脚本路径与导出参数；默认等待上限为 3600 秒。
- **配置复用**：实时取数直接使用导出技能目录中的 `config.py`，不要求在分析技能中重复配置账号。
- **网络访问**：读取本地 Excel/JSON 时不访问网络；实时取数时由导出技能连接用户配置的金蝶服务器；仅显式传入 `--check-update` 时访问 GitHub Releases API。
- **打开浏览器**：仅显式传入 `--open` 时用系统默认浏览器打开生成的 HTML。
- 所有分析在本地完成，不上传任何业务数据。

## 安装依赖

在技能目录中执行：

```bash
python -m pip install -r requirements.txt
```

实时取数还需要安装并配置 `kingdee-data-exporter`。程序会自动查找以下同级目录：

- `kingdee-data-exporter/`
- `KingdeeDataExporter/`

安装位置不同时，也可以用 `--exporter` 指定 `data_exporter.py` 的完整路径。程序会核验它确实属于 `kingdee-data-exporter`。

### 实时取数前的前置检查（务必先做，别等报错）

只在**实时取数**（不带 `--excel`）时需要。用 `--excel` 分析本地文件时不检查、不打扰用户。

1. **检查导出技能是否已安装**：确认同级目录下存在 `kingdee-data-exporter/data_exporter.py`（或 `KingdeeDataExporter/data_exporter.py`）。
2. **检查是否已配置**：确认存在 `~/.workbuddy/kingdee/config.json`，或环境变量 `KINGDEE_BASE_URL` + `KINGDEE_USERNAME` + `KINGDEE_PASSWORD`，
   或导出技能目录里有 `config.py`。三者有其一即可。
3. **缺任一项时，先告知用户，再按用户意愿处理** —— 不要静默失败，也不要自行在后台联网下载：
   - 先把缺什么、装完能得到什么讲清楚，并给出安装与配置步骤；
   - **用户同意后**，可协助安装（推荐让用户在 SkillHub 直接装 `kingdee-data-exporter`；
     或联网拉取后放到本技能同级目录并确认目录内含 `SKILL.md`）：
     ```bash
     cd <存放本技能的父目录>
     curl -L -o kd.zip https://github.com/LittleBeaverStudio/KingdeeDataExporter/archive/refs/heads/master.zip
     # 解压后把 KingdeeDataExporter-master 重命名为 kingdee-data-exporter
     ```
   - 用户不想装时，退化为 `--excel` 模式：让用户先把 Excel 导出来。
4. **配置引导**：只填账套名称即可（`acct_name`，acctid 会自动解析）。配完让用户跑一次
   `python data_exporter.py --doctor`，它会逐步定位是配置、网络、账套、登录还是权限问题。
   ⚠️ 提醒用户：密码连续错约 5 次会锁账号，不要反复重试。

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

## 检查新版本

```bash
python analyzer.py --check-update
```

仅该命令会访问 GitHub Releases API。本地文件分析不联网；实时取数只连接已配置的金蝶服务器。

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
