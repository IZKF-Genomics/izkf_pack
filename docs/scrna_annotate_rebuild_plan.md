# `scrna_annotate` 重做開發計劃

## 文件目的

本文件把 [scrna_annotate_redesign.md](/home/ckuo/github/izkf_pack/docs/scrna_annotate_redesign.md) 的產品與架構草案，轉換成可以直接執行的開發計劃。

這份計劃的目標不是再討論方向，而是回答下面幾個實作問題：

- 這次重做的範圍是什麼
- 先做哪些，後做哪些
- 現有模板哪些檔案要保留、搬移、淘汰或重寫
- 每一個 phase 的交付物是什麼
- 怎樣算完成、怎樣算可合併

## 專案目標

這次重做要把 `scrna_annotate` 從目前的單目錄、多方法混合模板，改為三層式 workflow：

- `tier1_quick_preview`
- `tier2_refinement`
- `tier3_formal_annotation`

新的模板要符合以下要求：

- 使用者第一次進來只填最少資訊就能看到結果
- 預設先跑 Tier 1，而不是要求先選 reference model
- 每一層有獨立 `run.sh`、`config`、`results`、`reports`
- 最上層有 orchestrator 控制 workflow
- 不同來源的 label 不互相覆蓋
- 報告以 workflow 決策為中心，而不是以方法為中心

## 重做範圍

## In Scope

- 重做 `templates/scrna_annotate/` 目錄結構
- 把現有 annotation runtime 拆分為 tier-based workflow
- 建立頂層 orchestrator `run.sh`
- 建立新的 config schema
- 重新定義輸出欄位命名
- 重新整理報告結構
- 把現有 `CellTypist` 流程搬移到 Tier 3
- 實作 Tier 1 MVP
- 實作 Tier 2 MVP

## Out Of Scope For First Rebuild

以下內容不列入第一輪重做：

- `scANVI` 正式 backend 實作
- `scGPT` backend 實作
- `scDeepSort` backend 實作
- `LangCell`、`mLLMCelltype`、`CellTypeAI` 整合
- 與 R 生態方法混合 runtime
- 大幅改寫 `scrna_prep` 與 `scrna_integrate`

這些方法可以在新骨架穩定後再做第二輪擴充。

## 成功標準

這次重做完成時，至少要滿足：

1. `scrna_annotate/run.sh` 預設可跑，且只執行 Tier 1
2. Tier 1 在只有 `input_h5ad` 與 `cluster_key` 的情況下能產生可讀報告
3. Tier 2 可讀取 Tier 1 outputs，產生 refinement 報告
4. Tier 3 可讀取 Tier 2 outputs，並以 `CellTypist` 執行 formal annotation
5. 新的 `adata.obs` 欄位命名不會覆蓋不同層的結果
6. 使用者可以單獨 rerun 任一 tier
7. 文件完整描述新 workflow 與執行方式

## 重做策略

## 採用漸進式重做，不採一次性覆寫

不建議直接在第一個 commit 就把舊模板整個砍掉重做。建議採用：

1. 先建立新骨架
2. 再搬移 shared utilities
3. 再逐步遷移 Tier 1、Tier 2、Tier 3
4. 最後移除或 retire 舊結構

這樣可以降低下列風險：

- 一次性大改造成模板完全不可用
- 現有 `CellTypist` runtime 行為被不小心破壞
- 測試基線消失，無法確認 regression

## 建議 branch/workflow

建議把這次工作視為一個明確的重做專案，而不是零散 patch：

- branch 名稱建議：`scrna-annotate-rebuild`
- 所有 tier 重構工作集中在同一個 branch
- 大 milestone 可拆成多個 commit / PR

## 目錄與檔案遷移計劃

## 新結構目標

```text
templates/scrna_annotate/
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
    results/
    reports/
  tier2_refinement/
    README.md
    run.sh
    run.py
    config/
      00_refinement_config.yaml
    results/
    reports/
  tier3_formal_annotation/
    README.md
    run.sh
    run.py
    config/
      00_formal_annotation_config.yaml
    results/
    reports/
  shared/
    lib/
```

## 現有檔案處置建議

### 直接保留並改位置

- `lib/annotation_io.py` -> `shared/lib/annotation_io.py`
- `lib/report_utils.py` -> `shared/lib/report_utils.py`
- 其他可共用 helper -> `shared/lib/`

### 改寫後保留名稱

- `README.md`
- `run.sh`

### 拆解或重寫

- `run.py`
- `build_annotation_outputs.py`
- `config/00_annotation_config.yaml`
- `assets/00_annotation_config.template.yaml`

### 內容需搬移到新 tier

- `01_celltypist.qmd` -> Tier 3 的 formal annotation report
- `00_annotation_overview.qmd` -> 頂層 workflow overview

### 暫時保留為 scaffold

