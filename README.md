# 臺北 e 大學習輔助程式

Windows 桌面 GUI，用於減少臺北 e 大學習流程中的重複操作、集中顯示資訊並提升操作可及性。目前已完成登入偵測、學習紀錄掃描、課程依序播放、時數倒數、額外時數補正，以及單頁單選／多選測驗的題目擷取與答案回填。

## 使用邊界

- 不提供帳號密碼欄位，不保存或自動輸入帳密。
- 第一次使用時，由使用者在正式 Google Chrome 手動登入。
- 專用 Chrome profile 位於 `%LOCALAPPDATA%\TaipeiELearnAssistant\chrome-profile`，後續沿用登入狀態。
- Chrome 與 GUI 分開顯示。
- 不偽造學習紀錄，也不以固定計時器宣告課程完成。
- 測驗只處理閱讀時數已達標、學習紀錄顯示「未完成」的課程。
- 測驗答案驗證成功後仍需人工確認才填入；目前不自動送出。

## 執行

需要 Python 3.12+ 與正式版 Google Chrome。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test]"
.\.venv\Scripts\python main.py
```

Playwright 使用已安裝的正式 Chrome（`channel="chrome"`），不需另裝 Chromium。

## Windows 離線版

下載 Release 中的 `TaipeiELearnAssistant-v0.1.0-win64.zip`，完整解壓縮後執行 `TaipeiELearnAssistant\TaipeiELearnAssistant.exe`。

離線版不需安裝 Python，也不需下載 Playwright Chromium；仍需 Windows 10/11 與正式版 Google Chrome。第一次使用由使用者在程式開啟的 Chrome 手動登入。不要分享 `%LOCALAPPDATA%\TaipeiELearnAssistant\chrome-profile`。

## 目前功能

- 使用專用持久化 Chrome profile，偵測登入後進入學習紀錄。
- 自動選「未完成」、更新課程、每頁顯示 50 筆並掃描。
- 基本上課時數為認證時數 50%，可逐課增加額外補正時數。
- 依勾選順序進入課程，顯示目前門數與倒數，時間到進入下一門。
- 從學習紀錄讀取未完成測驗連結；閱讀時數不足時跳過。
- 支援「正式測驗／繼續上一次作答／再測驗一次」入口。
- 擷取單頁單選、多選題，產生 AI 提示詞並驗證固定答案格式。
- 人工確認後填入答案，不自動送出。

## 階段 1 驗收

1. 開啟程式，確認五頁可切換，主要按鈕文字完整。
2. 在 1280×720、1366×768、1920×1080 與 Windows 100%、125%、150% 顯示比例目視檢查。
3. 學習紀錄與選課頁各有 30 筆模擬資料；確認垂直／水平捲軸可拖曳、文字不重疊。
4. 按「開啟正式 Chrome」，首次手動登入臺北 e 大，再按「重新偵測登入」。
   偵測為已登入後，程式會自動進入學習紀錄、選擇「未完成」、按「更新我的課程」、改為每頁 50 筆，再切換 GUI 頁面。
5. 關閉並重開程式，確認同一 profile 沿用登入狀態。

程式開啟首頁：`https://elearning.taipei/mpage/`。

日誌：`%LOCALAPPDATA%\TaipeiELearnAssistant\logs\app.log`。

## 階段 2 驗收

1. 登入後開啟「我的課程／數位課程學習記錄」。
2. GUI 進入「學習紀錄／上課」，按「重新掃描」。
3. 程式先選「未完成」並更新課程，再把每頁筆數調為 50，依分頁掃描未完成課程並以課程 ID 去重。
4. 對照平台的課程名稱、修課時間、認證時數及完成狀態。
5. 修課時間與認證時數同時保留原始文字及正規化秒數；無法解析的列會在畫面提示並把 HTML 特徵寫入日誌。

基本所需上課時數採認證時數的 50%；例如認證 1 小時需上課 30 分鐘。手動補正時，額外時數加在此基本時數上。課程是否完成仍只採平台「課程完成與否」欄，不由時間推測。
