# 88 - CG 数据管线：type='CG' 全流程

> 状态：**活动文档**（CG feature 阶段 1 的权威设计 + 实施计划载体；实施落地后按实际代码复核修订本档）。
> 前序关系：CG feature 总体规划（会话定稿）→ **本档**（阶段 1：资源类型入管线）。
> 后续：devdoc 89（解锁 API）→ 90（cg 展示命令）→ 91（画廊入口）→ 92（画廊网格 UI）。
> 适用工程：CG 图作为与背景/立绘同级的一等资源，新增独立类型 `type='CG'`。

---

## 一、背景与决策记录

### 1.1 需求

galgame 的 CG（Event CG / 一览图）需要：
- 剧情中**全屏展示**一张纯图片（语法对标 `bg`，但语义上是"一次性事件图"而非持久背景）。
- 玩家"看过即解锁"，解锁状态落盘（SYSTEM.SAV 的 `cg_flags`）。
- 从主菜单 **gallery** 入口回看已解锁 CG。

本档（阶段 1）只做第一块地基：**让 CG 图成为引擎可寻址的一级资源**。展示命令、解锁、画廊分别由后续 devdoc 落地。

### 1.2 关键决策

| # | 决策 | 理由 |
|---|------|------|
| D1 | CG 走**全新资源类型 `type='CG'`**，不混入 `IMG`/`SPR` 池 | 用户选定。画廊/解锁可精确遍历 `cg_map[]`，不被背景/立绘污染 |
| D2 | CG 在渲染语义上等价**非 sprite 全屏背景**：不透明、透明色 15 不传播、共享全局调色板 | 与 `bg` 同管线，天然支持与背景/CG 同屏切换零冲突（全工程单一调色板） |
| D3 | 仅 `export_asset_table.py` 新增 `cg_map[]` 映射表 + `build_game.py` 放行 `CG` 类型 + validator 感知；**`pack_images.py` 零改动** | 因为 `pack_images.py` 已把"非 ANI 行"一律当普通图像打包（`is_sprite = (type=='SPR')`），CG 走 else 分支即正确 |
| D4 | CG 文件名沿用 `images/<名>.MAG` 约定，`img_map.name` 存引用 key（小写） | 与现有 IMG/SPR 完全同构 |

---

## 二、数据流现状（阶段 1 的改造点）

```
assets/<game>/images.map ──PNG→MAG──▶ projects/<game>/images/*.MAG
                                           │
                                    ASSETS.DB  img_map
                                    ┌──────────────┬──────────────┬──────┐
                                    │ name (key)   │ filename     │ type │
                                    └──────────────┴──────────────┴──────┘
                                           │
            ┌──────────────────────────────┴───────────────────────────────┐
            │ pack_images.py  →  IMAGE.DAT（全图共享调色板重映射）            │
            │ export_asset_table.py  →  nb_asset_table.h（asset_map/…/cg_map）│
            └───────────────────────────────────────────────────────────────┘
```

`img_map` 表结构（已在 demo-a2/ASSETS.DB 中实测兼容）：
```sql
CREATE TABLE img_map (
    id       INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    type     TEXT DEFAULT 'BG',
    name     TEXT DEFAULT ""
);
```
即 `type` 是自由 TEXT，插入 `type='CG'` 无需改表结构。

### 改造点清单（阶段 1）

| # | 文件 | 改动 |
|---|------|------|
| A1 | `tools/naiz_build/build_game.py` | `convert_png_to_mag` 中 `atype not in ('IMG','SPR')` 白名单增加 `'CG'`；转换的 else 分支（`reserved=PROTECTED_IDX_ALL`）天然覆盖 CG（非 sprite） |
| A2 | `tools/naiz_build/export_asset_table.py` | 新增 `cg_map[]` 块：`SELECT id, name FROM img_map WHERE type='CG' ORDER BY id`；返回计数 |
| A3 | `tools/naiz_build/nb_validator.py` | `load_reference` 读 CG key 集；为未来 `cg` 命令做铺垫（本阶段可仅为通过性，不强制消费） |
| A4 | `pack_images.py` | **预期零改动**（D3）。但需回归确认 CG 行 `is_sprite=False`、`transparent_idx=None`、`user_string=b"naiz\x1a"`，与 IMG 一致 |

