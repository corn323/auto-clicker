"""所有使用者可見文字集中在此；程式內部識別字（record_point 等）不在此列。

命名原則（見 ui-copy 指引）：
1. 按鈕一律用動詞開頭，說出「做了什麼」。
2. 設定名稱＋單位＋一句灰字說明；細節與範例放 Tooltip。
3. 不用實作名詞（SendInput、jitter、hold）對使用者說話。
4. 錯誤訊息要說「哪裡錯、怎麼改、合法範圍」。
"""
from __future__ import annotations

from ..config import APP_NAME

# ---- 基本 ----
APP_TITLE = APP_NAME
WINDOW_DEFAULT = (1040, 700)
WINDOW_MIN = (640, 420)
NARROW_WIDTH = 820

# ---- 分頁 ----
TAB_POINTS = "點位"
TAB_GLOBAL = "全域"
TAB_SCRIPT = "腳本"

# ---- 標題列 ----
HINT = ("{record} 新增目前游標位置   ·   {start} 開始/暫停   ·   "
        "{stop} 停止")
THEME_DARK = "深色"
THEME_LIGHT = "淺色"
TIP_THEME = "切換深色／淺色主題（會記住）"

# ---- 左側點位面板 ----
BTN_ADD = "新增點位 {hotkey}"
BTN_PICK = "選取畫面位置"
BTN_TEST = "測試點位"
BTN_UP = "上移"
BTN_DOWN = "下移"
BTN_COPY = "複製"
BTN_DELETE = "刪除"

TIP_ADD = "立即用目前游標位置新增一個點位（{hotkey}）"
TIP_PICK = "覆蓋畫面，點一下要新增的位置；Esc 或右鍵取消"
TIP_TEST = "立即在選取的點位點擊一次（會真的點擊）"
TIP_UP = "在清單中往前移"
TIP_DOWN = "在清單中往後移"
TIP_COPY = "複製選取的點位（預設停用）"
TIP_DELETE = "刪除選取的點位"

TREE_HEADINGS = (
    ("enabled", "啟用"), ("name", "名稱"), ("pos", "座標"),
    ("screen", "螢幕"), ("offset", "偏移"), ("button", "按鍵"),
    ("count", "次數"),
)
TREE_MIN_WIDTHS = {
    "enabled": 44, "name": 100, "pos": 92, "screen": 168,
    "offset": 48, "button": 64, "count": 48,
}
TREE_NARROW_COLUMNS = ("enabled", "name", "pos", "count")

EMPTY_TITLE = "還沒有點位"
EMPTY_HINT = "按 {hotkey} 新增目前游標位置，或按「選取畫面位置」點選目標。"
EMPTY_EDITOR = "從左側選擇點位，或按 {hotkey} 新增。"

# ---- 點位設定頁 ----
EDITOR_HINTS = {
    "name": "清單中顯示的名稱",
    "enabled": "取消勾選後，執行時略過此點位",
    "pos": "由「新增點位」或「重新選取」決定",
    "screen": "依座標自動判定；縮放或螢幕變更後請重新校正",
    "radius": "每次落點在目標周圍的隨機偏移；0 = 正中央",
    "hold": "每一點按住的時間範圍",
    "interval": "此點位兩下點擊之間隔",
    "jitter": "間隔上下浮動的比例",
    "jitter_mode": "均勻＝等機率；常態＝多數接近中間",
    "button": "要送出的滑鼠鍵與次數",
    "repeat": "每次輪到此點位要點幾下",
    "weight": "僅「加權隨機」使用；越大越常被選",
}
EDITOR_TIPS = {
    "name": "例：每日簽到按鈕",
    "radius": "例：5 → 落點在 ±5px 內隨機",
    "hold": "例：30–120 → 每下隨機按住 30 到 120 毫秒",
    "interval": "例：200 → 同一點位約每 200 毫秒點一下",
    "jitter": "例：20% → 間隔 200ms 時落在 160–240ms",
    "jitter_mode": "常態分佈會讓多數間隔接近設定值",
    "repeat": "例：3 → 每輪連點三下",
    "weight": "例：權重 5 被抽中的機率約為 1 的 5 倍",
}
LBL_NAME = "名稱"
LBL_ENABLED = "啟用此點位"
LBL_POS = "座標"
LBL_SCREEN = "所屬螢幕"
LBL_RADIUS = "偏移半徑"
LBL_HOLD = "按住時間"
LBL_INTERVAL = "點擊間隔"
LBL_JITTER = "間隔隨機幅度"
LBL_BUTTON = "按鍵"
LBL_REPEAT = "重複次數"
LBL_WEIGHT = "權重"
BTN_REPICK = "重新選取"
CHK_DOUBLE = "雙擊"
UNIT_PX = "px"
UNIT_MS = "ms"
UNIT_PCT = "%"
UNIT_TIMES = "次"

