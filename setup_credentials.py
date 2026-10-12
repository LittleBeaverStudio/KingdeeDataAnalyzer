# -*- coding: utf-8 -*-
"""金蝶凭据配置向导（弹窗）—— **明文不落盘**。

给谁用
──────
· 新装 Skill 的用户：双击 / 运行本脚本，在弹窗里填 **公司名（账套名称）、用户名、密码** 即可。
· 已装旧版、本机还留着明文 `~/.workbuddy/kingdee/config.json` 的用户：
  本向导会把旧值读进来、加密保存，并**默认删除那份明文文件**，同时提示改密码。

三条硬规矩
──────────
1. **不经过对话**：凭据只在本地弹窗里输入，不进任何聊天记录。
2. **不落明文**：密码等敏感字段经 DPAPI 加密写入 `~/.workbuddy/kingdee/credentials.bin`
   （绑当前 Windows 用户；别人/别的机器都读不出）。
3. **不回显、不写日志**：输入框掩码显示；脚本只打印字段名是否存在，永不打印值。

用法
────
  python helpers/setup_credentials.py            # 打开弹窗（正常用法）
  python helpers/setup_credentials.py --check     # 只看状态，不开窗（可用于无人值守排查）
  python helpers/setup_credentials.py --delete    # 只删除已保存的加密凭据
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import credstore  # noqa: E402

# 旧版明文配置（仅用于**迁移读取**，迁移后应删除）
LEGACY_CONFIG = Path.home() / ".workbuddy" / "kingdee" / "config.json"

# 可能的旧版技能内 config.py（老写法，仅用于预填）
# ① 本脚本所在目录（放到导出技能根目录时即自己的目录）
# ② 常见安装位置
_EXPORTER_CANDIDATES = (
    Path(__file__).resolve().parent,
    Path(__file__).resolve().parent.parent,
    Path.home() / ".workbuddy" / "skills" / "kingdee-data-exporter",
    Path.home() / ".workbuddy" / "skills" / "KingdeeDataExporter",
)


def _read_legacy_config() -> dict:
    """读旧明文配置（只读不写）。返回 {} 表示没有。"""
    if not LEGACY_CONFIG.is_file():
        return {}
    try:
        data = json.loads(LEGACY_CONFIG.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(data, dict):
        return {}
    profiles = data.get("profiles")
    if isinstance(profiles, dict) and profiles:
        want = os.environ.get("KINGDEE_PROFILE") or str(data.get("default") or "")
        if not want:
            want = next(iter(profiles))
        picked = profiles.get(want)
        if isinstance(picked, dict):
            common = {k: v for k, v in data.items() if k not in ("profiles", "default")}
            merged = {**common, **picked}
            # 兼容旧键名：server/acct/user/pwd → base_url/acctid/username/password
            for old, new in (("server", "base_url"), ("acct", "acctid"),
                             ("user", "username"), ("pwd", "password")):
                if old in merged and new not in merged:
                    merged[new] = merged.pop(old)
            return merged
    return data


def _read_exporter_config() -> dict:
    """从导出技能的 config.py 预填（早期写法）。"""
    for cand in _EXPORTER_CANDIDATES:
        cfg_py = Path(cand) / "config.py"
        if not cfg_py.is_file():
            continue
        try:
            sys.path.insert(0, str(cand))
            from config import KINGDEE_CONFIG as KC  # type: ignore
            if isinstance(KC, dict):
                return {k: v for k, v in KC.items() if v}
        except Exception:  # noqa: BLE001
            continue
        finally:
            if str(cand) in sys.path:
                sys.path.remove(str(cand))
    return {}


def collect_prefill() -> dict:
    """按 加密存储 > 旧明文 > 导出技能config.py 顺序取预填值（密码不回填到界面更安全）。"""
    pre: dict = {}
    pre.update({k: v for k, v in _read_exporter_config().items()})
    pre.update({k: v for k, v in _read_legacy_config().items() if v})
    saved = credstore.load()
    if saved:
        pre.update({k: v for k, v in saved.items() if v})
    return pre


def run_gui() -> int:
    import tkinter as tk
    from tkinter import messagebox, ttk

    pre = collect_prefill()
    legacy = _read_legacy_config()
    legacy_has_secret = bool(str(legacy.get("password") or "").strip())
    saved_exists = credstore.exists()

    root = tk.Tk()
    root.title("金蝶云星空 · 凭据配置")
    root.resizable(False, False)

    frm = ttk.Frame(root, padding=16)
    frm.grid(sticky="nsew")

    ttk.Label(frm, text="金蝶云星空 · 连接凭据", font=("Microsoft YaHei UI", 12, "bold")
              ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
    ttk.Label(frm, foreground="#666", justify="left", wraplength=460, text=(
        "只需维护 3 项：公司名（账套名称）、用户名、密码。\n"
        "凭据会用 Windows 系统加密后保存在本机，不会写入明文文件，也不会进入对话记录。"
    )).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 12))

    rows = [
        ("base_url", "服务器地址", "https://你的域名", False),
        ("acct_name", "公司名 / 账套名称", "例如：示例二科技有限公司", False),
        ("username", "用户名", "金蝶登录账号", False),
        ("password", "密码", "登录密码", True),
    ]
    entries: dict[str, ttk.Entry] = {}
    for i, (key, label, hint, secret) in enumerate(rows, start=2):
        ttk.Label(frm, text=label).grid(row=i, column=0, sticky="w", pady=4, padx=(0, 10))
        var = tk.StringVar()
        # 密码一律不回填（避免把旧明文再显示一遍）
        if not secret and pre.get(key):
            var.set(str(pre[key]))
        ent = ttk.Entry(frm, textvariable=var, width=42, show="*" if secret else "")
        ent.grid(row=i, column=1, sticky="we", pady=4)
        if hint:
            ttk.Label(frm, text=hint, foreground="#999").grid(row=i, column=2, sticky="w", padx=(8, 0))
        entries[key] = ent

    next_row = 6

    # ── 存量迁移区 ──
    del_legacy = tk.BooleanVar(value=legacy_has_secret)
    if legacy_has_secret:
        box = ttk.LabelFrame(frm, text="检测到旧版明文配置", padding=10)
        box.grid(row=next_row, column=0, columnspan=3, sticky="we", pady=(12, 0))
        ttk.Label(box, foreground="#b00", wraplength=460, justify="left", text=(
            "本机存在明文文件：\n%s\n"
            "里面的密码是明文保存的。保存后建议删除它，并到金蝶后台修改一次密码。"
            % LEGACY_CONFIG
        )).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(box, text="保存后删除该明文文件（推荐）", variable=del_legacy
                        ).grid(row=1, column=0, sticky="w", pady=(8, 0))
        next_row += 1

    status = ttk.Label(frm, foreground="#666", justify="left", wraplength=460, text="")
    status.grid(row=next_row, column=0, columnspan=3, sticky="w", pady=(10, 0))

    def refresh_status() -> None:
        if not credstore.available():
            status.configure(text="⚠️ 当前系统不支持 DPAPI，无法加密保存。请改用环境变量方式。")
        else:
            status.configure(text="当前加密凭据：" + credstore.describe())

    refresh_status()

    def on_save() -> None:
        base_url = entries["base_url"].get().strip()
        acct_name = entries["acct_name"].get().strip()
        username = entries["username"].get().strip()
        password = entries["password"].get()

        if not (username and password):
            messagebox.showwarning("还差一点", "用户名和密码是必填项。")
            return
        if not (base_url or acct_name):
            messagebox.showwarning("还差一点", "请至少填「服务器地址」或「公司名 / 账套名称」之一。")
            return

        payload = {
            "base_url": base_url,
            "acct_name": acct_name,
            "username": username,
            "password": password,
        }
        if str(pre.get("acctid") or "").strip():
            payload["acctid"] = str(pre["acctid"]).strip()

        try:
            credstore.save(payload)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("保存失败", f"{exc}")
            return

        notes = [f"已加密保存到：\n{credstore.STORE_PATH}"]
        if legacy_has_secret and del_legacy.get():
            try:
                LEGACY_CONFIG.unlink()
                notes.append(f"已删除明文文件：\n{LEGACY_CONFIG}")
            except OSError as exc:
                notes.append(f"⚠️ 明文文件删除失败，请手动删除：\n{LEGACY_CONFIG}\n（{exc}）")

        if legacy_has_secret:
            notes.append("安全建议：旧密码曾以明文存在本机，请到金蝶后台修改一次密码。")

        messagebox.showinfo("完成", "\n\n".join(notes))
        refresh_status()
        root.destroy()                      # 保存成功 → 自动关闭配置窗口
        entries["password"].delete(0, "end")

    btns = ttk.Frame(frm)
    btns.grid(row=next_row + 1, column=0, columnspan=3, sticky="e", pady=(14, 0))
    ttk.Button(btns, text="保存", command=on_save).grid(row=0, column=1, padx=(0, 8))
    ttk.Button(btns, text="退出", command=root.destroy).grid(row=0, column=2)
    if saved_exists:
        def on_clear() -> None:
            if messagebox.askyesno("确认", "删除本机已保存的加密凭据？"):
                credstore.delete()
                refresh_status()
        ttk.Button(btns, text="清除已保存凭据", command=on_clear).grid(row=0, column=0, padx=(0, 8))

    try:  # 居中
        root.update_idletasks()
        w, h = root.winfo_width(), root.winfo_height()
        x = (root.winfo_screenwidth() - w) // 2
        y = (root.winfo_screenheight() - h) // 3
        root.geometry(f"+{x}+{y}")
    except Exception:  # noqa: BLE001
        pass

    try:
        root.attributes("-topmost", True)   # 配置窗不被其它窗口压住
    except Exception:  # noqa: BLE001
        pass

    root.mainloop()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="金蝶凭据配置向导（加密保存，不落明文）")
    ap.add_argument("--check", action="store_true", help="只打印状态，不开窗")
    ap.add_argument("--delete", action="store_true", help="删除已保存的加密凭据")
    a = ap.parse_args()

    if a.delete:
        print("已删除" if credstore.delete() else "（没有已保存的加密凭据）")
        return 0
    if a.check:
        print("平台            :", sys.platform)
        print("DPAPI 可用      :", credstore.available())
        print("加密凭据文件    :", credstore.STORE_PATH, "存在" if credstore.exists() else "不存在")
        print("加密凭据内容    :", credstore.describe())
        print("旧版明文配置    :", LEGACY_CONFIG, "存在" if LEGACY_CONFIG.is_file() else "不存在")
        if LEGACY_CONFIG.is_file() and str(_read_legacy_config().get("password") or "").strip():
            print("                  ⚠️ 该文件含明文密码，建议运行本脚本迁移后删除")
        return 0

    if not credstore.available():
        print("当前系统不支持 DPAPI（非 Windows）。请改用环境变量：\n"
              "  KINGDEE_BASE_URL / KINGDEE_ACCTID / KINGDEE_ACCT_NAME\n"
              "  KINGDEE_USERNAME / KINGDEE_PASSWORD")
        return 2
    try:
        return run_gui()
    except ImportError:
        print("未找到 tkinter，无法弹出配置窗口。请改用环境变量方式注入凭据。")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