- `02_scanvi.qmd`
- `03_decoupler_review.qmd`
- `04_scdeepsort.qmd`
- `05_scgpt.qmd`

這些可先移到合適 tier 或 archive 區，避免在第一版重做中拖慢主線進度。

## Phase 規劃

## Phase 0: 決策凍結

### 目標

在開始重構前，先把第一版要支援的功能鎖定，避免 scope 漂移。

### 要凍結的決策

- Tier 1 第一版只做 `CellAnnotator + manual_review`
- Tier 2 第一版做 marker review + cluster top markers + disagreement summary
- Tier 3 第一版只做 `CellTypist`
- `GPTCelltype` 不列入第一版 default path，可先保留為後續選項

### 交付物

- 本文件確認為實作依據

### 驗收標準

- 團隊對 MVP 範圍沒有未決重大歧見

## Phase 1: 建立新骨架

### 目標

建立三層目錄、頂層 orchestrator、shared library 結構與新的 config layout。

### 任務

- 建立 `tier1_quick_preview/`
- 建立 `tier2_refinement/`
- 建立 `tier3_formal_annotation/`
- 建立 `shared/lib/`
- 建立頂層 `config/workflow.yaml`
- 重寫頂層 `run.sh` 作為 orchestrator
- 建立各 tier 最小 `run.sh` 與 `run.py`

### 交付物

- 新目錄樹存在
- 各 tier 有最小可執行入口
- 頂層 `./run.sh` 能正確 dispatch 到 Tier 1

### 驗收標準

- `templates/scrna_annotate/run.sh` 可執行
- `--tier tier1|tier2|tier3` CLI 介面可解析
- 缺少前置輸出時能清楚報錯

## Phase 2: 抽 shared utilities

### 目標

把目前散落在舊模板中的共用功能抽到 shared layer，減少複製與未來維護成本。

### 任務

- 搬移 `annotation_io.py`
- 搬移 `report_utils.py`
- 新增 `workflow_io.py`
- 抽出共用 config 解析邏輯
- 抽出共用 `adata` 載入與 metadata 驗證邏輯

### 交付物

- `shared/lib/` 有清楚的共用模組
- 各 tier 可以 import shared utilities

### 驗收標準

- 共用邏輯不再分散在多個 tier 中重複實作

## Phase 3: 實作 Tier 1 MVP

### 目標

完成第一個真正對使用者可用的 quick preview workflow。

### 第一版方法

- `CellAnnotator`
- `manual_review`

### 任務

- 定義 Tier 1 config schema
- 實作 Tier 1 `run.py`
- 寫入 preview-related `adata.obs` 欄位
- 產生 preview tables
- 產生 `01_quick_preview.html`
- 若 `CellAnnotator` 因為 API/provider 條件不足無法執行，應退回 `manual_review`

### 輸出

- `results/adata.preview.h5ad`
- `results/tables/preview_consensus.csv`
- `results/tables/preview_disagreement_summary.csv`
- `reports/01_quick_preview.html`

### 驗收標準

- 只填最少 config 即可跑完 Tier 1
- 沒有 formal model 也不會卡死
- 報告中能看出哪些 cluster 需要 refine

## Phase 4: 實作 Tier 2 MVP

### 目標

讓 Tier 1 結果可以進入 evidence-based refinement。

### 任務

- 定義 Tier 2 config schema
- 讀取 Tier 1 outputs
- 實作 marker review
- 產生 cluster top markers
- 產生 refinement suggestions
- 建立 `02_refinement.html`

### 輸出

- `results/adata.refined.h5ad`
- `results/tables/cluster_marker_candidates.csv`
- `results/tables/marker_review_summary.csv`
- `results/tables/refinement_suggestions.csv`
- `reports/02_refinement.html`

### 驗收標準

- Tier 2 可獨立 rerun
- marker file 可選填
- 沒有 marker file 時仍可輸出基本 refinement summary

## Phase 5: 遷移 Tier 3 CellTypist

### 目標

把目前現有的 `CellTypist` runtime 從舊模板搬移到 Tier 3，新系統下仍保持 conservative annotation 行為。

### 任務

- 定義 Tier 3 config schema
- 搬移 `CellTypist` 執行邏輯
- 適配新欄位命名
- 適配新 workflow inputs
- 產生 `03_formal_annotation.html`
- 保留 `Unknown` 與 acceptance logic

### 輸出

- `results/adata.annotated.h5ad`
- `results/tables/formal_annotation_predictions.csv`
- `results/tables/formal_annotation_summary.csv`
- `reports/03_formal_annotation.html`

### 驗收標準

- 使用者只有在主動填入 `CellTypist` model 時才進入 Tier 3
- Tier 3 輸出不覆蓋 Tier 1 / Tier 2 labels
- 形式上仍可產生最終 `final_label`

