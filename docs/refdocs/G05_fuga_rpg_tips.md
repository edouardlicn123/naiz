# FUGA System Game Station 技術資料

> **来源**: [FUGA](https://web.archive.org/web/20021206125421/http://www.asahi-net.or.jp/~KC2H-MGR/rpg/source/) (RPG 開発者向けテクニカル資料)
> **内容**: 高速画像処理, 画面分割, スクロール, セーブデータ制御

---

## 概要

FUGA は PC-9801 向け RPG 開発を支援するドキュメント集で、主に以下の技術テーマを扱う:

1. グラフィック画面の分割表示
2. 高速矩形転送 (GRCG/EGC)
3. スクロール処理の高速化
4. ファイルセーブの信頼性
5. メモリ効率化

## 1. グラフィック画面分割

### テキスト分割

画面を上下に分割し、上部にゲーム画面、下部にメッセージラインを配置する。

```asm
; テキスト表示ライン制限
out 68h, 04h    ; 80桁モード
; GDC で表示開始ライン設定
; メッセージ部分 (下 4 行) は別管理
```

### VRAM 分割管理

```c
// ゲーム画面領域 (TEXT VRAM 0-20行)
#define GAME_AREA_LINES  21
#define MSG_AREA_LINES    4
#define MSG_START_LINE   21

// 各領域の属性別管理
char game_attr[GAME_AREA_LINES * 80];
char msg_attr[MSG_AREA_LINES * 80];
```

## 2. GRCG 高速転送

### 矩形転送 (GRCG RMW)

```asm
; GRCG を使った高速矩形塗りつぶし
; 引数: AX=色, CX=サイズ, SI=アドレス
setgrcg:
    push ax
    mov dx, 7Ch
    mov al, 82h      ; GRCG enable, RMW mode
    out dx, al
    pop ax
    mov dx, 7Eh      ; Pattern register
    ; パターンは AL の bit0-3 に対応
    out dx, al       ; Plane 0
    out dx, al       ; Plane 1
    out dx, al       ; Plane 2
    out dx, al       ; Plane 3
    ret
```

### スプライト転送

```c
// GRCG を使った透過スプライト転送
void sprite_put(int x, int y, const unsigned char *data) {
    int offset = (y * 80) + (x / 8);
    unsigned char mask;
    int bit = x % 8;

    // GRCG RMW 設定
    outp(0x7C, 0x83); // Enable + RMW + 全プレーン

    // パターン設定
    for (int plane = 0; plane < 4; plane++) {
        outp(0x7E, data[plane]);
    }

    // マスク処理
    if (bit == 0) {
        // 整列転送
        for (int row = 0; row < 16; row++) {
            unsigned char *vram = (unsigned char *)(0xA8000L + offset + row * 80);
            *vram = data[4 + row];
        }
    } else {
        // 非整列転送 (2回に分ける)
        // ...
    }

    // GRCG 解除
    outp(0x7C, 0x00);
}
```

## 3. EGC BitBLT

### 矩形コピー

```c
// EGC を使った 4 プレーン一括コピー
void egc_bitblt(int dst_x, int dst_y, int src_x, int src_y,
                 int width, int height) {
    // EGC 初期化
    outp(0x6A, 0x07);  // 拡張モード切替可
    outp(0x6A, 0x05);  // EGC
    outp(0x7C, 0x80);  // GRCG enable for EGC

    // 全プレーンアクセス
    outpw(0x4A0, 0xFFF0);
    // 前景色 = 0xFFFF (全ビット1)
    outpw(0x4A6, 0xFFFF);
    // マスク = 0xFFFF
    outpw(0x4A8, 0xFFFF);
    // ビット長 = 15
    outpw(0x4AE, 0x000F);

    // ブロック転送実行 (VRAM 直接アクセスでコピー)
    // EGC は VRAM 読み書き時に自動演算
    for (int y = 0; y < height; y++) {
        unsigned char *src = (unsigned char *)(0xA8000L + (src_y + y) * 80 + src_x / 8);
        unsigned char *dst = (unsigned char *)(0xA8000L + (dst_y + y) * 80 + dst_x / 8);
        for (int x = 0; x < width / 8; x++) {
            *dst++ = *src++;  // EGC が自動処理
        }
    }

    // 後始末
    outp(0x6A, 0x06);  // 拡張モード切替不可
    outp(0x7C, 0x00);  // GRCG 解除
}
```

## 4. スクロール処理

### 縦スクロール

```asm
; GDC 表示開始アドレス変更による縦スクロール
; TEXT GDC: 60h/62h, GRAPHIC GDC: A0h/A2h
scroll_up:
    mov dx, 0A0h
    mov al, 70h        ; 表示開始アドレス設定コマンド
    out dx, al
    mov dx, 0A2h
    mov ax, [scroll_y] ; スクロールY位置
    out dx, al         ; 下位
    mov al, ah
    out dx, al         ; 上位
    ret
```

### 横スクロール

横スクロールは GDC の開始アドレスに加え、ビット単位のオフセット処理が必要:

```c
void hscroll_set(int pixels) {
    int offset = pixels / 8;      // バイト単位
    int bit = pixels % 8;          // ビット単位

    // GDC 開始アドレス
    outp(0xA0, 0x70);
    outp(0xA2, offset & 0xFF);
    outp(0xA2, (offset >> 8) & 0xFF);
}
```

## 5. セーブデータの信頼性

### チェックサム

```c
// セーブデータの完全性検証
typedef struct {
    unsigned char data[8192];
    unsigned short checksum;
} SaveBlock;

unsigned short calc_checksum(const SaveBlock *block) {
    unsigned short sum = 0;
    const unsigned short *p = (const unsigned short *)block->data;
    for (int i = 0; i < sizeof(block->data) / 2; i++) {
        sum += p[i];
    }
    return sum;
}

int save_block_is_valid(const SaveBlock *block) {
    return calc_checksum(block) == block->checksum;
}
```

### 二重化セーブ

```c
// 2つのスロットに保存し、読込時は有効な方を選択
#define SAVE_SLOTS 2
int load_game(int slot) {
    SaveBlock blocks[SAVE_SLOTS];
    for (int i = 0; i < SAVE_SLOTS; i++) {
        read_save_slot(i, &blocks[i]);
    }
    // 有効な最新スロットを選択
    int best = -1;
    for (int i = 0; i < SAVE_SLOTS; i++) {
        if (save_block_is_valid(&blocks[i])) {
            if (best < 0 || blocks[i].timestamp > blocks[best].timestamp)
                best = i;
        }
    }
    if (best < 0) return -1; // 全滅
    memcpy(&save_data, &blocks[best].data, sizeof(save_data));
    return 0;
}
```

## 6. メモリ効率化

### データ圧縮

RPG のマップデータ圧縮に簡易ランレングス:

```c
unsigned char *rle_compress(const unsigned char *src, int src_len, int *dst_len) {
    unsigned char *dst = malloc(src_len * 2); // 最悪ケース
    int di = 0;
    int si = 0;
    while (si < src_len) {
        unsigned char c = src[si++];
        int count = 1;
        while (si < src_len && src[si] == c && count < 255) {
            count++;
            si++;
        }
        dst[di++] = count;
        dst[di++] = c;
    }
    *dst_len = di;
    return dst;
}
```