# ---- 全域設定頁 ----
SECTION_BEHAVIOR = "運作方式"
SECTION_STOP = "停止方式"
SECTION_ADVANCED = "進階設定"
LBL_ORDER = "執行順序"
LBL_MOVE = "游標移動"
LBL_MIN_INTERVAL = "最低間隔"
LBL_STOP = "停止條件"
LBL_HOTKEYS = "全域熱鍵"
LBL_PRESS_DELAY = "按下前延遲"
LBL_PAUSE = "隨機長停頓"
LBL_CORNER = "角落急停"
LBL_MONITORS = "螢幕配置"

HINT_ORDER = {
    "sequential": "依序：每個點位輪流",
    "random": "隨機：每輪重新洗牌",
    "weighted": "加權隨機：依各點位權重抽選",
}
HINT_MOVE = {
    "teleport": "瞬移：直接跳到目標，最快",
    "curve": "曲線移動：沿弧線移動，較像人手",
}
HINT_MIN_INTERVAL = "任何兩次點擊之間至少間隔這麼久"
HINT_STOP = {
    "manual": "用手動熱鍵開始、暫停與停止",
    "repeats": "累計點擊次數達到設定值後自動停止",
    "time": "執行達到設定秒數後自動停止",
}
HINT_HOTKEYS = "改鍵後按「套用熱鍵」；被其他程式占用時請換鍵"
HINT_PRESS_DELAY = "移到目標後、按下前的等待；另加 0–3ms 隨機"
HINT_PAUSE = "以設定機率插入較長的停頓，模擬中途休息"
HINT_CORNER = "游標進入角落的方形區域時立即停止"
HINT_MONITORS = "螢幕或縮放變更後按「重新校正」"

TIP_ORDER = "依序最快；加權隨機適合多個點位有不同重要性時"
TIP_MOVE = "瞬移較快；曲線移動較自然但稍慢"
TIP_MIN_INTERVAL = "例：10 → 兩次點擊至少相隔 10 毫秒"
TIP_STOP = "總次數與總時間只影響自動停止，不會改變手動熱鍵"
TIP_HOTKEYS = "點一下欄位後直接按新按鍵名稱，例如 F7、Ctrl+F8"
TIP_PRESS_DELAY = "例：8 → 按下前先等 8 毫秒，避免過於機械"
TIP_PAUSE = "例：3% 機率，停 300–1500 毫秒 → 平均約每 33 次停一次"
TIP_CORNER = "容差最少 2px；新增或選取畫面時會自動暫停偵測"
TIP_MONITORS = "重新校正會依目前螢幕更新所有點位的螢幕資訊"

LBL_PAUSE_CHANCE = "機率"
LBL_PAUSE_RANGE = "長度範圍"
LBL_STOP_COUNT = "總次數"
LBL_STOP_TIME = "總時間"
LBL_CORNER_ON = "啟用"
LBL_CORNER_TOLERANCE = "容差"
BTN_APPLY_HOTKEYS = "套用熱鍵"
BTN_RECALIBRATE = "重新校正"
UNIT_SEC = "秒"
RANGE_ERROR = "合法範圍 {lo}–{hi}"

