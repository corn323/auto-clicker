# AutoClicker 滑鼠連點器

Windows 桌面滑鼠連點器。Python 3.11+ 標準函式庫（實測相容 3.10），零第三方依賴；
透過 Win32 `SendInput` 於系統層注入輸入，支援多螢幕、混合 DPI、負座標副螢幕，
內建擬人化隨機偏移與宣告式 JSON 腳本。

## 功能

- **多點位**：新增（F6，按下即記錄當前位置並有音效＋標題列提示）、選取、拖曳排序、
  逐一啟用/停用，每點獨立參數。
- **擬人化**：常態分佈點擊偏移（sigma = 半徑/3，截斷於半徑）、間隔抖動（均勻/常態）、
  貝茲曲線移動游標、按下前短延遲（預設 8ms，另加 0–3ms 隨機）、隨機長停頓。
- **全域熱鍵**：F6 新增、F8 開始/暫停、F9 停止（可在全域設定改鍵）。
- **角落急停**：滑鼠游標移到虛擬桌面任一角落即立刻停止（可開關、可選角落；
  容差下限 2px；選取畫面遮罩與新增期間暫停偵測）。
- **停止條件**：手動熱鍵 / 總點擊次數 / 總時間。
- **腳本**：click / move / wait / press_key / loop / if_pixel_color，
  可載入、匯出、驗證、執行；`examples/` 附三個範例。

## 安裝與執行

```powershell
# 需 Python 3.10+（tkinter 內建）
python main.py
```

設定自動儲存於 `%APPDATA%\AutoClicker\settings.json`（原子寫入，損壞自動回預設；
新增的主題與視窗大小位置缺少時使用預設值，舊設定檔可直接沿用）。

## 打包與發布

正式產物由 GitHub Actions 的 Release workflow 建置（PyInstaller 版本固定於
`requirements-build.txt`），推送 `v*.*.*` tag 後自動測試、打包、產生 SHA256、
簽發來源證明並建立 Release；流程詳見「發布流程」。

```powershell
# 本機手動打包（需自行安裝 PyInstaller，腳本不會自動下載任何東西）
pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File build.ps1
# 產出 dist\AutoClicker.exe 與 SHA256 摘要檔
```

打包參數不使用 `--exclude-module` 排除標準庫：PyInstaller 6.x 的 runtime hook
（`pyi_rth_inspect` 等）需要 `urllib`，一旦排除，產物啟動時會直接出現
`No module named 'urllib'` 而開不了 GUI。應用程式原始碼本身完全不使用網路、
程序執行或動態求值 API，由 `tests/test_security.py` 的 AST 掃描逐項把關。

## 下載與驗證

Release 附上 `AutoClicker.exe` 與 `AutoClicker.exe.sha256`；若 onefile
冷啟動較慢，另附 `AutoClicker-onedir.zip`。

目前版本：**v0.1.0** →
<https://github.com/corn323/auto-clicker/releases/tag/v0.1.0>
（`AutoClicker.exe` SHA256：
`64E20B32D68567D5390E9B656D86E4B00AA5103B7532B16BD6697D88742F537B`）

1. PowerShell 比對雜湊：

```powershell
Get-FileHash .\AutoClicker.exe -Algorithm SHA256
Get-Content .\AutoClicker.exe.sha256
```

兩者應一致（`.sha256` 檔第一欄為雜湊，後面是檔名）。

2. 驗證來源證明（需 GitHub CLI 2.49+ 並登入）：

```powershell
gh attestation verify .\AutoClicker.exe --repo corn323/auto-clicker
```

3. exe **未經程式碼簽章**，SmartScreen 或 Smart App Control 可能攔截。
   若不想繞過系統警告，建議下載原始碼後執行 `python main.py`。

### 實測數據

全部為實際量測值；本機為 Windows 11、Python 3.10.11、PyInstaller 6.22.3，
CI 為 GitHub Actions `windows-latest`（Python 3.12.10、PyInstaller 6.22.3）。

| 項目 | 本機 | CI（windows-latest） |
|---|---:|---:|
| Python 直譯器啟動（`python -c pass`） | 26–37 ms | — |
| GUI 啟動（原始碼 `pythonw main.py`） | 首次 1006 ms、後續 337 / 391 ms | — |
| GUI 閒置記憶體（視窗開啟 5 秒後） | 31.8–31.9 MB | — |
| GUI 記憶體 128 秒取樣 | 31.8 MB 全程持平，無持續成長 | — |
| 打包後 EXE 冷啟動（onefile） | 1483 ms* | 約 3528 ms |
| 打包後 EXE 冷啟動（onedir） | 未測† | 約 333 ms |
| 打包後 EXE 閒置記憶體 | 36.5 MB* | 40.7 MB |
| `--onefile` 大小 | 8.35 MB | 11.12 MB |
| `--onedir` 大小（資料夾） | 19.28 MB | 26.60 MB |
| `--onedir` 壓縮後（zip） | 8.33 MB | 11.42 MB |

