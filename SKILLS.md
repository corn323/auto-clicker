# Skills 採用紀錄

本專案開發過程中依使用者規則讀取並套用 `C:\Users\User\.codex\skills` 下的 skills。

## 採用

| Skill | 套用方式 |
|---|---|
| careful-coding | 全程遵守：先讀周邊程式碼再動手、最小變更、不引入未驗證依賴、每階段實機驗證（PrintWindow 截圖檢查 UI、單元測試 106 例全過）、不靜默吞錯（引擎/熱鍵錯誤皆回報 UI） |
| engineering-security-engineer（必讀） | 驅動整體安全設計：威脅模型（SECURITY.md）、設定/腳本輸入全驗證夾限、白名單 schema、原子寫入、secrets 亂數、禁用網路/subprocess/eval API 並以 tests/test_security.py 自動把關、UIPI 權限偵測提示 |
| ui-design / user-experience / information-design | 深色主題與版面階層、DPI 縮放像素值、狀態列即時回饋（狀態/點位/計數/時間）、遮罩選點全虛擬桌面涵蓋、熱鍵提示常駐右上、錯誤訊息具體（含 UIPI 原因說明）、危險動作（停止按鈕）醒目 |
| backend（部分） | 原子檔案寫入、輸入驗證層與 UI 分層、執行緒生命週期管理（daemon + 可中斷等待） |

## 判定不適用

- design-ui-designer：本專案為工具型桌面 UI，非品牌/視覺識別設計。
- 網頁類 skills（gsap-*、web game、frontend 等）：使用者明令禁止；本專案為
  tkinter 桌面程式，無任何網頁技術。

## 備註

- 測試與打包流程：`python -m unittest discover -s tests -t .`、
  `powershell -ExecutionPolicy Bypass -File build.ps1`。
- 環境差異紀錄：需求寫 Python 3.11+，實機為 3.10.11，程式碼以
  `from __future__ import annotations` 保持 3.10 相容。
