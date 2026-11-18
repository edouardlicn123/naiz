<p align="center"><img src="assets/logomini.png" alt="Naiz" width="520"></p>

# Naiz — PC-98 Visual Novel Engine

[English](README.md) | [简体中文](README.zh-CN.md) | **繁體中文** | [日本語](README.ja.md)

> **ナイズ** — 以 PC-98（NEC PC-9801/9821）為基礎的電子小說引擎，使用 NB 純文字劇本格式。
> A PC-98 visual novel engine with NB (Naiz Book) text-based scripting.

---

## 概覽

Naiz 是面向 PC-98 的視覺小說（ADV）製作套件：劇本與設定都是可直接編輯的純文字，素材就是普通的圖片與音訊檔案，建置後以 **32-bit 保護模式**程式的形式，在實機 PC-9801/9821 或 NP2kai 模擬器上執行。

核心特色：

- **32 位元保護模式** — 以 DOS/4GW 執行於 PC-98 的保護模式下，擺脫實模式 640 KB 記憶體與 64 KB 區段上限，長劇本與大量素材不必再精打細算
- **Naiz Queue 統一執行模型** — ISR 獨立時鐘 + 生產-消費佇列 + frame pump，BGM/動畫/立繪/轉場/打字機全事務解耦；transition 期間自動 preload 下一場景資源，消除同步阻塞與 burst drain，長時間 stall 不影響時鐘節奏
- **純文字劇本** — 在 `.nb` 檔案裡撰寫劇情，改一行、重新建置一次就能看到效果，無需專用編輯器
- **滑鼠與鍵盤** — 兩種操作方式同時可用
- **多語言發行** — 一次撰寫，可同時發行 10 種語言（英語、簡中、繁中、日、韓、法、德、義、西、葡），玩家在開機選單自選
- **開箱即用的工具鏈** — 環境設定、建置打包、模擬器測試、動畫製作、素材下載均有獨立腳本

---

## 快速開始

首次使用先設定環境（Python venv、NP2kai、Open Watcom 工具鏈）：

```bash
./start.sh          # 互動式設定選單
./start.sh check    # 僅環境檢測
```

首次執行會在 `~/venv` 建立共用 Python 虛擬環境；同父目錄下的 `naiz-studio` 共用同一 venv，不會重複建立。

建置並執行示範專案：

```bash
./makegame.sh build demo-a2            # 素材 → MAG → IMAGE.DAT → 編譯引擎 → 部署 DOS 樹
./makegame.sh make  demo-a2            # 打包 disks/demo-a2.hdi
./makegame.sh test  demo-a2 --serial   # NP2kai 啟動，序列埠日誌輸出
```

`build` 只部署到 `games/<game>/`，`make` 才把部署樹注入 HDI；模擬器啟動的是 HDI，因此修改引擎後兩者都要執行。

---

## 工具鏈

| 入口 | 用途 |
|---|---|
| `start.sh` | 環境設定（check / pip / deps / np2kai / retroarch / watcom / djgpp / mirror）、`audit` 符號封裝稽核、`fullaudit` 全專案規則稽核 |
| `makegame.sh` | `build` 編譯專案、`make` 打包 HDI、`makegame` 二合一、`test [--serial]` 啟動模擬器、`audio` 設定模擬器音訊延遲 |
| `anima.sh` | `.na` 動畫腳本 → `.ANI` 容器（init / register / check / mp4 / build / buildall / list） |
| `market.sh` | 從公開市場儲存庫整包下載素材（list / get / get-all / sync / menu） |
| `~/naiz-studio` | 網頁版 NB 劇本 IDE（獨立儲存庫，需與本儲存庫同父目錄，透過 `./studio.sh` 啟動） |
| `tools/` | Python 工具鏈：`naiz_img` 映像檔注入、`naiz_build` 資料打包與驗證、`naiz_conv` 格式轉換與 i18n、`naiz_audio` 音訊、`diag` 診斷、`env_setup` 環境安裝 |

套件層級索引見 `docs/B90-参考-函数索引.md`。

---

## 衍生專案

| 專案 | 儲存庫 | 說明 |
|---|---|---|
| Naiz Script Studio | https://github.com/edouardlicn123/naiz-studio | 網頁版 NB 劇本 IDE；須與本儲存庫同父目錄，共用 `~/venv`，透過 `./studio.sh` 啟動 |
| naiz-openpack | https://github.com/edouardlicn123/naiz-openpack | 開源建置資源包（FreeDOS(98) 鏈 + 開源基底 HDI）；`./start.sh openpack` 下載解壓縮至 `tools_open/` |
| naiz_cmpack | https://github.com/edouardlicn123/naiz_cmpack | 商用建置資源包（MS-DOS 5 + PC-9821 BIOS）；`./start.sh commercial` 下載解壓縮至 `tools_commercial/` |
| naiz_assets | https://github.com/edouardlicn123/naiz_assets | 公開素材市場儲存庫；`./market.sh` 依套件下載資源至 `assets_samples/` |

---

## 參考專案

- [MHVNVisualNovelEngine](https://github.com/maxotaku11niku/MHVNVisualNovelEngine) — MIT, 場景格式參考
- [98Bridge](https://github.com/NullMagic2/98Bridge) — MIT, HDI 注入設計參考
- [ADV98](https://github.com/yarufu/pc98) — MIT, PC-98 ADV 引擎；遊戲端 PMD 整合與 BGM 生命週期參考
- [ADVS98](https://alammofm.com/advs98/) (Adventure System 98) — 原始碼未公開, PC-98 視覺小說/指令式 ADV 的瀏覽器內編輯器 + `p98c` 編譯器 + 內建模擬器（WASM，可離線）；網頁端視覺化編輯體驗（左腳本 / 右實機畫面）參考
- [98fmplayer](https://github.com/myon98/98fmplayer) — BSD-2-Clause, PMD/FMP 驅動與 OPN 暫存器實作參考
- [NP2kai](https://github.com/AZO234/NP2kai) — MIT, 模擬器宿主與 fmgen FM 核心（實機 oracle）
- [ymfm](https://github.com/aaronsgiles/ymfm) — BSD-3-Clause, Yamaha FM 模擬核心（離線音色 oracle，已 vendor 於 `tools/vendor/ymfm`）

License: MIT — see `LICENSE`.
