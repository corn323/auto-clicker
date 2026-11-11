# 安全設計（SECURITY.md）

## 威脅模型

AutoClicker 是在本機以使用者權限執行、並向其他視窗注入滑鼠/鍵盤輸入的工具。
信任邊界為「使用者機器上的其他程序」與「使用者載入的設定檔/腳本檔」。
本程式**不提供任何網路功能**，攻擊面侷限於本機檔案與 Windows 輸入子系統。

| # | 威脅 | 來源 | 防護 |
|---|------|------|------|
| T1 | 惡意/損壞設定檔造成崩溃或越權行為 | `%APPDATA%\AutoClicker\settings.json` | 逐欄位型別檢查 + 夾限（config.py）；檔案 > 1MB 拒載；非 JSON 拒載回預設；不會抛未捕捉例外 |
| T2 | 惡意腳本執行任意程式碼 | 載入的 JSON 腳本 | 嚴格 schema：頂層與步驟欄位白名單、未知欄位即拒絕、深度/數量/範圍上限、按鍵白名單；**絕不** eval/exec/import 使用者字串 |
| T3 | 資源耗盡（炸彈腳本） | loop 嵌套 | 巢狀 ≤ 5、步驟 ≤ 1000、loop ≤ 10000、展開動作 ≤ 1,000,000，解析期即拒絕 |
| T4 | 檔案寫入被劫持（TOCTOU / 部分寫入） | 設定與腳本存檔 | `tempfile.mkstemp` + `os.fsync` + `os.replace` 原子替換，失敗即清暫存檔 |
| T5 | 程式自身被植入外傳管道 | 供應鏈 | 全原始碼禁用 socket/urllib/subprocess/os.system/eval/exec/pickle 等，`tests/test_security.py` 自動掃描；打包腳本再掃描執行檔可疑字串 |
| T6 | 對系統管理員視窗盲目注入 | UIPI | 偵測自身與前景視窗權限（`OpenProcess` + TokenElevation），不足時提示而非靜默失敗；`SendInput` 失敗抛 `OSError` 帶 UIPI 說明 |
| T7 | 程式失控狂點 | 邏輯錯誤 | F9 熱鍵 + 狀態列「停止」≤ 100ms 回應（所有等待皆可中斷）；角落急停；結束時 `finally` 釋放所有按住的按鍵 |
| T8 | 洩漏使用者資料 | — | 無網路 API、無遙測；設定只寫本機 `%APPDATA%` |

## 隨機數

點擊偏移與抖動使用 `secrets`（作業系統 CSPRNG），不用可預測的 `random`，
亦無固定種子——行為不可重放，無法由觀察推導後續座標。

## 輸入注入的最小權限

- 只注入滑鼠移動/按鍵與白名單按鍵碼；不操作剪貼簿、不讀取其他視窗內容
  （僅 `GetPixel` 讀單一像素色值供腳本判斷）。
- 熱鍵使用 `RegisterHotKey`，系統會在觸發時才投遞訊息；不掛全域鉤子
  （`SetWindowsHookEx`），不監看使用者其他按鍵。

## 已知風險（不視為漏洞）

- 以系統管理員執行本程式可對更高權限視窗注入——這是 Windows 設計，使用風險自負。
- 遊戲反作弊可能偵測 `SendInput` 注入；請遵守目標服務條款。
- 惡意設定檔可讓程式「點擊某處」，但座標上限 ±1,000,000、動作皆為滑鼠/單鍵，
  無法昇華為程式碼執行。

## 安全自檢清單

- [x] 無網路：socket/urllib/requests 等零使用（自動掃描）
- [x] 無程序執行：subprocess/os.system 零使用
- [x] 無動態求值：eval/exec/compile/__import__ 零使用
- [x] 反序列化僅 `json.load`，無 pickle/yaml
- [x] 外部輸入（設定/腳本）全數驗證夾限，損壞即回預設
- [x] 檔案寫入原子化（mkstemp + os.replace）
- [x] 大小上限：設定檔 1MB、腳本 1MB、點位 100、步驟 1000
- [x] 全域熱鍵可隨時急停；finally 保證釋放按鍵
- [x] UIPI 權限差異有偵測與提示，不靜默
