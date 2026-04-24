# `scrna_annotate` 重構草案

## 目的

本文件提出 `scrna_annotate` 模板的重構方案，將目前以單一目錄承載多種 annotation 方法的設計，改為以使用者決策流程為中心的分層式 workflow。

重構目標：

- 讓使用者在幾乎不需要設定的情況下，先看到一版可用的 annotation 預覽結果
- 把後續 refinement 與 formal annotation 往後移，避免第一次執行就要求使用者選 reference model 或複雜參數
- 保留 conservative review 與 `Unknown` 策略，避免過度自動化
- 讓各 tier 的輸入、輸出、依賴與報告都更清楚

這個方向符合單細胞 best practices 對 annotation 的基本精神：

- 自動 annotation 應視為起點，而不是最終真相
- 參考資料是否匹配 query dataset 極度重要
- 不確定的 cluster 應保留為待審查狀態，而非被強制指派

預設參考：

- Single-cell best practices annotation chapter  
  <https://www.sc-best-practices.org/cellular_structure/annotation.html>

## 為什麼需要重構

目前模板的主要問題：

- 使用者一開始就面對 method-centric 結構，而不是 decision-centric workflow
- `CellTypist` 目前是唯一正式 backend，但很多資料集沒有合適 model
- 同一個模板同時承載 quick preview、reference-based annotation、review scaffold，心智模型不夠清楚
- 未來若再加入更多方法，會讓 config、輸出欄位與報告更加混亂

特別是對首次使用者而言，最需要的不是「所有方法都能選」，而是：

1. 先跑出一版結果
2. 看懂哪裡可靠、哪裡不可靠
3. 再決定要不要進入下一層方法

## 設計原則

### 1. 預設就能跑

第一次執行時，使用者應只需提供：

- `input_h5ad`
- `cluster_key`

其餘欄位盡量提供合理 default。

### 2. 先看結果，再做選擇

第一層不應要求：

- tissue-specific reference
- classifier model path
- marker YAML
- 額外訓練資料

第一層的目標不是高精度，而是快速產生可審閱的粗略 annotation landscape。

### 3. 各層有不同責任

- Tier 1：快速預覽
- Tier 2：低門檻 refinement
- Tier 3：正式 reference-based annotation

### 4. 不同層的結果不能互相覆蓋

建議保留不同來源的 label 欄位，例如：

- `preview_label_*`
- `refined_label`
- `formal_label_*`
- `final_label`

這樣使用者與開發者都能清楚追蹤每個結果的來源。

### 5. 報告應以決策流程為中心

不建議優先維持「每個方法一頁」的設計。更適合的方向是：

- `00_overview.html`
- `01_quick_preview.html`
- `02_refinement.html`
- `03_formal_annotation.html`

## 建議的新架構

### 總體 workflow

建議把模板改為三層式設計：

- `tier1_quick_preview`
- `tier2_refinement`
- `tier3_formal_annotation`

每一層都有自己的：

- `README.md`
- `run.sh`
- `run.py`
- `config/`
- `results/`
- `reports/`

最上層 `scrna_annotate/` 只負責 workflow orchestration 與全域設定。

### 建議的目錄結構

```text
templates/
  scrna_annotate/
    README.md
    run.sh
    config/
      workflow.yaml
    tier1_quick_preview/
      README.md
      run.sh
      run.py
      config/
        00_quick_preview_config.yaml
      lib/
      results/
      reports/
    tier2_refinement/
      README.md
      run.sh
      run.py
      config/
        00_refinement_config.yaml
      lib/
      results/
      reports/
    tier3_formal_annotation/
      README.md
      run.sh
      run.py
      config/
        00_formal_annotation_config.yaml
      lib/
      results/
      reports/
    shared/
      lib/
        annotation_io.py
        workflow_io.py
        report_utils.py
```

## Tier 規劃

## Tier 1: Quick Preview

### 目的

讓使用者在最低設定負擔下，立刻看到一版粗略 annotation 結果。

### 預設方法

第一版建議只納入低設定工具：

- `GPTCelltype`
- `CellAnnotator`
- `manual_review` fallback

如果實作上要保守一點，也可以第一版先只納入：

- `CellAnnotator`
- `manual_review`

理由：

- `GPTCelltype` 很輕量，但偏 cluster marker -> label 的超簡化流程
- `CellAnnotator` 比較接近完整 workflow
- `manual_review` 在沒有 API key、沒有合適工具、或結果很不可信時仍然有保底能力

### 輸入

至少需要：

- `input.h5ad`
- `cluster_key`
- `X_umap`

可選 metadata：

- `sample_id_key`
- `batch_key`
- `condition_key`
- `sample_label_key`

### 不應要求

- tissue-specific classifier model
- marker YAML
- 參考 atlas path
- raw count-specific reference setup

### 建議輸出

寫入 `adata.obs`：

- `preview_label_gptcelltype`
- `preview_label_cellannotator`
- `preview_consensus_label`
- `preview_disagreement_flag`
- `preview_review_priority`

