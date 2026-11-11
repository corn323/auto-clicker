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
| T7 | 程式失控狂點 | 邏輯錯誤 | F9 熱鍵 + 狀態列「停止」≤ 100ms 回應（所有等待皆可中斷）；角落急停；任何例外、停止、關閉視窗都送 `release_all_buttons()`；按下後的 `finally` 保證對應 button-up |
| T8 | 洩漏使用者資料 | — | 無網路 API、無遙測；設定只寫本機 `%APPDATA%` |
| T9 | 遮罩/新增期間誤觸角落急停，導致無法操作 | 自身功能衝突 | `set_corner_suppressed()` 於選取畫面遮罩與新增期間暫停角落偵測，結束（含例外）即恢復 |
| T10 | 行程權限查詢過度取權 | UIPI 偵測 | `OpenProcess` 僅要求 `PROCESS_QUERY_LIMITED_INFORMATION`，且 `hproc`/`token` 皆以 `try/finally` + `CloseHandle` 關閉 |
| T11 | 按下前延遲被濫用成超長等待 | 設定檔 | `press_delay_ms` 夾限 0–50ms，隨機附加 0–3ms；所有延遲皆可被停止/急停中斷 |
| T12 | GitHub Actions 被入侵或 tag 被移動 | 第三方 action | 全部 action 釘完整 commit SHA（含 `actions/*`）並註記版本；Dependabot 每週提 PR；CodeQL 掃描；不自動合併依賴 PR |
| T13 | 偽造 tag 或版本不一致 | Git tag | Release 只接受 `v*.*.*`，並核對 `autoclicker.__version__`；來源證明綁定 repo/commit；建議手動開啟 tag 保護 |
| T14 | 建置工具被投毒（PyPI） | `requirements-build.txt` | PyInstaller 與 hooks 固定精確版本；只在 Release job 安裝；Dependabot 監控；殘餘風險見下節 |
| T15 | Token 權限過大或濫用 | `GITHUB_TOKEN` | workflow 預設 `permissions` 最小；只有 release job 有 `contents`/`id-token`/`attestations` write；checkout 設 `persist-credentials: false`；無 `pull_request_target`；不使用自訂 secrets |
| T16 | 下載到被替換的未簽章 exe | 發布產物 | Release 附 SHA256 與 build provenance（`gh attestation verify`）；文件明示未簽章風險；殘餘風險見下節 |

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
- [x] 全域熱鍵可隨時急停；例外/停止/關窗皆送出 button-up
- [x] UIPI 權限差異有偵測與提示，不靜默
- [x] 行程查詢僅 `PROCESS_QUERY_LIMITED_INFORMATION`，handle 全數 finally 關閉
- [x] 遮罩/新增期間角落偵測暫停；容差下限 2px
- [x] 按下前延遲夾限 0–50ms（+0–3ms 隨機），可被停止中斷
- [x] 遮罩以虛擬桌面實體像素定位（Win32），不依賴 Tk 縮放
- [x] 打包腳本僅執行 PyInstaller 與 SHA256，不下載任何東西
- [x] 所有 GitHub Actions 釘完整 commit SHA（含官方 `actions/*`）
- [x] workflow 預設最小權限；只有 Release job 有寫入權
- [x] 無 `pull_request_target`；Release 僅由 tag 觸發
- [x] GitHub 事件內容經 `env` 傳入，不直接插入 `run` 腳本
- [x] 建置工具固定版本（`requirements-build.txt`），Dependabot 每週監控

## 供應鏈殘餘風險（無法完全緩解）

- **平台與上游帳號**：GitHub、runner 映像、action 維護者或 PyPI 帳號若被入侵，
  本專案無法保證偵測。以完整 SHA 釘選、最小權限、人工審核 Dependabot PR
  降低機率，但無法消除。
- **建置工具投毒**：固定版本只防版本漂移，不防同版本套件被替換；目前未做
  hash pinning 或離線快取，列為後續強化項。
- **Tag/分支保護**：需在 GitHub 網頁手動設定，workflow 無法自我保證。
- **未簽章 exe**：attestation 只證明「由哪個 repo/commit/workflow 建置」，
  不證明二進位無惡意；若 repo 或 action 已被入侵，證明同樣失效。
  Windows SmartScreen／Smart App Control 仍可能攔截。
- **非 hermetic 建置**：Python patch 版本與 runner 映像會更新，產物不保證
  bit-for-bit 可重現。
- **私有 repo 限制**：CodeQL 與 artifact attestations 需方案支援；公開 repo
  使用 `GITHUB_TOKEN` 即可，無需自訂 secrets。

## 2026-11 安全複核（本輪變更）

| 變更 | 安全影響 | 驗證 |
|---|---|---|
| F6 新增改為立即記錄並加音效/標題列回饋 | 無新增攻擊面；不再有等待期間的輸入空窗 | 手動 + 截圖驗證 |
| 角落急停可開關、可選角落、遮罩/新增期間暫停 | 避免自身功能誤觸停止；容差下限 2px 防誤判 | `TestCornerCheck`（觸發/不觸發/下限/suppressed/負座標端點） |
| 按下前短延遲（0–50ms + 隨機） | 延遲可中斷；夾限防止超長等待 | `TestPressDelay`、`TestStopCondition` |
| OpenProcess 最小權限 + finally 關閉 handle | 降低權限暴露與 handle 洩漏 | 原始碼斷言：僅 `PROCESS_QUERY_LIMITED_INFORMATION`、`CloseHandle` 於 finally |
| 例外/停止/關窗送出 button-up | 防止按鍵卡住（左/右/中鍵） | `TestButtonRelease`（按下後例外、執行緒 finally、腳本按壓例外） |
| 絕對座標正規化四捨五入 | 落點誤差 ≤ 1px | `TestRoundtrip`（1920/1080、2560/1440、負座標、4K） |
| 遮罩改用虛擬桌面實體像素 | 負座標/混合 DPI 精準貼合 | 手動驗證步驟（README「手動驗證」）；`virtual_rect` 實體像素 |
| build.ps1 僅 PyInstaller + SHA256 | 供應鏈：不在打包流程下載/安裝 | 腳本無網路指令；缺少 PyInstaller 時僅報錯不下載 |
| UI 重設計（可縮放、主題、視窗記憶） | 無新增攻擊面；`theme` 限 dark/light，`window` 四欄位皆為整數並夾限，位置不符螢幕時置中 | 106 測試 + 多尺寸/主題截圖 |
| CI／CodeQL／Release workflow | 供應鏈與權限面：action 釘 SHA、預設唯讀、Release 才 write、無 `pull_request_target`、tag 與 `__version__` 核對、產物 SHA256 與 provenance | workflow 靜態檢視；推送後由 GitHub 實際執行驗證 |

測試總數：**106 例**，`python -m unittest discover -s tests -t .` 全數通過。
