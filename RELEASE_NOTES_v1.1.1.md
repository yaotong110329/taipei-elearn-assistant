# v1.1.1 - 選課口袋修正

## 批次選課

- 「加入選課口袋」改為操作網站目前的搜尋與按鈕流程，不再直接呼叫容易變動的內部 API。
- 支援網站原生提示視窗及頁面內確認視窗。
- 加入後進入選課口袋再次確認；已存在的課程視為成功，不重複加入。
- 維持只選取「直接報名」課程，跳過已報名、不可報名、停止報名及認證時數 0 的課程。

## 安裝

下載 `TaipeiELearnAssistant-v1.1.1-win64.zip`，完整解壓縮後執行 `TaipeiELearnAssistant\TaipeiELearnAssistant.exe`。需要 Windows 10/11 64-bit 及正式版 Google Chrome，不需安裝 Python。