\* 以本機下載的 v0.1.0 正式產物量測：視窗 handle 正常取得、WM_CLOSE 可正常
關閉、過程無任何點擊操作。
† 本機啟用 Smart App Control，新產生的未簽章 exe 會被系統攔截
（CodeIntegrity 事件 3118）；由 GitHub Release 下載的 onedir 產物同樣被攔截，
因此本機無法量測，CI 上的同一份建置流程則已完成啟動、取得視窗 handle 與
量測。每一個 Release 的說明都會附上當次 runner 的實測數字。

`--onefile` 是單一 exe、免解壓好攜帶，但啟動時需先解壓到暫存，一般較慢；
`--onedir` 需整包解壓，啟動較快、總體積較大，適合長期固定使用。若 Release
量到 onefile 冷啟動超過 1 秒，會同時附上 `AutoClicker-onedir.zip` 供選擇。

## 使用說明

1. **新增點位**：按 F6（或「新增點位 F6」按鈕），立即記錄當下游標位置，
   並在標題列顯示「已新增點位」提示。
2. **選取畫面位置**：全螢幕半透明遮罩上直接點選；遮罩涵蓋所有螢幕（含負座標副螢幕）。
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

## 介面操作

- 視窗可自由縮放（最小約 640×420）；寬度不足時自動改為上下堆疊，設定區可捲動。
- 標題列右側可切換深色/淺色主題；主題與視窗大小位置會記住，下次啟動還原
  （位置若已不在任何螢幕上，會自動置中於主螢幕）。
- 每個設定項都有單位、一句灰字說明與 Tooltip（含數值範例）；超出範圍會即時顯示
  「合法範圍 X–Y」，輸入值仍由既有驗證規則夾限。
- 「進階設定」（按下前延遲、隨機長停頓、角落急停、螢幕配置）預設收合。

## 手動驗證：全螢幕遮罩（負座標副螢幕／混合 DPI）

遮罩位置與尺寸以 Win32 虛擬桌面實體像素計算（`GetSystemMetrics` 的
`SM_*VIRTUALSCREEN` + `SetWindowPos`），不依賴 Tk 縮放換算。請依下列步驟驗證：

1. 設定多螢幕：主螢幕 100%/150% 縮放，副螢幕放在主螢幕左側或上方（座標為負）。
2. 啟動 AutoClicker，按「選取畫面位置」開啟遮罩。
3. 確認遮罩完整覆蓋**所有**螢幕（包含負座標那一塊），邊緣無縫、不偏移、不超出。
4. 確認每個螢幕的藍框與「螢幕 N 寬×高 DPI」標籤都畫在該螢幕範圍內，
   且跨 DPI 的螢幕框大小與實際螢幕一致。
5. 在副螢幕（負座標）點一下，確認新增點位座標與游標實際位置一致（誤差 0–1px）。
6. 在混合 DPI 下按 F6 新增，標題列提示的座標應與游標位置一致。
7. 遮罩開啟期間把游標移到角落，**不應**觸發角落急停（偵測已暫停）；
   關閉遮罩後再移入角落，應立即停止。

可用「全域 › 進階設定 › 重新校正」在變更螢幕配置後更新各點位的螢幕資訊。

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

## 發布流程

1. 更新 `autoclicker/__init__.py` 的 `__version__` 與 `CHANGELOG.md`。
2. 提交後建立並推送 tag：

```powershell
git tag v0.1.0
git push origin v0.1.0
```

3. Release workflow 會依序：跑完整測試（118 例）→ 核對 tag 與 `__version__`
   （`v0.1.0` 對 `0.1.0`，不一致即失敗）→ 以固定版 PyInstaller 建置
   onefile 與 onedir → 產生 SHA256 → 啟動 exe 煙霧測試並量測 →
   `actions/attest-build-provenance` 簽發來源證明 → 以內建 `gh` 建立 Release。
4. 需求 Tag 命名為 `v*.*.*`；測試失敗、版本不符或 exe 啟動即崩潰都不會發布。

`push` 到 `main` 或開 PR 時會由 `ci.yml` 在 Windows 上跑 Python 3.11／3.12／
3.13／3.14 矩陣測試（只指定 major.minor，由 setup-python 依 runner 平台挑選
可取得的最新 patch 版本）；`codeql.yml` 另做 Python 靜態掃描（push/PR 與
每週排程）。

### 需要維護者在 GitHub 手動設定

- 分支保護：對 `main` 要求 CI 通過、禁止強制推送。
- Tag 保護：限制誰能建立/刪除 `v*.*.*`（建議只允許維護者）。
- 確認 Actions 允許 `GITHUB_TOKEN` 建立 Release；若使用私有 repo，
  還需允許 artifact attestations 與 CodeQL（Advanced Security）。
- Dependabot PR 需人工審核，勿自動合併（避免供應鏈自動更新）。

## 開發

```powershell
python -m unittest discover -s tests -t .   # 118 個測試
```

安全設計與威脅模型見 `SECURITY.md`。
原始碼禁止使用網路、subprocess、eval/exec 等危險 API，並有 `tests/test_security.py`
以字串掃描＋AST 結構化檢查自動把關（含 CI workflow 自身的權限與 SHA 釘選檢查）。
AI Agent 的提示詞、Skills 與本機設定不納入版控（見 `.gitignore`）。
