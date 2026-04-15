# 2026-04-13 影音同步損毀盤點與修復策略報告

## 1. 現狀總結 (Executive Summary)
針對 2026 年 4 月份產出的部分錄影檔案（MP4 容器），普遍發現嚴重的影音不同步現象。經過對 `bella__donne`, `hannah_lourens`, `germaine_jones` 等多位實況主檔案的精確盤點與交叉實驗，確認該問題為 **「內容層級的物理位移」**，無法透過傳統的 `aresample` 或時間戳修復工具自動校正。

## 2. 實驗數據與觀察 (Empirical Findings)

### A. 盤點規律
* **固定步進**：位移量通常為 **0.8s** 的倍數（如 1.6s, 2.4s, 3.2s），這與 HLS 音訊片段的最小單元一致。
* **偽對齊現象**：`ffprobe` 顯示 `start_time=0` 是無效的數據，實際播放時開頭即存在偏移。
* **時長誤導**：檔案結尾的時長差（Video duration - Audio duration）**不等於** 實際需要的位移量。
    * 範例：`hannah_lourens` 時長落差為 **1.6s**，但人眼驗證最準確的位移量為 **2.4s**。

### B. 修復實驗結果
1. **`aresample=async=1000`**: **無效**。無法修正物理位移，且在該批損毀檔案上無反應。
2. **`itsoffset` (固定位移)**: **有效**。透過強制平移音軌或影像軌，可完美恢復對齊。
3. **`-shortest`**: **有效**。可切除因位移產生的結尾「黑屏」或「無聲」片段。

## 3. 核心問題根因 (Root Cause Hypothesis)
錄製期間發生 HLS 音訊片段丟失（Packet Drop），`yt-dlp` 在寫入 MP4 容器時，雖然維持了連續的時間戳，但內容已經因為缺失而「往前縮排」，導致後續所有影音內容產生固定的、非連續性的偏移。

## 4. 推薦修復指令 (Repair Protocol)
實驗證明 **`Delay Audio` (延後音軌)** 是解決「聲音提前」的通用方案：

```bash
# 延後音軌 2.4 秒並對齊結尾
ffmpeg -i input.mp4 -itsoffset 2.4 -i input.mp4 -map 0:v -map 1:a -c copy -shortest output.mp4
```

## 5. 代碼重構進度 (Codebase Refactor)
已於 2026-04-13 推送變更至 `master` 分支：
* **`app/services/recorder/paths.py`**: 轉檔指令新增 `-fflags +genpts` 與 `-shortest`，防止未來新錄製的檔案發生類似結尾不一的問題。
* **`Scheduler` 重構**: 簡化 Capture 邏輯，優化 MKV 轉檔流程。

## 6. 後續建議方案：半自動修復工具
由於隱形位移量無法自動計算，建議開發一個輕量化腳本：
1. 為特定檔案產生 **[0.8s, 1.6s, 2.4s, 3.2s]** 的 10 秒預覽短片。
2. 人眼確認後，執行一鍵式 `itsoffset` 無損修復。

## 7. 錄製格式與儲存策略決策 (Recording & Storage Strategy)

### A. 格式選擇：為何維持 MKV 而非改用 TS？
* **合併優勢**：Chaturbate 採影音分離 HLS，`yt-dlp` 調用 `ffmpeg` 封裝成 `.mkv` 時對多串流合併的支援度與穩定性優於原始 `.ts`。
* **中繼資料 (Metadata)**：`.mkv` 的時長與索引資訊完整，方便 `ffprobe` 進行自動化盤點。
* **結論**：繼續使用 **MKV** 作為錄製端容器，`.mp4` 僅作為最終分發格式。

### B. 「後悔藥」保留策略 (The Regret Medicine)
* **決策**：不應在轉檔 `.mp4` 成功後立即刪除原始 `.mkv`。
* **邏輯**：原始 `.mkv` 保留了錄製時的原始時間戳 (Raw PTS)。若 `.mp4` 發現歪掉，可直接回頭對 `.mkv` 進行「深度修復」。
* **深度修復指令** (對原始檔極其有效)：
    ```bash
    # 使用 wallclock 強制對齊原始流
    ffmpeg -use_wallclock_as_timestamps 1 -i source.mkv -c copy -shortest repaired.mp4
    ```
* **建議保留天數**：3 ~ 7 天，或直到硬碟空間達到警戒線。

---
**文件狀態**：已歸檔 (Updated with Strategy Decisions)
**撰寫人**：Gemini CLI
**關聯檔案**：`notes/av-sync-investigation-2026-04-11.md`