### 素材登记（作者侧，镜 devdoc80 §4.2 的 ANI 手动 SQL 约定）

```
assets/<game>/images/cgXX.png  （或任意 png）
images.map 加一行：
  images/cgXX.png images/cgXX.MAG --256color

ASSETS.DB 手动插入：
INSERT INTO img_map (name, filename, type) VALUES ('cgXX','images/cgXX.MAG','CG');
```

> 说明：当前 SDK 没有独立的"img_map 登记"自动化入口（与 ANI 手工 SQL 同待遇，见 devdoc80 §4.2 定案），故 CG 登记沿用同一手工 SQL 约定；`makegame.sh build <game>` 全流程自动消费 ASSETS.DB。

---

## 三、阶段 1 细化实现（逐文件）

### A1 build_game.py

`convert_png_to_mag`（当前约 130 行）：
```python
if atype is not None and atype not in ('IMG', 'SPR'):
```
改为：
```python
if atype is not None and atype not in ('IMG', 'SPR', 'CG'):
```
后续 `if atype == 'SPR': … else: kwargs['reserved'] = PROTECTED_IDX_ALL` 分支对 `CG` 走 else（非 sprite），正确。

### A2 export_asset_table.py

在 `anim_map[]` 块之后、`header_footer` 之前插入 `cg_map[]`：
```python
# -- cg_map: CG assets (type='CG') --
lines.append('/* CG asset key->ID lookup (for cg command) */')
lines.append('static const struct { const char *key; int id; } cg_map[] = {')
cg_rows = list(db.execute(
    "SELECT id, name FROM img_map WHERE type='CG' ORDER BY id"
))
if not cg_rows:
    lines.append('    {"__dummy__", 0},')
for row in cg_rows:
    lines.append('    {"%s", %d},' % (escape(row[1]), row[0]))
lines.append('    {NULL, 0}')
lines.append('};')
lines.append('')
```
返回计数从 `return len(img_rows), len(chars), len(exprs), len(spr_rows)` 扩展为含 `len(cg_rows)`，`__main__` 打印同步补 `%d cg`。

> `nb_asset_table.h` 由 `export_asset_table.py` **自动生成、禁止手改**（表头 DO NOT EDIT）。阶段 1 需为 demo-a2 生成含 `cg_map[]` 的表。

### A3 nb_validator.py

`load_reference` 返回值增加 CG key 集：
```python
cur = db.execute("SELECT name FROM img_map WHERE type='CG'")
cg_keys = {row[0] for row in cur}
```
并在返回值元组中纳入（调用处同步解包）。本阶段 validator 不新增对 `.nb` 的 `cg` 命令检查（命令在阶段 3 才有），仅保证类型可被工具链识别、不报"未知类型"。

### A4 pack_images.py 回归要点

核对 `pack_images.py`：
- `load_img_map_assets`: `query='SELECT id, filename, type FROM img_map'` 无类型过滤 → CG 行被读入。
- 主循环 `is_sprite = (asset_type == 'SPR')` → CG=False。
- `remap_pixels_to_palette(..., transparent_idx=15 if is_sprite else None, ...)` → CG 走 `transparent_idx=None`，与 IMG 一致。
- `user_string = (MAG_SPRITE_MARKER+… if is_sprite else b"naiz\x1a")` → CG 走 `b"naiz\x1a"`。
- **结论：CG 行零改动即正确打包。** 需构建回归确认无误报。

---

## 四、Bug 检查（§十七 规则逐条过）

