# Changelog

格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，
版本號採語意化版本。發布時由 Release workflow 讀取本檔與 `git log` 產生說明。

## [0.1.0] - 2026-11-11

### Added

- GitHub Actions CI：Windows（windows-latest）＋ Python 3.11／3.12／3.13／3.14
  矩陣，執行 `compileall` 與完整測試；只指定 major.minor，由 setup-python
  依 runner 平台挑選可取得的最新 patch 版本。
- CodeQL 掃描：push/PR 到 `main` 及每週排程。
- Release workflow：推送 `v*.*.*` tag 後自動測試、核對版本、建置
  onefile/onedir、產生 SHA256、煙霧測試、來源證明與 GitHub Release。
- Dependabot 每週檢查 `github-actions` 與 `pip` 更新。
- `requirements-build.txt` 固定建置工具版本。
- `autoclicker.__version__`（`0.1.0`），供 Release 核對 tag。
- 安全測試改以 AST 結構化檢查補強（僅允許標準庫匯入、危險呼叫清單、
  禁止動態 getattr、CI workflow 自身的 SHA／權限／secrets 檢查）。

### Changed

- UI/UX 重設計：視窗可縮放、窄版堆疊、深/淺主題、視窗位置記憶、
  文案與 Tooltip 改善、進階設定收合。
- 用語由「錄製」改為「新增點位／選取畫面位置」。
- `build.ps1` 與 Release workflow 採用相同打包參數：移除
  `--exclude-module urllib`（PyInstaller 6.x runtime hook 需要該模組，
  排除後 exe 會因 `No module named 'urllib'` 無法啟動）。
- `.gitignore` 排除 AI Agent 指示文件與本機 AI 工具設定，`SKILLS.md`
  已從版控移除（檔案仍保留在本機）。

### Fixed

- 修正 CI 在 Windows 2025 runner 上因指定 patch 版 Python（3.11.18／3.12.16）
  找不到而完全沒有執行測試的問題。
- 腳本分派改為明確分支，移除 `getattr(self, f"_do_{stype}")` 動態屬性取用。
- GUI 直接貼上的腳本內容加上 1 MB 大小上限。
- `OpenProcessToken` 失敗時不再對 NULL handle 呼叫 `CloseHandle`。

### Notes

- 首次正式發布：<https://github.com/corn323/auto-clicker/releases/tag/v0.1.0>
  （含 `AutoClicker.exe`、`AutoClicker.exe.sha256`、`AutoClicker-onedir.zip`
  與 build provenance 來源證明）。
- exe 未經程式碼簽章；SmartScreen / Smart App Control 可能攔截，
  建議改用原始碼執行。遊戲防作弊與服務條款風險請自行評估。
