<p align="center"><img src="assets/logomini.png" alt="Naiz" width="520"></p>

# Naiz — PC-98 ビジュアルノベルエンジン

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | **日本語**

> **ナイズ** — PC-98（NEC PC-9801/9821）向けのビジュアルノベルエンジン。NB（Naiz Book）プレーンテキスト形式のスクリプトを採用。

---

## 概要

Naiz は PC-98 向けのビジュアルノベル（ADV）制作スイートです。スクリプトと設定はそのまま編集できるプレーンテキストで、素材は通常の画像・音声ファイルです。**32 ビットプロテクトモード**のプログラムとしてビルドされ、実機の PC-9801/9821 または NP2kai エミュレータ上で動作します。

主な特徴：

- **32 ビットプロテクトモード** — DOS/4GW により PC-98 のプロテクトモードで動作し、リアルモードの 640 KB メモリ制限と 64 KB セグメント制限から解放されます。長いスクリプトや大量の素材でもやりくりは不要です
- **Naiz Queue 統一実行モデル** — ISR 独立クロック + 生産者-消費者キュー + frame pump により、BGM／アニメーション／立ち絵／トランジション／タイプライターをトランザクションとして分離。トランジション中に次シーンのリソースを自動プリロードし、同期ブロッキングと burst drain を排除します。長い stall が発生してもクロックのリズムに影響しません
- **プレーンテキストスクリプト** — `.nb` ファイルに物語を記述し、1 行変えてビルドし直すだけで反映されます。専用エディタは不要です
- **マウスとキーボード** — 両方の操作を同時に利用できます
- **多言語リリース** — 一度書けば 10 言語（英語、簡体字中国語、繁体字中国語、日本語、韓国語、フランス語、ドイツ語、イタリア語、スペイン語、ポルトガル語）で同時にリリースできます。プレイヤーは起動メニューで選択します
- **すぐ使えるツールチェーン** — 環境設定、ビルドとパッケージング、エミュレータテスト、アニメーション制作、素材ダウンロードのための専用スクリプトを用意しています

---

## クイックスタート

初回は環境をセットアップします（Python venv、NP2kai、Open Watcom ツールチェーン）：

```bash
./start.sh          # 対話式セットアップメニュー
./start.sh check    # 環境チェックのみ
```

初回実行時に共有 Python 仮想環境を `~/venv` に作成します。同じ親ディレクトリにある `naiz-studio` は同じ venv を再利用し、重複して作成しません。

デモプロジェクトのビルドと実行：

```bash
./makegame.sh build demo-a2            # 素材 → MAG → IMAGE.DAT → エンジンコンパイル → DOS ツリー展開
./makegame.sh make  demo-a2            # disks/demo-a2.hdi をパッケージ
./makegame.sh test  demo-a2 --serial   # NP2kai を起動し、シリアルログを出力
```

`build` は `games/<game>/` への展開のみを行い、`make` が展開ツリーを HDI に注入します。エミュレータが起動するのは HDI なので、エンジンを変更した後は両方を実行してください。

---

## ツールチェーン

| エントリ | 役割 |
|---|---|
| `start.sh` | 環境設定（check / pip / deps / np2kai / retroarch / watcom / djgpp / mirror）、`audit` シンボルカプセル化監査、`fullaudit` プロジェクト全体のルール監査 |
| `makegame.sh` | `build` でプロジェクトをコンパイル、`make` で HDI をパッケージ、`makegame` で両方、`test [--serial]` でエミュレータ起動、`audio` でエミュレータのオーディオ遅延を設定 |
| `anima.sh` | `.na` アニメーションスクリプト → `.ANI` コンテナ（init / register / check / mp4 / build / buildall / list） |
| `market.sh` | 公開マーケットリポジトリからパッケージ単位で素材をダウンロード（list / get / get-all / sync / menu） |
| `~/naiz-studio` | Web 版 NB スクリプト IDE（別リポジトリ。本リポジトリと同じ親ディレクトリに置き、`./studio.sh` で起動） |
| `tools/` | Python ツールチェーン：`naiz_img` イメージ注入、`naiz_build` データパッケージングと検証、`naiz_conv` 形式変換と i18n、`naiz_audio` オーディオ、`diag` 診断、`env_setup` 環境インストール |

パッケージ単位の索引は `docs/B90-参考-函数索引.md` を参照してください。

---

## 派生プロジェクト

| プロジェクト | リポジトリ | 説明 |
|---|---|---|
| Naiz Script Studio | https://github.com/edouardlicn123/naiz-studio | Web 版 NB スクリプト IDE。本リポジトリと同じ親ディレクトリに置く必要があり、`~/venv` を共有。`./studio.sh` で起動 |
| naiz-openpack | https://github.com/edouardlicn123/naiz-openpack | オープンソース構築素材パック（FreeDOS(98) チェーン + オープンソース基盤 HDI）。`./start.sh openpack` で `tools_open/` にダウンロード・展開 |
| naiz_cmpack | https://github.com/edouardlicn123/naiz_cmpack | 商用構築素材パック（MS-DOS 5 + PC-9821 BIOS）。`./start.sh commercial` で `tools_commercial/` にダウンロード・展開 |
| naiz_assets | https://github.com/edouardlicn123/naiz_assets | 公開素材マーケットリポジトリ。`./market.sh` でパッケージ単位に `assets_samples/` へダウンロード |

---

## 参考プロジェクト

- [MHVNVisualNovelEngine](https://github.com/maxotaku11niku/MHVNVisualNovelEngine) — MIT、シーン形式の参考
- [98Bridge](https://github.com/NullMagic2/98Bridge) — MIT、HDI 注入設計の参考
- [ADV98](https://github.com/yarufu/pc98) — MIT、PC-98 ADV エンジン。ゲーム側の PMD 統合と BGM ライフサイクルの参考
- [ADVS98](https://alammofm.com/advs98/) (Adventure System 98) — ソース非公開。PC-98 ビジュアルノベル／コマンド式 ADV 向けのブラウザ内エディタ + `p98c` コンパイラ + 内蔵エミュレータ（WASM、オフライン動作可）。Web 上のビジュアル編集体験（左にスクリプト／右に実機画面）の参考
- [98fmplayer](https://github.com/myon98/98fmplayer) — BSD-2-Clause、PMD/FMP ドライバと OPN レジスタ実装の参考
- [NP2kai](https://github.com/AZO234/NP2kai) — MIT、エミュレータホストと fmgen FM コア（実機 oracle）
- [ymfm](https://github.com/aaronsgiles/ymfm) — BSD-3-Clause、Yamaha FM エミュレーションコア（オフライン音色 oracle、`tools/vendor/ymfm` に vendor 済み）

License: MIT — see `LICENSE`.
