# -*- coding: utf-8 -*-
"""安全自檢：原始碼不得出現網路、程序執行、動態求值等危險 API。"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = [ROOT / "main.py",
           *sorted((ROOT / "autoclicker").rglob("*.py"))]

FORBIDDEN = [
    # 網路
    r"\bsocket\b", r"\burllib\b", r"\brequests\b", r"\bhttpx\b",
    r"\bftplib\b", r"\bsmtplib\b", r"\btelnetlib\b", r"\bxmlrpc\b",
    # 程序執行
    r"\bsubprocess\b", r"os\.system\b", r"os\.popen\b", r"os\.execv\w*",
    r"os\.spawn\w*", r"\bwinexec\b", r"ShellExecute",
    # 動態求值 / 反序列化
    r"(?<![\w.])eval\s*\(", r"(?<![\w.])exec\s*\(",
    r"(?<![\w.])compile\s*\(", r"__import__",
    r"\bpickle\b", r"\bmarshal\b", r"\byaml\b",
    # 危險檔案操作
    r"shutil\.rmtree", r"os\.remove\b.*settings", r"\bglob\.iglob",
    # 外部通訊
    r"\bwebbrowser\b", r"\bsmtplib\b", r"\bctypes\.windll\.wininet\b",
    r"InternetOpen", r"URLDownload",
]

ALLOWED = set()


def code_lines(path: Path):
    """移除三引號字串（docstring）後，回傳（行號, 內容）清單。"""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    out = []
    in_str: str | None = None
    for lineno, line in enumerate(lines, 1):
        if in_str is None:
            if '"""' in line or "'''" in line:
                marker = '"""' if '"""' in line else "'''"
                before, _sep, after = line.partition(marker)
                if after.count(marker) >= 1:
                    continue  # 同一行開關
                in_str = marker
                continue
            out.append((lineno, line))
        else:
            if in_str in line:
                in_str = None
            continue
    return out


class TestNoForbiddenApis(unittest.TestCase):
    def test_sources_exist(self):
        self.assertGreaterEqual(len(SOURCES), 6)
        for path in SOURCES:
            self.assertTrue(path.exists(), str(path))

    def test_no_forbidden_calls(self):
        for path in SOURCES:
            for lineno, line in code_lines(path):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for pattern in FORBIDDEN:
                    self.assertIsNone(
                        re.search(pattern, line),
                        f"{path.name}:{lineno} 出現禁用 API "
                        f"「{pattern}」：{stripped}")

    def test_no_suspicious_strings(self):
        for path in SOURCES:
            for lineno, line in code_lines(path):
                self.assertIsNone(
                    re.search(r"https?://", line),
                    f"{path.name}:{lineno} 含網址字串")

    def test_atomic_write_used(self):
        for path in (ROOT / "autoclicker" / "config.py",
                     ROOT / "autoclicker" / "scripting.py"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("os.replace", text,
                          f"{path.name} 未使用原子寫入 os.replace")

    def test_random_source_is_os_entropy(self):
        text = (ROOT / "autoclicker" / "engine.py").read_text(encoding="utf-8")
        self.assertIn("import secrets", text)
        self.assertNotIn("random.seed", text)
        self.assertNotIn("Random(", text)
        self.assertNotIn("import random", text)

    def test_json_only_deserialization(self):
        text = (ROOT / "autoclicker" / "config.py").read_text(encoding="utf-8")
        self.assertIn("json.load", text)
        for path in SOURCES:
            t = path.read_text(encoding="utf-8")
            self.assertNotIn("pickle.load", t)

    def test_openprocess_least_privilege(self):
        text = (ROOT / "autoclicker" / "win32.py").read_text(encoding="utf-8")
        self.assertIn("PROCESS_QUERY_LIMITED_INFORMATION", text)
        self.assertNotIn("PROCESS_ALL_ACCESS", text)
        self.assertNotIn("PROCESS_VM_READ", text)
        self.assertNotIn("PROCESS_CREATE_THREAD", text)

    def test_all_handles_closed(self):
        text = (ROOT / "autoclicker" / "win32.py").read_text(encoding="utf-8")
        self.assertIn("CloseHandle(hproc)", text)
        self.assertIn("CloseHandle(token)", text)
        # 每個 OpenProcess / OpenProcessToken 都必須有 finally 區塊關閉
        self.assertIn("finally:", text)
        self.assertGreaterEqual(text.count("CloseHandle"), 2)

    def test_no_corner_detection_during_overlay(self):
        text = (ROOT / "autoclicker" / "ui" / "app.py").read_text(encoding="utf-8")
        self.assertIn("set_corner_suppressed(True)", text)
        self.assertIn("set_corner_suppressed(False)", text)


if __name__ == "__main__":
    unittest.main()
