# 图标资源说明

本目录存放图标的**源文件**与**打包时使用的图标**。其中 `logo.icns` 与 `icon.ico` 只在构建阶段使用；`window_icon.png` 由程序在运行时读取，并通过 PyInstaller 的 `datas` 一并打包。

| 文件 | 用途 | 由谁使用 |
| --- | --- | --- |
| `logo.svg` | 矢量母版，修改图标时从这里改起 | 仅供设计使用，不参与构建 |
| `logo.png` | 1024×1024 位图母版，由 `logo.svg` 导出 | `logo.icns` 与 `icon.ico` 的生成来源 |
| `logo.icns` | macOS `.app` 应用包图标 | `tchMaterial-parser.spec` 中的 `BUNDLE(icon=...)` |
| `icon.ico` | Windows 可执行文件图标 | `tchMaterial-parser.spec` 中的 `EXE(icon=...)` |
| `window_icon.png` | 程序运行时的窗口图标（窗口左上角、Alt+Tab，以及主界面标题旁） | `src/tchmaterial_parser/app.py` 直接读取，`tchMaterial-parser.spec` 负责打包 |
| `last_quarter_moon_3d.png`、`sun_3d.png`、`crescent_moon_3d.png`、`information_3d.png`（来自 [microsoft/fluentui-emoji](https://github.com/microsoft/fluentui-emoji)） | 程序右上角选择主题、关于图标 | `src/tchmaterial_parser/images.py` 直接读取，`tchMaterial-parser.spec` 负责打包 |
| `last_quarter_moon_flat.svg`、`sun_flat.svg`、`crescent_moon_flat.svg`、`information_flat.svg`（来自 [microsoft/fluentui-emoji](https://github.com/microsoft/fluentui-emoji)） | 矢量图 | 仅供设计使用，不参与构建 |

## 更换图标时的操作

修改 `logo.svg` 后，导出一份 1024×1024 的 `logo.png`，然后重新生成下列三个文件。

### 1. 重新生成 `icon.ico`

`icon.ico` 需要包含**多个尺寸**：Windows 在标题栏用 16×16，在桌面用 32×32，在「超大图标」视图下用 256×256。若只放单一尺寸，系统只能拉伸缩放，会明显模糊。

```python
from PIL import Image

Image.open("assets/logo.png").convert("RGBA").save(
    "assets/icon.ico",
    format="ICO",
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
```

### 2. 重新生成 `logo.icns`

在 macOS 上可使用系统自带的 `iconutil`（需先按 `icon_16x16.png`、`icon_16x16@2x.png` 等命名规则准备一个 `logo.iconset` 目录）：

```sh
iconutil -c icns logo.iconset -o assets/logo.icns
```

### 3. 更新 `window_icon.png`

程序以 `assets/window_icon.png` 作为运行时窗口图标的唯一来源。更新图标时直接替换该文件即可，无需再同步源码字符串；`tchMaterial-parser.spec` 会在打包时将它收集到相同的 `assets/` 相对路径。