輸出檔案：

- `results/tables/preview_labels_gptcelltype.csv`
- `results/tables/preview_labels_cellannotator.csv`
- `results/tables/preview_consensus.csv`
- `results/tables/preview_disagreement_summary.csv`
- `results/adata.preview.h5ad`
- `reports/01_quick_preview.html`

### 報告要回答的問題

- 哪些 cluster 在 preview tools 之間一致
- 哪些 cluster 有明顯分歧
- 哪些 cluster 可以先接受 broad lineage
- 哪些 cluster 應優先進入 refinement

### 使用者體驗

使用者第一次執行：

```bash
cd scrna_annotate
./run.sh
```

預設只跑 Tier 1，然後直接打開：

- `tier1_quick_preview/reports/01_quick_preview.html`

## Tier 2: Refinement

### 目的

把 Tier 1 的粗略結果，轉成更可信的 broad label 與 review evidence。

Tier 2 不是正式 reference mapping，而是低門檻 refinement。

### 建議內容

- marker review
- cluster top markers
- broad lineage collapsing
- disagreement triage

### 輸入

- `input.h5ad`
- Tier 1 outputs
- optional marker YAML

### 建議輸出

寫入 `adata.obs`：

- `marker_suggested_label`
- `refined_broad_label`
- `refinement_status`

輸出檔案：

- `results/tables/cluster_marker_candidates.csv`
- `results/tables/marker_review_summary.csv`
- `results/tables/refinement_suggestions.csv`
- `results/adata.refined.h5ad`
- `reports/02_refinement.html`

### 報告要回答的問題

- 哪些 preview labels 有 marker evidence 支持
- 哪些 cluster 仍然 ambiguous
- 哪些 cluster 已經足以接受 broad lineage label
- 是否值得進入 Tier 3 formal annotation

## Tier 3: Formal Annotation

### 目的

在使用者已有足夠背景資訊時，執行正式 reference-based annotation。

### 第一版建議方法

- `CellTypist`

未來可擴充：

- `scANVI`

### 輸入

- `input.h5ad`
- Tier 2 refinement 結果
- method-specific config
- model path 或 reference path

### 建議輸出

寫入 `adata.obs`：

- `formal_label_celltypist`
- `formal_confidence`
- `formal_status`
- `final_label`

輸出檔案：

- `results/tables/formal_annotation_predictions.csv`
- `results/tables/formal_annotation_summary.csv`
- `results/tables/method_comparison.csv`
- `results/adata.annotated.h5ad`
- `reports/03_formal_annotation.html`

### 報告要回答的問題

- 正式方法與前兩層是否一致
- 哪些 cluster 可以接受 formal label
- 哪些 cluster 應維持 `Unknown`
- 是否存在 reference mismatch 的跡象

## 執行模型

## 建議每個 tier 有獨立 `run.sh`

建議每層保留獨立 `run.sh`，原因：

- 各 tier 的依賴與設定不同
- 各 tier 可以單獨 rerun
- 各 tier 的失敗更容易 debug
- 後續加入新方法時，不會讓單一 `run.py` 過度膨脹

### 最上層 orchestrator

最上層 `scrna_annotate/run.sh` 建議只負責：

1. 讀取 `config/workflow.yaml`
2. 判斷要跑哪一層
3. 檢查必要前置輸出是否存在
4. 呼叫對應 tier 的 `run.sh`

### 建議 CLI 模式

最簡單模式：

```bash
./run.sh
```

預設行為：

- 只跑 Tier 1

指定單層：

```bash
./run.sh --tier tier2
./run.sh --tier tier3
```

連續執行：

```bash
./run.sh --from tier1 --to tier3
```

### workflow 驗證行為

若使用者指定：

```bash
./run.sh --tier tier2
```

但 Tier 1 outputs 不存在，應清楚報錯，例如：

- `Tier 2 requires Tier 1 preview outputs. Run ./run.sh first or provide --from tier1.`

## Config 設計

## 頂層 workflow config

檔案：

- `scrna_annotate/config/workflow.yaml`

建議內容：

```yaml
global:
  input_h5ad: /abs/path/to/adata.prep.h5ad
  cluster_key: leiden
  batch_key: batch
  condition_key: condition
  sample_id_key: sample_id
  sample_label_key: sample_display
  unknown_label: Unknown

workflow:
  default_tier: tier1
  auto_recommend_next: true
```

## Tier 1 config

檔案：

- `tier1_quick_preview/config/00_quick_preview_config.yaml`

建議內容：

```yaml
quick_preview:
  methods:
    - cellannotator
  enable_gptcelltype: false
  write_consensus: true
  unknown_label: Unknown
```

說明：

- 若沒有 API key 或 provider 設定，`GPTCelltype` 可預設關閉
- 若日後要再提高便利性，可在偵測到 API key 時自動開啟

## Tier 2 config

檔案：

