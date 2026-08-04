# -*- coding: utf-8 -*-
# 图像相关的处理：系统彩色 Emoji 字形渲染、主题图标绘制与封面适配

import os, subprocess
from pathlib import Path
from typing import Literal
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .platform_utils import os_name, print_error, resource_path

def color_emoji_font_paths() -> list[Path]: # 获取当前系统可能存在的彩色 Emoji 字体
    candidates: list[Path] = []

    if os_name == "Windows":
        windows_dir = Path(os.getenv("WINDIR") or os.getenv("SystemRoot") or "C:/Windows")
        candidates.append(windows_dir / "Fonts" / "seguiemj.ttf") # Segoe UI Emoji
    elif os_name == "Darwin":
        candidates.extend([
            Path("/System/Library/Fonts/Apple Color Emoji.ttc"),
            Path("/System/Library/Fonts/Apple Color Emoji.ttf"),
            Path("/Library/Fonts/Apple Color Emoji.ttc"),
        ])
    elif os_name == "Linux":
        # 各发行版安装 Noto Color Emoji 的目录并不统一，先询问 fontconfig，再检查常见路径
        try:
            result = subprocess.run(
                ["fc-match", "-f", "%{file}\n", "Noto Color Emoji"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0 and result.stdout.strip():
                candidates.append(Path(result.stdout.splitlines()[0].strip()))
        except Exception:
            pass
        candidates.extend([
            Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
            Path("/usr/share/fonts/noto/NotoColorEmoji.ttf"),
            Path("/usr/share/fonts/google-noto-emoji/NotoColorEmoji.ttf"),
            Path.home() / ".local" / "share" / "fonts" / "NotoColorEmoji.ttf",
            Path.home() / ".fonts" / "NotoColorEmoji.ttf",
        ])

    # 去重并忽略不存在的候选项；找不到系统 Emoji 字体时由调用方决定如何显示原字符
    unique_paths: list[Path] = []
    for path in candidates:
        if path.is_file() and path not in unique_paths:
            unique_paths.append(path)
    return unique_paths

def render_system_emoji(symbol: str, icon_size: int) -> Image.Image | None: # 将系统 Emoji 字体中的原始字形渲染为透明背景图像
    # 彩色 Emoji 字体可能是可缩放的 COLR，也可能只有固定字号的 CBDT/SBIX 位图，
    # 因此依次尝试当前 DPI 所需字号及常见的位图 strike 尺寸
    font_sizes = list(dict.fromkeys([max(icon_size * 4, 64), 160, 128, 109, 96, 64, 48, 32]))

    for font_path in color_emoji_font_paths():
        for font_size in font_sizes:
            try:
                font = ImageFont.truetype(str(font_path), font_size)
                measuring_image = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
                measuring_draw = ImageDraw.Draw(measuring_image)
                bounds = measuring_draw.textbbox((0, 0), symbol, font=font, embedded_color=True)
                width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
                if width <= 0 or height <= 0:
                    continue

                padding = max(round(font_size * 0.08), 2)
                rendered = Image.new("RGBA", (round(width + padding * 2), round(height + padding * 2)), (0, 0, 0, 0))
                draw = ImageDraw.Draw(rendered)
                draw.text(
                    (padding - bounds[0], padding - bounds[1]),
                    symbol,
                    font=font,
                    fill=(128, 128, 128, 255), # 仅供没有嵌入颜色层的字形使用；系统自带的彩色或灰白图层会保留原貌
                    embedded_color=True,
                )
                content_bounds = rendered.getbbox()
                if not content_bounds:
                    continue
                rendered = rendered.crop(content_bounds)

                fit_size = max(icon_size - 2, 1)
                scale = min(fit_size / rendered.width, fit_size / rendered.height)
                resized = rendered.resize(
                    (max(round(rendered.width * scale), 1), max(round(rendered.height * scale), 1)),
                    Image.Resampling.LANCZOS,
                )
                icon = Image.new("RGBA", (icon_size, icon_size), (0, 0, 0, 0))
                icon.alpha_composite(resized, ((icon_size - resized.width) // 2, (icon_size - resized.height) // 2))
                return icon
            except Exception as e:
                continue
    return None

def make_icon_image(icon_name: Literal["system", "light", "dark", "about"], icon_size: int) -> Image.Image: # 优先使用系统 Emoji 的原始字形，无法渲染时使用图片
    icon_mapping = {
        "system": ("🌗", "last_quarter_moon_3d.png"),
        "light": ("☀️", "sun_3d.png"),
        "dark": ("🌙", "crescent_moon_3d.png"),
        "about": ("ℹ️", "information_3d.png")
    }
    emoji_icon = render_system_emoji(icon_mapping[icon_name][0], icon_size)
    if emoji_icon is not None:
        return emoji_icon

    with Image.open(resource_path("assets", icon_mapping[icon_name][1])) as icon:
        icon_image = icon.copy()
    icon_image.thumbnail((icon_size, icon_size), Image.Resampling.LANCZOS)
    return icon_image

def fit_cover_image(image: Image.Image, size: tuple[int, int]) -> Image.Image: # 按原始比例将封面居中放进透明画布
    cover = ImageOps.exif_transpose(image).convert("RGBA")
    cover.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.alpha_composite(cover, ((size[0] - cover.width) // 2, (size[1] - cover.height) // 2))
    return canvas
