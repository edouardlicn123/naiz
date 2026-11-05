# B96 — NB 脚本解析器规范

**代码**：`core/engine/nb_parser.c`
**声明**：`core/engine/nb_internal.h`（不对外暴露）

## 一、职责

把一行 NB 脚本文本拆成「命令名 + 参数指针数组」，**不查命令表、不执行命令、不依赖 hal/render/layer**。

```c
int nb_parse_line(char *line, char *cmd, int cmd_size,
                  const char **args, int max_args, int *brace_arg);
```

## 二、支持的三种行格式

| 格式 | 示例 | 结果 |
|---|---|---|
| 括号参数 | `bg(normal,normal){logo}` | `cmd=bg`，`args=[normal, normal, logo]`，`brace_arg=2` |
| 纯括号 | `scene(mainmenu)` | `cmd=scene`，`args=[mainmenu]`，`brace_arg=-1` |
| 纯花括号 | `say{你好}` | `cmd=say`，`args=[你好]`，`brace_arg=0` |

规则：

- 括号段与花括号段可以共存；**花括号载荷永远是最后一个参数**。
- 逗号分隔，前后空白跳过；空参数保留为空串（`bg(,)` 合法，由命令自行处理）。
- `)` 之后游标若停在 `{`，该段转入花括号参数，不再当作括号参数。

## 三、原地改写约定

- `line` 会被**就地 NUL 截断**（逗号、右括号处写 `\0`），`args[]` 指向 `line` 内部。
- 因此 `args` 的生命周期 = `line` 的生命周期；调用方若要保留原文，必须在调用前复制。
- 参数数超过 `max_args` 时：停止收集，但仍继续扫描到行尾 `)`，保证游标位置正确。

## 四、辅助接口

| 接口 | 用途 |
|---|---|
| `nb_parse_line_semi(line, args, max_args)` | 多段行拆分（`question` / `scene` 等以 `;` 分段的命令） |
| `nb_get_line(buf, line_num)` | 从脚本缓冲提取第 N 行（跳过空行/注释） |

## 五、边界与禁止事项

1. 解析器**不得**调用 `nb_commands.c` 的分派表；命令查找与参数校验属于执行层。
2. 解析器**不得**做任何 I/O、内存分配或 `hal` 调用——它在脚本装载阶段被反复调用。
3. 花括号载荷不做转义处理（`\,` 的还原在执行层），保持 tokenizer 无状态。
4. 新增行格式必须先扩展 `nb_parse_line` 并同步 `nb_internal.h` 注释，再在 `nb_commands.c` 注册命令。

## 六、验收

- 三类格式各有用例覆盖（`tools/tests/` 中的 parser 测试）。
- 任何格式错误行返回 0 参数且 `cmd` 为空串，由执行层统一报 `NB_DEBUG`，解析器自身不打印。
