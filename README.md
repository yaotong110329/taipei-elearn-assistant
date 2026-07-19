# 臺北 e 大學習輔助程式 v1.1.1

Windows 桌面工具，用來減少臺北 e 大登入、掃描、上課、答題與選課流程中的重複操作。程式操作正式 Google Chrome，不保存帳號密碼，也不偽造平台資料。

## 程式用途與限制

- 使用獨立 Chrome profile 保存登入工作階段；第一次使用仍須手動登入。
- 學習紀錄會自動切換「未完成」、更新課程並改為每頁 50 筆。
- 上課基本時數為認證時數的 50%；例如認證 1 小時，倒數 30 分鐘。
- 少數特殊課程可用「✏️ 補正」增加額外時數；實際所需時數為基本時數加補正時數。
- 倒數結束後直接銜接下一門，不等待平台把課程標示為完成。
- 測驗只支援單頁的單選題與多選題。AI 只提供答案，送出前仍應自行確認。
- 批次選課會先列出並勾選結果；加入選課口袋及全部報名仍由使用者按鈕確認。
- 程式需要網路、正式版 Google Chrome，以及可正常使用的臺北 e 大帳號。

## 離線版安裝

1. 從 [GitHub Releases](https://github.com/yaotong110329/taipei-elearn-assistant/releases) 下載 `TaipeiELearnAssistant-v1.1.1-win64.zip`。
2. 完整解壓縮 ZIP；不能只取出 EXE。
3. 確認 Windows 10/11 64-bit 已安裝正式版 Google Chrome。
4. 執行 `TaipeiELearnAssistant\TaipeiELearnAssistant.exe`。
5. 第一次使用，在程式開啟的 Chrome 手動登入臺北 e 大。

離線版不需安裝 Python，也不需另下載 Playwright Chromium。

## 登入與上課

1. 按「開啟正式 Chrome」並手動登入。偵測登入後，程式會自動進入學習紀錄。
2. 進入「學習紀錄／上課」，按「開始掃描」。
3. 勾選要執行的課程。需要補正時，先選課程再按「✏️ 補正」。
4. 按「開始上課」。GUI 會顯示目前第幾門／總數及該課程倒數。
5. 倒數結束後自動離開、關閉可能出現的問卷視窗，再進入下一門。

若課程入口卡住，可按「跳過」；任何階段都可按「回到學習紀錄」。手動關閉 Chrome 後，可回首頁再按「開啟正式 Chrome」。

## 批次選課

1. 先確認 Chrome 已登入，再進入「選課」。
2. 展開「選課關鍵字」，勾選本次要搜尋的主題，並為每列設定 1～5 門。預設關鍵字永久保留；可另增刪自訂關鍵字。
3. 按「搜尋已勾選關鍵字」。程式會跨分頁搜尋，每個關鍵字依該列數量取課。
4. 已報名、不可報名及認證時數 0 小時的課程會排除；相同課程會去重。
5. 取消不需要的勾選，再按「加入選課口袋」。
6. 檢查結果後，按「選課口袋全部報名」。

## 測驗答題

1. 先掃描學習紀錄，再進入「答題」按「掃描未答題課程」。
2. 候選條件：課程未完成、有測驗項目、成績不是 100 分。閱讀時數為 0 的課程會顯示，但不能勾選進入。
3. 勾選課程並按「開始答題」。程式會處理「正式測驗」、「繼續上一次作答」或「再測驗一次」，擷取題目並把 AI 提示詞複製到剪貼簿。
4. 將提示詞貼給 AI。AI 回傳格式為 `[[ANSWERS]]1=A;2=BD;3=C[[/ANSWERS]]`。
5. 複製 AI 回答，按「從剪貼簿讀取送出答案」。格式及選項驗證通過後，程式會自動填入、送出、顯示分數，再進入下一門測驗；最後一門完成後回到學習紀錄未完成區。

## 常見問題

- **按鈕沒反應或頁面停住：** 先按「回到學習紀錄」，再重新掃描。若 Chrome 已被關閉，回首頁重新開啟。
- **登入狀態消失：** 使用程式開啟的 Chrome 重新登入；不要用無痕模式，也不要刪除 `chrome-profile`。
- **課程沒有開始倒數：** 課程可能有多層入口。保留 Chrome 視窗並查看日誌；可先跳過該課程再回報課名與錯誤。
- **閱讀時數為 0，無法測驗：** 先完成最低閱讀時數，再重新掃描。
- **AI 答案無法驗證：** 確認完整保留 `[[ANSWERS]]`、`[[/ANSWERS]]`，題號齊全，答案只含選項字母。

首頁：`https://elearning.taipei/mpage/`

日誌：`%LOCALAPPDATA%\TaipeiELearnAssistant\logs\app.log`

## 隱私與安全

- 程式沒有帳號密碼輸入欄位，不保存或上傳帳密。
- 登入 profile、設定與日誌位於 `%LOCALAPPDATA%\TaipeiELearnAssistant`。
- `chrome-profile` 可能包含有效登入工作階段，請勿分享或上傳。
- AI 提示詞包含測驗題目。貼到外部 AI 前，請自行確認資料使用政策。
- 原始碼放在 GitHub repository；可執行離線 ZIP 放在 GitHub Release，兩者分開提供。

## 開發、測試及打包

需要 Python 3.12+ 與正式版 Google Chrome。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test]"
.\.venv\Scripts\python main.py
```

執行測試：

```powershell
python -m pytest --basetemp .test-temp -q
```

建立 Windows 離線版：

```powershell
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean taipei-elearn.spec
```

PyInstaller 產物位於 `dist\TaipeiELearnAssistant`。整個資料夾都必須保留，因為 EXE 需要同層的 `_internal`。
