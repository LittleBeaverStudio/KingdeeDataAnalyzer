# -*- coding: utf-8 -*-
"""凭据加密存储（Windows DPAPI，**纯标准库**）。

为什么要有它
────────────
基准事实：**环境变量在本地并不保密** —— 同一 Windows 用户下的其它进程可以读到，
还会随子进程继承、进崩溃转储、进日志与 CI 输出。真正的"本机保密"要靠操作系统的
凭据保护机制。Windows 上的正解是 DPAPI（`CryptProtectData`），而它**用 `ctypes`
就能调**，所以本模块不引入任何第三方依赖（本 Skill 的既定原则：核心链路只用标准库）。

存哪儿 / 保护到什么程度
──────────────────────
默认落盘 `~/.workbuddy/kingdee/credentials.bin`，用 DPAPI 按**当前 Windows 登录用户**
派生密钥加密，效果：
  · 同一台机器上的**其它 Windows 用户**读不出（不同用户主密钥不同）；
  · 把文件拷到**别的机器**解不开；
  · 不在任何 git 仓库里，不会被顺手提交 / 打包 / 备份带走。

安全细节
────────
· 额外加一段**固定 entropy**，避免同机其它程序拿到密文后直接 `CryptUnprotectData`。
· 调用时带 `CRYPTPROTECT_UI_FORBIDDEN`，绝不弹系统对话框（无人值守场景必须）。
· 写入用**原子替换**（先写 `.tmp` 再 `os.replace`），避免半截文件。
· 本模块**不打印任何明文**；`describe()` 只回报字段名是否存在。

非 Windows
──────────
`available()` 返回 False，调用方应回落到环境变量 / 明文配置，**不要报错**。
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
from ctypes import wintypes
from pathlib import Path

# ── 落盘位置（技能目录之外：升级/重装/打包都不会覆盖或带走）──
STORE_DIR = Path.home() / ".workbuddy" / "kingdee"
STORE_PATH = STORE_DIR / "credentials.bin"

# 固定 entropy：不是密钥（就写在源码里），作用是让"别的程序捡到密文"不能直接解
_ENTROPY = b"kingdee-skill-credstore-v1"

# 受本模块保护的敏感字段名（仅用于 describe / 迁移判断，不参与加解密逻辑）
SECRET_FIELDS = (
    "password",
    "client_secret",
    "encrypt_key",
    "client_id",
)


# ─────────────────────────── DPAPI 绑定 ───────────────────────────

class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]


def _bind():
    """加载 crypt32/kernel32 并声明签名；非 Windows 返回 None。"""
    if sys.platform != "win32":
        return None, None
    try:
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except OSError:
        return None, None

    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DATA_BLOB),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(_DATA_BLOB),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return crypt32, kernel32


_CRYPT32, _KERNEL32 = _bind()

CRYPTPROTECT_UI_FORBIDDEN = 0x1


def _blob(data: bytes):
    """构造 DATA_BLOB；返回 (blob, 持有人)，持有人必须存活到调用结束。"""
    keeper = ctypes.create_string_buffer(data, len(data))
    return _DATA_BLOB(len(data), ctypes.cast(keeper, ctypes.c_void_p)), keeper


def _take(blob: _DATA_BLOB) -> bytes:
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        if blob.pbData:
            _KERNEL32.LocalFree(blob.pbData)


def _protect(data: bytes) -> bytes:
    in_blob, keep1 = _blob(data)
    ent_blob, keep2 = _blob(_ENTROPY)
    out = _DATA_BLOB()
    ok = _CRYPT32.CryptProtectData(
        ctypes.byref(in_blob), None, ctypes.byref(ent_blob),
        None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out),
    )
    del keep1, keep2
    if not ok:
        raise OSError(ctypes.get_last_error(), "CryptProtectData 失败")
    return _take(out)


def _unprotect(blob: bytes) -> bytes:
    in_blob, keep1 = _blob(blob)
    ent_blob, keep2 = _blob(_ENTROPY)
    out = _DATA_BLOB()
    ok = _CRYPT32.CryptUnprotectData(
        ctypes.byref(in_blob), None, ctypes.byref(ent_blob),
        None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out),
    )
    del keep1, keep2
    if not ok:
        raise OSError(ctypes.get_last_error(), "CryptUnprotectData 失败（密文不属于当前用户 / 已损坏）")
    return _take(out)


# ─────────────────────────── 对外 API ───────────────────────────

def available() -> bool:
    """当前环境能否使用 DPAPI 加密存储。"""
    return _CRYPT32 is not None


def exists() -> bool:
    return STORE_PATH.is_file()


def save(payload: dict) -> None:
    """把 dict 加密写入 credentials.bin（原子替换，权限收紧到仅当前用户）。"""
    if not available():
        raise RuntimeError("当前平台不支持 DPAPI，无法使用加密凭据存储")
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    blob = _protect(raw)
    tmp = STORE_PATH.with_suffix(".bin.tmp")
    with open(tmp, "wb") as fh:
        fh.write(blob)
    os.replace(tmp, STORE_PATH)
    try:  # 尽力收紧权限（NTFS 上失败也不影响加密保护）
        os.chmod(STORE_PATH, 0o600)
    except OSError:
        pass


def load() -> dict | None:
    """读取并解密；无文件返回 None；密文不可解时返回 None（并给出提示）。"""
    if not available() or not exists():
        return None
    try:
        blob = STORE_PATH.read_bytes()
    except OSError:
        return None
    if not blob:
        return None
    try:
        raw = _unprotect(blob)
    except OSError as exc:
        print(f"[WARN] 加密凭据无法解密（{exc}）——可能换了 Windows 用户或拷自别的机器，"
              f"请重新运行 helpers/setup_credentials.py")
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        print("[WARN] 加密凭据内容损坏，请重新运行 helpers/setup_credentials.py")
        return None
    return data if isinstance(data, dict) else None


def delete() -> bool:
    """删除加密凭据文件；存在并删除成功返回 True。"""
    if not exists():
        return False
    try:
        STORE_PATH.unlink()
        return True
    except OSError:
        return False


def describe(data: dict | None = None) -> str:
    """只回报**字段名是否存在**，绝不回显任何值（可安全写日志）。"""
    if data is None:
        data = load()
    if not data:
        return "（未配置加密凭据）"
    names = sorted(k for k, v in data.items() if v not in (None, "", {}))
    secrets = [k for k in names if k in SECRET_FIELDS]
    plain = [k for k in names if k not in SECRET_FIELDS]
    return ("已配置字段: " + ", ".join(plain) +
            (" ｜ 加密字段: " + ", ".join(secrets) if secrets else " ｜ 加密字段: 无"))


if __name__ == "__main__":  # 自检：加解密往返 + 错误熵，不落盘
    print("平台        :", sys.platform)
    print("DPAPI 可用  :", available())
    if available():
        probe = {"password": "自检用临时值", "username": "probe"}
        blob = _protect(json.dumps(probe).encode("utf-8"))
        back = json.loads(_unprotect(blob).decode("utf-8"))
        print("往返一致    :", back == probe)
        try:
            _unprotect(b"\x00" * 32)
            print("损坏密文    : ❌ 竟然解开了")
        except OSError:
            print("损坏密文    : ✅ 解密失败（符合预期）")
        print("存储路径    :", STORE_PATH)
        print("当前状态    :", describe())
