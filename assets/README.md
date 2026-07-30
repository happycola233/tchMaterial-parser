# 图标资源说明

本目录存放图标的**源文件**与**打包时使用的图标**。这些文件在程序运行时都不会被读取，
它们要么在打包阶段由 PyInstaller 烧进可执行文件，要么以 base64 的形式写死在源码中。

| 文件 | 用途 | 由谁使用 |
| --- | --- | --- |
| `logo.svg` | 矢量母版，修改图标时从这里改起 | 仅供设计使用，不参与构建 |
| `logo.png` | 1024×1024 位图母版，由 `logo.svg` 导出 | `logo.icns` 与 `icon.ico` 的生成来源 |
| `logo.icns` | macOS `.app` 应用包图标 | `tchMaterial-parser.spec` 中的 `BUNDLE(icon=...)` |
| `icon.ico` | Windows 可执行文件图标 | `tchMaterial-parser.spec` 中的 `EXE(icon=...)` |
| `window_icon.png` | 程序运行时的窗口图标（窗口左上角、Alt+Tab） | 以 base64 形式内嵌于 `src/tchmaterial_parser.py` 的 `set_icon()` 中 |

## 更换图标时的操作

修改 `logo.svg` 后，导出一份 1024×1024 的 `logo.png`，然后重新生成下列三个文件。

### 1. 重新生成 `icon.ico`

`icon.ico` 需要包含**多个尺寸**：Windows 在标题栏用 16×16，在桌面用 32×32，在「超大图标」
视图下用 256×256。若只放单一尺寸，系统只能拉伸缩放，会明显模糊。

```python
from PIL import Image

Image.open("assets/logo.png").convert("RGBA").save(
    "assets/icon.ico",
    format="ICO",
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
```

### 2. 重新生成 `logo.icns`

在 macOS 上可使用系统自带的 `iconutil`（需先按 `icon_16x16.png`、`icon_16x16@2x.png` 等
命名规则准备一个 `logo.iconset` 目录）：

```sh
iconutil -c icns logo.iconset -o assets/logo.icns
```

### 3. 同步 `window_icon.png` 与源码中的 base64

窗口图标是以 base64 字符串**写死在源码里**的（这样打包时无需额外附带资源文件）。
更新 `window_icon.png` 后，必须重新生成这段字符串并替换 `set_icon()` 中的内容，否则
窗口图标不会跟着变化：

```python
import base64

with open("assets/window_icon.png", "rb") as f:
    print(base64.b64encode(f.read()).decode())
```
