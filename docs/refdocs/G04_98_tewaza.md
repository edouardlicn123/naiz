# いまさら PC-9801 小手先技巧講座

> **来源**: [吉崎](https://web.archive.org/web/19990224092301/http://www.asahi-net.or.jp/~FZ6Y-YMTR/) の PC-9801 ハードウェア情報
> **技术范围**: GDC, タイマ, I/O, メモリ制御

---

## 1. GDC 技巧

### ライン長変更の実際

GDC のライン長設定コマンド (4Bh) 使用時の注意点:

```asm
; TEXT GDC ライン長変更
mov dx, 60h      ; TEXT GDC コマンドポート
mov al, 4Bh      ; ライン長設定
out dx, al
mov dx, 62h      ; TEXT GDC データポート
mov al, 50       ; 水平トータル
out dx, al
mov al, 40       ; 表示桁数
out dx, al
```

ライン長変更後は VSYNC まで反映されないことがあるので注意。

### ページ切り替えを使った高速描画

```asm
; 裏画面に描画してから一瞬で表示切り替え
mov dx, 0A6h
mov al, 1        ; 绘图页面 = 1 (表)
out dx, al
; ... 绘图处理 ...
; 绘图完成后切换显示页面
mov dx, 0A4h
mov al, 1        ; 显示页面 = 1
out dx, al
```

### 水平スクロール

GDC の表示開始アドレス変更による水平スクロール:
```
; 开始地址 (70h + 8n 格式)
out 0A0h, 70h + n ; 参数 n
; 后续参数设置 GDC 内部寄存器
```

## 2. タイマ割り込みの活用

PIT (8253) カウンタ 0:

```asm
; 変更割り込み周期
mov al, 36h      ; カウンタ0, LSB/MSB, モード3
out 43h, al
mov ax, 5965     ; 50Hz 相当値
out 40h, al      ; LSB
mov al, ah
out 40h, al      ; MSB
```

割り込みハンドラ設定:
```asm
; 独自 INT 08h ハンドラの設定
xor ax, ax
mov ds, ax
mov ax, offset handler
mov [0020h], ax  ; INT 8h ベクタ
mov ax, seg handler
mov [0022h], ax
```

## 3. I/O ポートアクセス最適化

### 連続アクセスの注意

PC-9801 の I/O ポートは 8086 の I/O サイクルに注意:

```asm
; 悪い例 (間に合わない)
out 0A0h, al
out 0A2h, al      ; 連続アクセスで GDC が追いつかない

; 良い例
out 0A0h, al
jmp $+2           ; I/O 遅延
jmp $+2
out 0A2h, al
```

### GDC ステータス待ち

```asm
; GDC FIFO 空き待ち
wait_gdc:
in al, 0A0h       ; GDC ステータス
test al, 08h      ; FIFO に空きがある?
jz wait_gdc
```

## 4. メモリ制御

### EMS ページフレーム

EMS の標準ページフレームは D000:0000 (64KB)。使用時は:

```asm
mov ah, 44h       ; EMS マッピング
mov al, 0         ; 論理ページ 0
mov bx, 0         ; 物理ページ 0
mov dx, handle    ; EMS ハンドル
int 67h
```

### XMS UMB

XMS の UMB (Upper Memory Block) 取得:
```
AH = 10h
call dword ptr [xms_entry]
```

## 5. グラフィック高速化の解説

### GRCG を使った矩形塗りつぶし

```asm
; GRCG RMW モードでの矩形塗りつぶし
mov dx, 7Ch
mov al, 83h       ; GRCG enable + RMW + 全プレーン
out dx, al
mov dx, 7Eh       ; パターンレジスタ
mov ax, 0FFFFh    ; 全面データ=1
out dx, al        ; プレーン0
out dx, al        ; プレーン1
out dx, al        ; プレーン2
out dx, al        ; プレーン3
; VRAM アクセス (任意アドレスへ 1 バイト書き込み = 8 ドット)
mov ax, 0A800h
mov es, ax
mov di, 0         ; Y=0, X=0
mov cx, 80        ; 横幅
rep stosb         ; 塗りつぶし
; GRCG 解除
mov dx, 7Ch
mov al, 00h
out dx, al
```

### EGC を使った高速ブロック転送

```asm
; EGC による 4 プレーン一括 BitBLT 
mov dx, 6Ah
mov al, 07h       ; 拡張モード切替可
out dx, al
mov al, 05h       ; EGC モード
out dx, al
mov dx, 7Ch
mov al, 80h       ; GRCG enable (EGC)
out dx, al
; EGC 設定 (4A0h〜4AEh)
mov dx, 4A0h
mov ax, 0FFF0h    ; 全プレーンアクセス
out dx, ax        ; (Word アクセス必要)
; ... (以降 EGC パラメータ設定)
```

## 6. VSYNC 同期

```asm
; VSYNC 待ち (GDC ステータス)
wait_vsync:
in al, 0A0h       ; GRAPHIC GDC ステータス
test al, 20h      ; VSYNC 実行中?
jnz wait_vsync
; VSYNC 終了を待つ
wait_vsync_end:
in al, 0A0h
test al, 20h
jz wait_vsync_end
```

## 7. CRT タイミング制御

アナログ RGB モードとデジタル RGB モードの違い:

| モード | I/O 6Ah bit6 | 解像度 | 水平同期 |
|--------|-------------|--------|---------|
| CRT デジタル | 0 | 640x400 | 24.83kHz |
| CRT アナログ | 1 | 640x400 | 24.83kHz |
| 高解像度 | 1 | 640x480 | 31.47kHz |

エンジン開発ではアナログ RGB モード (Dsub15pin) が標準。