## Phase 6: 重寫文件與使用說明

### 目標

讓新模板的使用方式、階層概念與 rerun 策略對使用者清楚可見。

### 任務

- 重寫 `templates/scrna_annotate/README.md`
- 撰寫各 tier 的 `README.md`
- 更新 `docs/scrna_annotate.md`
- 補上執行範例
- 補上 workflow 圖示或文字流程說明

### 驗收標準

- 新使用者只看 README 就能知道怎麼先跑 Tier 1
- 使用者可以理解何時該進 Tier 2 或 Tier 3

## Phase 7: 測試、清理與舊版退場

### 目標

在新 workflow 穩定後，清理舊結構，避免兩套模板邏輯長期並存。

### 任務

- 補單元測試與最小整合測試
- 檢查舊檔案是否還有殘留依賴
- 移除或 archive 舊版 runtime 入口
- 更新 linkar/template metadata

### 驗收標準

- 新模板有最基本 smoke test
- 舊版單一 `run.py + build_annotation_outputs.py` 不再是主入口

## 里程碑

## Milestone 1: 新骨架可啟動

完成條件：

- 頂層 orchestrator 可 dispatch
- Tier 1/2/3 目錄建立完成

## Milestone 2: Tier 1 可交付

完成條件：

- 使用者可只靠最低設定看到 preview 結果

## Milestone 3: Tier 2 可交付

完成條件：

- 使用者可從 preview 進入 refinement，看到 marker evidence

## Milestone 4: Tier 3 可交付

完成條件：

- 現有 `CellTypist` 能在新 workflow 中工作

## Milestone 5: 舊版退場

完成條件：

- 舊版入口不再作為主流程
- 文件全面切換到新 workflow

## 任務分解

## A. 架構任務

- 建立 tier 目錄與 shared layer
- 重寫頂層 orchestrator
- 設計 tier-to-tier input contract
- 設計新的 output 命名

## B. Runtime 任務

- Tier 1 runtime
- Tier 2 runtime
- Tier 3 runtime
- fallback / error handling

## C. 報告任務

- `00_overview.html`
- `01_quick_preview.html`
- `02_refinement.html`
- `03_formal_annotation.html`

## D. 文件任務

- 頂層 README
- 各 tier README
- docs update

## E. 測試任務

- config parsing tests
- tier dispatch tests
- smoke tests for Tier 1
- regression tests for Tier 3 CellTypist behavior

## 技術風險

## 1. Tier 1 預設工具依賴外部 API

風險：

- `CellAnnotator` 可能需要 provider/API key
- 本地與 CI 不一定可重現

對策：

- 第一版要有 `manual_review` fallback
- Tier 1 報告應清楚記錄哪些工具實際執行、哪些被跳過

## 2. 舊版 CellTypist 邏輯遷移後 regression

風險：

- acceptance logic 改壞
- output tables 欄位改名後報告或 downstream 斷裂

對策：

- Phase 5 前先保留現有結果作為 regression baseline
- 為 Tier 3 補最小整合測試

## 3. 三層 workflow 讓路徑太多

風險：

- 若 CLI 與文件不清楚，使用者反而更困惑

對策：

- 預設只暴露最簡單模式：`./run.sh`
- 進階模式才提供 `--tier`、`--from/--to`

## 4. 過早整合太多工具

風險：

- 一開始就把 GPTCelltype、CellAnnotator、scDeepSort、scANVI 都塞入，會拖慢主線

對策：

- 嚴格守住 MVP 範圍
- 先完成骨架，再考慮增加工具

## 開發順序建議

建議依照下面順序實作：

1. Phase 0: 決策凍結
2. Phase 1: 新骨架
3. Phase 2: shared utilities
4. Phase 3: Tier 1 MVP
5. Phase 4: Tier 2 MVP
6. Phase 5: Tier 3 CellTypist
7. Phase 6: 文件
8. Phase 7: 清理與退場

這個順序的優點是：

- 先讓新骨架成立
- 先把使用者最需要的 Tier 1 做出來
- 再把現有正式 backend 遷移過來

## 建議的實作原則

- 一次只改一層，不同 phase 不要同時大幅動太多檔案
- 新增檔案與目錄時，先讓最小流程可跑，再補細節
- 保留 conservative defaults，不要因為重做而讓模板更激進
- 不要在第一版中追求工具數量，先追求 workflow clarity

## 下一步

如果這份計劃確認要採用，建議立刻開始以下工作：

1. 建立 `scrna-annotate-rebuild` 分支
2. 實作 Phase 1：新骨架與 orchestrator
3. 把 `CellAnnotator + manual_review` 鎖定為 Tier 1 MVP
4. 用一個小型測試資料集驗證 Tier 1 能完整產出報告

這樣就正式進入整個模板「全面重做」的實作階段。
