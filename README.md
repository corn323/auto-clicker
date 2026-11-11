# AutoClicker 滑鼠連點器

Windows 桌面滑鼠連點器。Python 3.11+ 標準函式庫（實測相容 3.10），零第三方依賴；
透過 Win32 `SendInput` 於系統層注入輸入，支援多螢幕、混合 DPI、負座標副螢幕，
內建擬人化隨機偏移與宣告式 JSON 腳本。

## 功能

- **多點位**：錄製（F6）、選取、拖曳排序、逐一啟用/停用，每點獨立參數。
- **擬人化**：常態分佈點擊偏移（sigma = 半徑/3，截斷於半徑）、間隔抖動（均勻/常態）、
  貝茲曲線移動游標、隨機長停頓。
- **全域熱鍵**：F6 錄製、F8 開始/暫停、F9 停止（可在全域設定改鍵）。
- **角落急停**：滑鼠游標移到虛擬桌面任一角落即立刻停止（預設左上、3px）。
- **停止條件**：手動熱鍵 / 總點擊次數 / 總時間。
- **腳本**：click / move / wait / press_key / loop / if_pixel_color，
  可載入、匯出、驗證、執行；`examples/` 附三個範例。

## 安裝與執行

```powershell
# 需 Python 3.10+（tkinter 內建）
python main.py
```

設定自動儲存於 `%APPDATA%\AutoClicker\settings.json`（原子寫入，損壞自動回預設）。

## 打包為單一執行檔

```powershell
pip install pyinstaller
powershell -ExecutionPolicy Bypass -File build.ps1
# 產出 dist\AutoClicker.exe 與 SHA256 摘要檔
```

## 使用說明

1. **錄製點位**：按 F6（或「錄製 F6」按鈕），3 秒後記錄游標位置。
2. **選取位置**：全螢幕半透明遮罩上直接點選；遮罩涵蓋所有螢幕（含負座標副螢幕）。
3. **編輯參數**：右側編輯面板可調整偏移半徑、按住時間、間隔、抖動模式、按鍵、
   重複次數、權重與所在螢幕。
4. **開始/暫停/停止**：F8 / F8 / F9，或狀態列按鈕。
5. **腳本**：切到「腳本」分頁，載入或撰寫 JSON，按「驗證」檢查後「執行」。

### 腳本格式

```json
{
  "version": 1,
  "name": "範例",
  "steps": [
    { "type": "wait", "ms": 500 },
    { "type": "click", "x": 100, "y": 200, "button": "left",
      "double": false, "hold_ms": 50 },
    { "type": "move", "x": 300, "y": 400, "mode": "curve" },
    { "type": "press_key", "key": "R", "hold_ms": 30 },
    { "type": "loop", "count": 5, "steps": [ ... ] },
    { "type": "if_pixel_color", "x": 0, "y": 0, "color": "#FF00AA",
      "tolerance": 20, "steps": [ ... ], "else": [ ... ] }
  ]
}
```

限制：步驟 ≤ 1000、巢狀深度 ≤ 5、loop count ≤ 10000、展開後動作 ≤ 1,000,000、
wait 10–600000ms、hold_ms ≤ 1000、按鍵限白名單（英數、F1–F24 等）。
不合規步驟整份拒絕執行，絕不部分套用。

## 採用的 Win32 API

| 用途 | API |
|---|---|
| 輸入注入 | `SendInput`（MOUSEINPUT / KEYBDINPUT，絕對座標 + VIRTUALDESK） |
| DPI | `SetProcessDpiAwarenessContext`（失敗退 `SetProcessDPIAware`）、`GetDpiForMonitor` |
| 螢幕 | `EnumDisplayMonitors`、`GetMonitorInfoW` |
| 熱鍵 | `RegisterHotKey` / `UnregisterHotKey`（專用執行緒 + GetMessage 迴圈） |
| 其他 | `GetCursorPos`、`GetPixel`、`GetDoubleClickTime`、`SetWindowPos`、`OpenProcess` |

## 已知限制

- **UIPI／系統管理員視窗**：以一般權限執行時，無法對以系統管理員執行的視窗注入輸入
  （Windows 的完整性層級隔離）。程式會偵測並提示；如需對此類視窗操作，請以系統管理員
  執行 AutoClicker（風險自負）。
- 遊戲反作弊系統（EAC、BattlEye 等）可能封鎖或偵測輸入注入；請遵守各服務條款。
- `GetPixel` 判色較慢且可能受硬體加速影響，`if_pixel_color` 不保證在所有遊戲內有效。
- 僅支援 Windows 10/11（Python 3.10+）。

## 開發

```powershell
python -m unittest discover -s tests -t .   # 77 個測試
```

安全設計與威脅模型見 `SECURITY.md`；第三方 Skills 採用紀錄見 `SKILLS.md`。
原始碼禁止使用網路、subprocess、eval/exec 等危險 API，並有 `tests/test_security.py`
自動掃描把關。
