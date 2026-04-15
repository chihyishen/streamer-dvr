# A/V 同步修復交接文件
日期：2026-04-14

## 本次 session 完成的診斷

### 問題確認
- MKV 和 MP4 都有音視不同步——問題在錄製源頭，不是轉檔造成
- 根因：HLS 音頻分片丟失（packet drop），導致音頻 PTS 出現跳躍
- 跳躍量為 ~1.6s 或 ~3.2s（0.8s 的倍數），與 HLS 分片最小單元一致

### 診斷數據（原始 MKV ffprobe 分析）
所有 MKV 的音視軌 start_time 完全對齊（無開頭偏移），問題來自中途的 PTS gap：

| 文件 | Audio gaps | 跳躍詳情 |
|------|------------|----------|
| germaine_jones_2026-04-13_22-44-39.mkv | 4 個 | 3.2s, 1.6s, 3.2s, 3.2s |
| hannahpage_2026-04-14_00-10-53.mkv | 4 個 | 1.6s, 1.6s, 3.2s, 1.6s |

## 修復方案測試結果

### 有效方案：`aresample=async=1`（對原始 MKV）
```bash
ffmpeg -fflags +genpts \
  -i input.mkv \
  -c:v copy \
  -af "aresample=async=1" \
  -c:a aac -b:a 128k \
  -shortest -movflags faststart \
  output.mp4
```

- 測試文件：`germaine_jones_2026-04-13_22-44-39.mkv`（2小時）
- 結果：原本 4 個 audio gap，修復後 **0 gaps**
- 原理：在 PTS 跳躍處自動填入靜音，後續音頻被推回正確時間位置
- 代價：音頻需重新編碼（aac），視頻仍 `-c:v copy` 無損

### 無效方案（勿用）
- `aresample=async=1000`：對已轉檔的 MP4 無效（PTS gap 已被抹平）
- `asetrate`：錯誤方案，拉伸音頻速率會讓沒問題的段落變歪
- `itsoffset`（固定值）：只能修單一固定偏移，無法處理多個分散的 gap

## 待驗證

**測試文件**：`/Volumes/Storage/Camrecs/videos/test/germaine_test_full.mp4`

需要人眼確認以下時間點的嘴型同步：
- **4:03** — 原 gap 3.2s
- **18:05** — 原 gap 1.6s
- **24:25** — 原 gap 3.2s
- **25:49** — 原 gap 3.2s

## 待解決的開放問題

### 從一開始就不同步的問題
用戶反映有些影片從第 0 秒就嘴型對不上，但 ffprobe 顯示 start_time 完全對齊。

**可能原因**：
1. HLS 第一個音頻分片就丟了 → MKV 有 PTS gap 記錄，`async=1` 可修
2. Chaturbate 來源端音視軌本身有固定 delay → PTS 上看不出來，只能 `itsoffset` 手動修

這些「從頭就歪」的檔案已經都轉成 MP4，無法重新診斷。**只能對新錄製的 MKV 測試**。

## 下一步（待本 session 驗證後執行）

### 若測試文件確認同步正常
修改 `app/services/recorder/paths.py`：

1. **移除** `_probe_av_sync_filter` 方法（整個 asetrate 邏輯）
2. **修改** `build_convert_command`，統一使用 `aresample=async=1`：

```python
def build_convert_command(self, source: Path, target: Path) -> list[str]:
    config = self.store.load_config()
    ffmpeg = self._ensure_dependency("ffmpeg", config.ffmpeg_path)
    return [
        ffmpeg, "-fflags", "+genpts",
        "-i", str(source),
        "-c:v", "copy",
        "-af", "aresample=async=1",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-movflags", "faststart",
        str(target), "-y",
    ]
```

## 其他結論

- **已轉檔的 MP4 沒救**：PTS gap 資訊已被抹平，無法用 `async=1` 修復
- **有對應 MKV 的可以救**：用上方指令重新轉檔即可
- **MKV 保留策略**：繼續保留，直到確認 MP4 沒問題為止（`delete_source_after_convert = false`）
- **`/tmp` 已清理**：之前 session 留下的約 7.5GB 測試殘檔已刪除