# ---- 腳本頁 ----
BTN_SCRIPT_LOAD = "載入檔案"
BTN_SCRIPT_EXPORT = "匯出"
BTN_SCRIPT_VALIDATE = "驗證"
BTN_SCRIPT_EXAMPLE = "載入範例"
BTN_SCRIPT_RUN = "執行"
BTN_SCRIPT_STOP = "停止"
SCRIPT_NO_FILE = "尚未載入腳本；可直接編輯下方範本，或按「載入範例」"
SCRIPT_MSG_OK = "驗證通過：{count} 個頂層步驟。"
SCRIPT_MSG_EXPORTED = "已匯出（腳本僅含宣告式步驟，不含可執行程式碼）。"
SCRIPT_DIALOG_LOAD_TITLE = "載入腳本"
SCRIPT_DIALOG_EXPORT_TITLE = "匯出腳本"
FILE_JSON = "JSON 腳本"
FILE_ALL = "所有檔案"

# ---- 狀態列 ----
STATE_LABELS = {
    "idle": "● 待機",
    "running": "● 執行中",
    "paused": "● 已暫停",
    "stopping": "● 停止中",
    "stopped": "● 已停止",
}
STATE_STYLES = {
    "idle": "StateIdle.TLabel",
    "running": "StateRunning.TLabel",
    "paused": "StatePaused.TLabel",
    "stopping": "StateStopping.TLabel",
    "stopped": "StateIdle.TLabel",
}
STAT_POINT = "點位"
STAT_CLICKS = "點擊"
STAT_TIME = "時間"
BTN_START = "開始 {hotkey}"
BTN_PAUSE = "暫停 {hotkey}"
BTN_RESUME = "繼續 {hotkey}"
BTN_STOP = "停止 {hotkey}"
TOAST_ADDED = "已新增點位：{name}（{x}, {y}）"

# ---- 遮罩 ----
OVERLAY_HINT = "點一下要新增的位置   ·   Esc 或右鍵取消"

# ---- 對話框 ----
LOAD_WARNINGS = "載入設定時已自動修正：\n\n{warnings}"
DLG_NO_SCREEN = "無法判斷座標屬於哪個螢幕；請到「全域 › 進階設定」按「重新校正」。"
DLG_POINT_LIMIT = "已達點位上限 {limit} 個，請先刪除不用的點位。"
DLG_PICK_FIRST = "請先在左側選擇要修改的點位。"
DLG_TEST_FIRST = "請先在左側選擇一個點位再測試。"
DLG_TEST_RUNNING = "請先停止目前執行，再測試點位。"
DLG_RECALIBRATED = "已依目前螢幕配置更新所有點位的螢幕資訊。"
DLG_NO_ENABLED = ("沒有啟用的點位。按 {record} 新增目前游標位置，"
                  "或勾選「啟用此點位」。")
DLG_LAYOUT_CHANGED = ("螢幕配置與新增點位時不同，落點可能偏移。\n"
                      "建議到「全域 › 進階設定」按「重新校正」。\n\n仍要開始？")
DLG_ELEVATED = ("前景程式（PID {pid}）以系統管理員執行，本工具不是。\n"
                "Windows 會封鎖輸入，點擊可能無效。\n\n仍要開始？")
DLG_HOTKEY_FAILED = "熱鍵註冊失敗，請改用其他按鍵：\n\n{detail}"
DLG_SCRIPT_LOAD_FAILED = "腳本無法載入：\n\n{errors}"
DLG_SCRIPT_EXPORT_FAILED = "腳本驗證失敗，無法匯出：\n\n{errors}"
DLG_SCRIPT_RUN_FAILED = "腳本驗證失敗：\n\n{errors}"
DLG_SCRIPT_RUNNING = "已有工作執行中；請先停止再執行腳本。"
DLG_EXPORT_ERROR = "匯出失敗：{reason}"
DLG_SAVE_ERROR = "無法儲存設定：{reason}\n請確認設定資料夾可寫入。"
