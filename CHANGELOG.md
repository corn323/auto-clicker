# Changelog

格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，
版本號採語意化版本。發布時由 Release workflow 讀取本檔與 `git log` 產生說明。

## [0.1.0] - 2026-11-11

### Added

- GitHub Actions CI：Windows、Python 3.11.18/3.12.16 矩陣，執行
  `compileall` 與完整測試（含安全掃描測試）。
- CodeQL 掃描：push/PR 到 `main` 及每週排程。
- Release workflow：推送 `v*.*.*` tag 後自動測試、核對版本、建置
  onefile/onedir、產生 SHA256、煙霧測試、來源證明與 GitHub Release。
- Dependabot 每週檢查 `github-actions` 與 `pip` 更新。
- `requirements-build.txt` 固定建置工具版本。
- `autoclicker.__version__`（`0.1.0`），供 Release 核對 tag。

### Changed

- UI/UX 重設計：視窗可縮放、窄版堆疊、深/淺主題、視窗位置記憶、
  文案與 Tooltip 改善、進階設定收合。
- 用語由「錄製」改為「新增點位／選取畫面位置」。

### Notes

- exe 未經程式碼簽章；SmartScreen / Smart App Control 可能攔截，
  建議改用原始碼執行。遊戲防作弊與服務條款風險請自行評估。
