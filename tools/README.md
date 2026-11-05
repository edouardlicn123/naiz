# Naiz Tools

Python 辅助工具链。每个子目录是一个独立工具包：

| 目录 | 职责 |
|------|------|
| `naiz_lib/` | 共享模块（MAG 编解码、IMAGE.DAT、调色板、字体容器、NB 行解析、NP2kai 捕获） |
| `naiz_img/` | HDI 镜像操作（open_image / NAIZFatFS / inject） |
| `naiz_build/` | 数据构建（pack_images、nb_validator、export_*、bump_version） |
| `naiz_conv/` | 格式转换（mag_convert、psf2font、ttf2font、i18n_gen、render_title） |
| `diag/` | 诊断工具（串口、FAT 浏览、HDI patch） |
| `diag_c/` | C 诊断程序（`make -C core diag`） |
| `env_setup/` | 环境安装（install_env + venv） |
| `naiz_docs/` | 文档站/图片生成 |
| `naiz_font/` | 字库数据（FONT.DAT / CJK.DAT / BLACK.DAT）与生成器 |
| `naiz_screendig/` | 独立截图诊断工具（P0） |
| `np2kaipatch/` | NP2kai 源码补丁 |
| `tests/` | pytest 单元测试 |

完整索引见 `docs/B90-参考-函数索引.md`。
