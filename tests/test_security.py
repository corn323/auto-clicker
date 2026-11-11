# -*- coding: utf-8 -*-
"""安全自檢：原始碼不得出現網路、程序執行、動態求值等危險 API。

除了字串掃描，另以 ast 做結構化檢查：字串掃描會被註解、字串常值或
變數命名誤觸／漏接，AST 檢查直接看「匯入什麼模組」與「呼叫了哪些函式」。
"""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = [ROOT / "main.py",
           *sorted((ROOT / "autoclicker").rglob("*.py"))]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

# 僅允許標準函式庫與本專案套件（執行期零第三方相依）。
LOCAL_MODULES = {"autoclicker", "autoclicker.ui"}
FORBIDDEN_IMPORTS = {
    "socket", "ssl", "urllib", "http", "ftplib", "smtplib", "telnetlib",
    "xmlrpc", "requests", "httpx", "aiohttp", "subprocess", "pickle",
    "marshal", "shelve", "yaml", "webbrowser", "ctypes.machinery",
}

# 禁止呼叫危險函式（以點號全名比對）。
FORBIDDEN_CALLS = {
    "eval", "exec", "compile", "__import__", "globals", "locals",
    "os.system", "os.popen", "os.spawnv", "os.spawnl", "os.spawnve",
    "os.execl", "os.execv", "os.execvp", "os.execvpe", "os.posix_spawn",
    "importlib.import_module", "importlib.__import__",
    "subprocess.run", "subprocess.Popen", "subprocess.call",
    "subprocess.check_call", "subprocess.check_output",
    "pickle.load", "pickle.loads", "marshal.load", "marshal.loads",
    "yaml.load", "yaml.safe_load", "shutil.rmtree",
    "webbrowser.open",
    "socket.socket", "socket.create_connection",
    "urllib.request.urlopen", "urllib.request.Request",
    "http.client.HTTPConnection", "http.client.HTTPSConnection",
    "ctypes.windll.shell32.ShellExecute", "ctypes.windll.wininet",
}

# 允許刪除檔案的位置：僅限原子寫入的暫存檔清理。
DELETE_ALLOWED_FILES = {"config.py", "scripting.py"}

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


def _dotted(node: ast.AST) -> str:
    """把 ast 節點轉成點號字串（Name / Attribute 鏈）。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


class TestAstSecurity(unittest.TestCase):
    """以 ast 做結構化檢查，補足字串掃描的盲點。"""

    @staticmethod
    def _trees():
        for path in SOURCES:
            yield path, ast.parse(path.read_text(encoding="utf-8"),
                                  filename=str(path))

    def test_imports_are_stdlib_only(self):
        """執行期只允許標準函式庫與本專案套件（零第三方 Runtime 依賴）。"""
        allowed = set(sys.stdlib_module_names) | LOCAL_MODULES
        for path, tree in self._trees():
            for node in ast.walk(tree):
                mods: list[str] = []
                if isinstance(node, ast.Import):
                    mods = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:  # 套件內相對匯入
                        continue
                    mods = [node.module or ""]
                for mod in mods:
                    root = mod.split(".")[0]
                    self.assertIn(root, allowed,
                                  f"{path.name}:{node.lineno} 匯入非標準模組 {mod}")
                    self.assertNotIn(root, FORBIDDEN_IMPORTS,
                                     f"{path.name}:{node.lineno} 匯入危險模組 {mod}")

    def test_no_dangerous_calls(self):
        for path, tree in self._trees():
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = _dotted(node.func)
                self.assertNotIn(name, FORBIDDEN_CALLS,
                                 f"{path.name}:{node.lineno} 呼叫危險函式 {name}")

    def test_file_deletion_limited_to_temp_cleanup(self):
        """只允許原子寫入的暫存檔清理使用 os.remove / os.unlink。"""
        total = 0
        for path, tree in self._trees():
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = _dotted(node.func)
                if name not in {"os.remove", "os.unlink"}:
                    continue
                total += 1
                self.assertIn(path.name, DELETE_ALLOWED_FILES,
                              f"{path.name}:{node.lineno} 不應刪除檔案 {name}")
        self.assertLessEqual(total, 4, "刪除檔案的呼叫數量異常")

    def test_no_dynamic_attribute_evaluation(self):
        """禁止 getattr(obj, 變數) 這類以變數決定屬性的動態取用。"""
        for path, tree in self._trees():
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == "getattr"
                        and len(node.args) >= 2
                        and not isinstance(node.args[1], ast.Constant)):
                    self.fail(f"{path.name}:{node.lineno} 使用動態 getattr")

    def test_no_url_literals(self):
        for path, tree in self._trees():
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    self.assertIsNone(
                        re.search(r"https?://", node.value),
                        f"{path.name}:{node.lineno} 含網址字串 {node.value!r}")


class TestWorkflowHardening(unittest.TestCase):
    """CI 本身也是攻擊面：workflow 必須釘 SHA、最小權限、僅 tag 發布。"""

    def test_workflows_exist(self):
        self.assertGreaterEqual(len(WORKFLOWS), 3)

    def test_actions_pinned_to_full_sha(self):
        pattern = re.compile(r"uses:\s*([\w.\-/]+)@([^\s#]+)")
        for path in WORKFLOWS:
            text = path.read_text(encoding="utf-8")
            for name, ref in pattern.findall(text):
                self.assertRegex(
                    ref, r"^[0-9a-f]{40}$",
                    f"{path.name}: {name} 未釘選完整 commit SHA（{ref}）")

    def test_no_pull_request_target(self):
        for path in WORKFLOWS:
            self.assertNotIn("pull_request_target",
                             path.read_text(encoding="utf-8"),
                             f"{path.name} 不得使用 pull_request_target")

    def test_release_only_on_tag(self):
        text = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8")
        self.assertIn('tags: ["v*.*.*"]', text)
        self.assertNotIn("pull_request", text)

    def test_minimum_permissions(self):
        """各 workflow 的寫入權限必須符合最小權限原則。"""
        allowed_writes = {
            "ci.yml": set(),
            "codeql.yml": {"security-events"},
            "release.yml": {"contents", "id-token", "attestations"},
        }
        for path in WORKFLOWS:
            text = path.read_text(encoding="utf-8")
            self.assertIn("permissions:", text,
                          f"{path.name} 未設定頂層 permissions")
            self.assertNotIn("write-all", text)
            writes = set(re.findall(r"^\s*([a-z-]+):\s*write\s*$", text,
                                    re.MULTILINE))
            self.assertTrue(writes <= allowed_writes[path.name],
                            f"{path.name} 出現非預期的寫入權限 {writes}")
        release = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8")
        self.assertIn("contents: write", release)
        self.assertIn("id-token: write", release)
        self.assertIn("attestations: write", release)
        # release workflow 的測試 job 不得有寫入權。
        test_job = release.split("  release:")[0]
        self.assertNotIn(": write", test_job,
                         "release workflow 的測試 job 不應有寫入權")

    def test_no_custom_secrets(self):
        for path in WORKFLOWS:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("secrets.", text,
                             f"{path.name} 不得使用自訂 secrets")

    def test_checkout_without_persisted_credentials(self):
        for path in WORKFLOWS:
            text = path.read_text(encoding="utf-8")
            for block in text.split("uses: actions/checkout@")[1:]:
                snippet = block[:400]
                self.assertIn("persist-credentials: false", snippet,
                              f"{path.name}: checkout 必須設定 persist-credentials: false")



if __name__ == "__main__":
    unittest.main()
