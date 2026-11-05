# bauxite PC-98x1 技術 Wiki

> **来源**: [bauxite.sakura.ne.jp](https://bauxite.sakura.ne.jp/) (Wayback Machine 归档)
> **内容**: PC-98x1 の開発ノウハウ、トラブルシューティング

---

## 1. 開発環境構築

### C コンパイラ

| 環境 | 特徴 | 備考 |
|------|------|------|
| LSI-C 86 | 16bit 実/保護, 軽量 | 試食版あり |
| LSI-C 86 試食版 | 非商用無料, 4KB制限 | 学習向け |
| Turbo C | 16bit, 統合環境 | 古い |
| Borland C++ | 16/32bit | バージョンによる |
| Open Watcom C/C++ | 32bit, 保護/DOS4GW | **Naiz 选用** |
| GCC (Cross) | 16/32bit | DJGPP, i386-elf |

### PC-98 開発キット

- PC-98 用の開発キット (NEC PC-9800 series SDK / PDOS)
- DOS4G 対応のツールチェイン

## 2. デバッグ手法

### シリアルデバッグ

```c
// 簡易シリアル出力
void debug_putc(char c) {
    while (!(inp(0x32) & 2));  // TX レディ待ち
    outp(0x30, c);
}
void debug_puts(const char *s) {
    while (*s) debug_putc(*s++);
}
```

### ポートモニタ

```asm
; 特定 I/O ポートの監視 (デバッグ用)
PORT_MONITOR:
    ; ブレークポイント代わりに
    mov dx, 0x60
    in al, dx
    mov dx, 0x90h   ; 未使用ポートに出力
    out dx, al
    ret
```

### 画面デバッグ

テキスト画面への直接出力:

```c
void dbg_putchar(int row, int col, char c, char attr) {
    unsigned char *vram = (unsigned char *)0xA0000L + (row * 80 + col) * 2;
    vram[0] = c;
    vram[1] = 0;   // 半角
    unsigned char *attr_vram = (unsigned char *)0xA2000L + row * 80 + col;
    attr_vram[0] = attr;
}
```

## 3. メモリ管理

### メモリマップ

```
00000 - 9FFFF : システム RAM (640KB)
A0000 - A3FFF : テキスト VRAM
A4000 - A7FFF : CG コード領域 / CG ウィンドウ
A8000 - AFFFF : グラフィック VRAM (プレーン 0)
B0000 - B7FFF : グラフィック VRAM (プレーン 1)
B8000 - BFFFF : グラフィック VRAM (プレーン 2)
C0000 - CFFFF : Option ROM
D0000 - DFFFF : EMS ページフレーム
E0000 - E7FFF : グラフィック VRAM (プレーン 3)
E8000 - EFFFF : I/O, システム領域
F0000 - FFFFF : BIOS ROM (一部 RAM)
```

### プロテクトモードでの VRAM アクセス

```c
// DOS/4GW 等の 32bit プロテクトモード下での VRAM アクセス
// セグメント:オフセットからリニアアドレスへ
unsigned long vram_linear = 0xA8000L;
volatile unsigned char *vram = (volatile unsigned char *)vram_linear;

// プレーン間のアクセス
void vram_write_plane(int plane, int offset, unsigned char data) {
    volatile unsigned char *base;
    switch (plane) {
        case 0: base = (volatile unsigned char *)0xA8000L; break;
        case 1: base = (volatile unsigned char *)0xB0000L; break;
        case 2: base = (volatile unsigned char *)0xB8000L; break;
        case 3: base = (volatile unsigned char *)0xE0000L; break;
        default: return;
    }
    base[offset] = data;
}
```

## 4. トラブルシューティング

### 表示が出ない

1. GDC が正しく初期化されているか確認
   - モードトリガ (68h/6Ah) の設定順序
   - ページ設定 (A4h/A6h) が正しいか
2. 表示許可信号が出力されているか
   - GDC の DE ビット確認
   - GDC モードレジスタ 1 の bit7 (DISPENABLE)
3. テキスト VRAM / グラフィック VRAM の値確認
4. グラフィックモードとテキストモードの切り替え確認

### GDC が反応しない

- GDC コマンド発行前に FIFO の空きを確認
- `jmp $+2` で I/O アクセスに十分な遅延を確保
- GDC リセット (コマンド 00h) で初期状態に戻す

### キーボード入力がおかしい

1. 8251 の初期化状態
2. シフトレジスタの状態 (0000:0522)
3. キーボードバッファのオーバーフロー
4. BIOS がキーボードを正しく制御しているか

### タイマ割り込みがこない

1. IMR (02h / 0Ah) の設定
2. PIT カウンタ 0 のモード設定
3. EOI (End of Interrupt) の送出 (Master: 00h, Slave: 08h)

## 5. パフォーマンス最適化

### I/O アクセス

- 連続 out の間に `jmp $+2` で遅延
- GDC FIFO ステータス確認はループ最小化
- 可能な限りワードアクセスを使用

### VRAM アクセス

- GRCG/EGC 使用で 4 プレーン一括処理
- テキスト VRAM は 1 回のアクセスで 2/4 バイト
- 横方向連続アクセスが最も効率的

### ループ最適化

```asm
; 悪い例 (ループ内 I/O)
loop:
    out dx, al
    loop loop

; 良い例 (アンロール)
    out dx, al
    out dx, al
    out dx, al
    out dx, al
```