### C 类（本阶段不改 C 代码，跳过；规则基线保持）
- C1–C25：无 C 改动，N/A。

### Python 类

| # | 规则 | 阶段 1 落点 | 检查结论 |
|---|------|------------|---------|
| P1 | 避免裸 `except:` | 未触碰异常处理 | ✓ |
| P2 | `open()` 用 `with` | 新增 SQL 查询无文件 open | ✓ |
| P3 | 不用 `assert` | 无 | ✓ |
| P4/P5 | struct 偏移/长度校验 | 无 struct 改动 | ✓ |
| P6 | 路径用 `Path` | `export_asset_table.py` 仍用 `os.path.join`（既有风格，`nb` 一致） | ✓（保持文件内一致，不引入回归） |
| P8 | 禁止函数体内 import | 无新增 import | ✓ |
| P9 | 禁止可变默认参 | 无 | ✓ |
| P11 | 可变状态跨函数传播 | `cg_rows` 是局部 list，不跨函数传值回写 | ✓ |
| P14 | 禁 eval/exec/os.system | 无 | ✓ |

### 特定于本阶段的风险
- **R-A：`cg_map[]` 空表占位** —— 复用 `{"__dummy__",0}` 哨兵，与 `asset_map` 一致；避免 `{NULL,0}` 前无元素导致遍历越界（C6 精神，Python 侧 id/name 均来自 SQL 行，无越界，但空表必须给合法终止哨兵）。✓
- **R-B：返回计数元组增位** —— `__main__` 解包必须同步，否则 `n_img,n_char,n_expr,n_spr = generate(...)` 对新返回元组会 ValueError。**这是本阶段最易漏的 bug 点**：`generate` 返回 5 元，main 必须 5 元解包。已在 §三.A2 强制标注。
- **R-C：`cg_map` key 与 `asset_map` key 冲突** —— CG 用独立表，`nb_asset_id()` 当前先查 `asset_map` 再查 `spr_asset_map`；`cg` 命令（阶段 3）将只查 `cg_map`，不混入 bg 查询路径，避免同名 key 二义。阶段 1 只生成表，不接命令，无冲突。✓
- **R-D：build_game 白名单漏 `CG` 导致转换阶段直接 exit 1** —— 若漏改 A1，一张 CG 就让 `makegame.sh build` 失败（`ERROR: unknown asset type`）。A1 是阶段 1 必须最先落地项。

---

## 五、验证方案（阶段 1 完成标准）

1. **工具链单元回归**（改 3 个 .py 后）：
   ```bash
   tools/env_setup/venv/bin/python -m py_compile tools/naiz_build/build_game.py \
       tools/naiz_build/export_asset_table.py tools/naiz_build/nb_validator.py
   tools/env_setup/venv/bin/python -m pytest tools/tests/ -q
   ```
2. **为 demo-a2 手工登记一张测试 CG**（临时，供验证；如需保留再定）：
   - 往 `demo-a2/ASSETS.DB` 插一行 `('cg_test','images/cg_test.MAG','CG')`，并备好 `images/cg_test.MAG`。
3. **生成表 + 查表**：
   ```bash
   tools/env_setup/venv/bin/python -m tools.naiz_build.export_asset_table \
       projects/demo-a2 core/engine/nb_asset_table.h
   ```
   确认 `nb_asset_table.h` 出现 `cg_map[]` 且含 `{"cg_test", N}`。
4. **完整数据构建**：
   ```bash
   ./makegame.sh build demo-a2
   ```
   确认 IMAGE.DAT 含 CG 条目、无 ERROR、无共享调色板违规。
5. **验收**：以上全绿后交用户截图/确认，进入阶段 2（devdoc 89）。

---

## 六、范围外（后续阶段）

- `cg` 展示命令 + 解锁（**devdoc 89 / 90**）
- gallery 入口 + 网格 UI（**devdoc 91 / 92**）
- 缩略图（二期独立阶段，未排）