- `tier2_refinement/config/00_refinement_config.yaml`

建議內容：

```yaml
refinement:
  marker_file: ""
  broad_lineage_mode: true
  rank_top_markers: 5
  unknown_label: Unknown
```

## Tier 3 config

檔案：

- `tier3_formal_annotation/config/00_formal_annotation_config.yaml`

建議內容：

```yaml
formal_annotation:
  method: celltypist
  enabled: false

celltypist:
  model: ""
  mode: best_match
  p_thres: 0.5
  use_gpu: false
```

說明：

- Tier 3 不應預設啟用，除非使用者主動填好 model / reference
- 這樣可以避免使用者第一次執行時因為 model 選擇問題卡住

## 欄位命名建議

建議停止把所有方法結果都寫進同一個通用欄位，例如 `predicted_label`。

改為保留來源資訊：

- `preview_label_gptcelltype`
- `preview_label_cellannotator`
- `preview_consensus_label`
- `marker_suggested_label`
- `refined_broad_label`
- `formal_label_celltypist`
- `formal_confidence`
- `final_label`

這樣有幾個好處：

- 使用者比較容易理解欄位來源
- 方法之間可比較而不會互相覆蓋
- 報告與 downstream export 可以更清楚

## 報告設計

### 建議從 method-centric 改成 workflow-centric

不建議優先維持這種結構：

- `01_celltypist.html`
- `02_scanvi.html`
- `03_decoupler_review.html`

建議改為：

- `00_overview.html`
- `01_quick_preview.html`
- `02_refinement.html`
- `03_formal_annotation.html`

### `00_overview.html` 應包含

- 本次 workflow 跑到哪一層
- 目前有哪些輸出可用
- 下一步推薦做什麼

### `01_quick_preview.html` 應包含

- preview tools 一致性
- disagreement summary
- preview consensus UMAP
- review priority list

### `02_refinement.html` 應包含

- marker evidence
- broad lineage suggestions
- unresolved clusters
- 推薦是否進 Tier 3

### `03_formal_annotation.html` 應包含

- formal annotation 結果
- 與 preview/refinement 的一致性比較
- confidence 與 acceptance status

## 第一版 MVP 建議

為了控制範圍，第一版不建議一次重寫所有未來方法。

### 第一版建議納入

- Tier 1
  - `CellAnnotator`
  - `manual_review`
- Tier 2
  - marker review
  - cluster top markers
  - disagreement summary
- Tier 3
  - `CellTypist`

### 第一版先不要納入

- `scANVI`
- `scDeepSort`
- `scGPT`
- `LangCell`
- `mLLMCelltype`
- `CellTypeAI`

原因不是這些工具沒有價值，而是第一版最重要的是：

- 建立清楚的 workflow 骨架
- 驗證分層 UX 是否好用
- 降低維護負擔

## 可能的開發順序

### Phase 1

- 建立新的三層目錄
- 建立頂層 orchestrator
- 把現有 `manual_review` 與 common report utilities 抽到 shared layer

### Phase 2

- 實作 Tier 1 `CellAnnotator`
- 產生 preview consensus / disagreement 輸出
- 完成 `01_quick_preview.html`

### Phase 3

- 實作 Tier 2 refinement
- 導入 marker review 與 top markers
- 完成 `02_refinement.html`

### Phase 4

- 把現有 `CellTypist` backend 移到 Tier 3
- 保留現有 conservative acceptance logic
- 完成 `03_formal_annotation.html`

### Phase 5

- 視需要加入 `scANVI`
- 視需要加入更多 quick preview tools

## 與現有模板的關係

建議不要直接把現有 `scrna_annotate` 全部覆寫成新版本。

較安全的做法：

1. 先在 `docs/` 內確認重構方案
2. 再建立新分支或新模板骨架
3. 把現有 `CellTypist` runtime 逐步搬到 Tier 3
4. 最後再決定是否 retire 舊版單目錄 layout

這樣可以降低一次性大重構帶來的風險。

## 最終建議

本模板最值得做的改變，不是增加更多 annotation 方法，而是改變整個使用者體驗：

- 先給使用者一版可看的結果
- 再告訴他哪裡需要 refine
- 最後才要求他選正式方法與 reference

簡單說，應把 `scrna_annotate` 從：

- 多方法展示模板

改成：

- 分層引導式 annotation workflow

這樣更符合使用者需求，也更符合單細胞 annotation 的實際工作模式。

## 待確認問題

以下問題在正式實作前仍需確認：

1. Tier 1 預設是否採 `CellAnnotator` 單工具，或同時納入 `GPTCelltype`
2. 是否接受 LLM/API 依賴作為 Tier 1 預設體驗的一部分
3. Tier 2 是否應該保留 purely local fallback，避免外部 API 全面失效時 workflow 中斷
4. `final_label` 是否只允許在 Tier 3 或明確人工確認後寫入
5. 舊版 `scrna_annotate` 是否保留為 backward-compatible template
