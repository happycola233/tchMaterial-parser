# -*- coding: utf-8 -*-
# 图像相关的处理：系统彩色 Emoji 字形渲染、主题图标绘制与封面适配

import os, math, subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .platform_utils import os_name

def color_emoji_font_paths() -> list[Path]: # 获取当前系统可能存在的彩色 Emoji 字体
    candidates: list[Path] = []

    if os_name == "Windows":
        windows_dir = Path(os.environ.get("WINDIR") or os.environ.get("SystemRoot") or "C:/Windows")
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
        except (FileNotFoundError, subprocess.SubprocessError):
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
                rendered = Image.new("RGBA", (width + padding * 2, height + padding * 2), (0, 0, 0, 0))
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
            except (OSError, ValueError):
                continue
    return None

def draw_theme_icon_fallback(target_theme: str, icon_size: int) -> Image.Image: # 绘制无须系统字体的月亮或太阳图标
    # 先以 4 倍尺寸绘制再缩小，使曲线和斜线在高 DPI 与普通屏幕上都保持平滑
    draw_scale = icon_size / 4
    icon = Image.new("RGBA", (icon_size * 4, icon_size * 4), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)

    if target_theme == "dark": # 蓝色月牙表示点击后切换到深色模式
        draw.ellipse(
            (round(2.2 * draw_scale), round(1.4 * draw_scale), round(13.6 * draw_scale), round(14.6 * draw_scale)),
            fill="#5b8def",
        )
        draw.ellipse(
            (round(5.4 * draw_scale), round(0.4 * draw_scale), round(15.2 * draw_scale), round(11.8 * draw_scale)),
            fill=(0, 0, 0, 0),
        )
    else: # 暖黄色太阳表示点击后切换到浅色模式
        center = 8 * draw_scale
        ray_inner = 5.3 * draw_scale
        ray_outer = 7.2 * draw_scale
        ray_width = max(round(1.25 * draw_scale), 1)
        for angle in range(0, 360, 45):
            radians = math.radians(angle)
            start = (center + math.cos(radians) * ray_inner, center + math.sin(radians) * ray_inner)
            end = (center + math.cos(radians) * ray_outer, center + math.sin(radians) * ray_outer)
            draw.line((start, end), fill="#f0b429", width=ray_width)
        radius = 3.2 * draw_scale
        draw.ellipse((center - radius, center - radius, center + radius, center + radius), fill="#f0b429")

    return icon.resize((icon_size, icon_size), Image.Resampling.LANCZOS)

def make_theme_icon_image(target_theme: str, icon_size: int) -> Image.Image: # 优先使用系统 Emoji 的原始字形，无法渲染时使用几何图标
    symbol = "🌙" if target_theme == "dark" else "☀️"
    emoji_icon = render_system_emoji(symbol, icon_size)
    if emoji_icon is not None:
        return emoji_icon
    return draw_theme_icon_fallback(target_theme, icon_size)

def fit_cover_image(image: Image.Image, size: tuple[int, int]) -> Image.Image: # 按原始比例将封面居中放进透明画布
    cover = ImageOps.exif_transpose(image).convert("RGBA")
    cover.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.alpha_composite(cover, ((size[0] - cover.width) // 2, (size[1] - cover.height) // 2))
    return canvas
