# -*- coding: utf-8 -*-
# 图像相关的处理：系统彩色 Emoji 字形渲染、主题图标绘制与封面适配

import os, math, subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .platform_utils import os_name, print_error

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
            except Exception as e:
                print_error(e)
                continue
    return None

def draw_theme_icon_fallback(target_theme: str, icon_size: int) -> Image.Image: # 绘制不依赖系统字体的主题图标
    # 在 4 倍分辨率下绘制，坐标系按 16×16 设计
    scale = icon_size / 4
    canvas_size = icon_size * 4

    icon = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)

    yellow = "#F0B429"
    blue = "#5B8DEF"
    system_dark = "#4D6FA9"

    def rounded_line(start: tuple[float, float], end: tuple[float, float], fill: str, width: float) -> None: # 绘制带圆形端点的线段，使太阳光芒在小尺寸下更平滑
        line_width = max(round(width * scale), 1)
        radius = line_width / 2
        start_px = (start[0] * scale, start[1] * scale)
        end_px = (end[0] * scale, end[1] * scale)
        draw.line((start_px, end_px), fill=fill, width=line_width)

        for point_x, point_y in (start_px, end_px):
            draw.ellipse((point_x - radius, point_y - radius, point_x + radius, point_y + radius), fill=fill)

    if target_theme == "light":
        # 太阳主体略小一些，为光芒留出均匀空间
        center = (8.0, 8.0)
        body_radius = 3.0
        ray_inner = 5.2
        ray_outer = 7.1

        for angle in range(0, 360, 45):
            radians = math.radians(angle)
            cos_angle = math.cos(radians)
            sin_angle = math.sin(radians)

            rounded_line(
                (center[0] + cos_angle * ray_inner, center[1] + sin_angle * ray_inner),
                (center[0] + cos_angle * ray_outer, center[1] + sin_angle * ray_outer),
                fill=yellow,
                width=1.05,
            )

        draw.ellipse(
            ((center[0] - body_radius) * scale, (center[1] - body_radius) * scale, (center[0] + body_radius) * scale, (center[1] + body_radius) * scale),
            fill=yellow,
        )

    elif target_theme == "dark":
        # 先绘制圆月，再用独立 alpha 遮罩挖出月牙
        moon_mask = Image.new("L", icon.size, 0)
        moon_draw = ImageDraw.Draw(moon_mask)
        moon_draw.ellipse((2.2 * scale, 1.3 * scale, 13.7 * scale, 14.7 * scale), fill=255)
        moon_draw.ellipse((5.4 * scale, 0.3 * scale, 15.3 * scale, 11.9 * scale), fill=0)
        moon_layer = Image.new("RGBA", icon.size, blue)
        icon.alpha_composite(Image.composite(moon_layer, Image.new("RGBA", icon.size, (0, 0, 0, 0)), moon_mask))

    else:
        # 使用类似 🌗 的双色圆形表示“跟随系统”：左侧暖黄色代表浅色主题，右侧蓝色代表深色主题
        bounds = (2.0 * scale, 2.0 * scale, 14.0 * scale, 14.0 * scale)
        circle_mask = Image.new("L", icon.size, 0)
        circle_draw = ImageDraw.Draw(circle_mask)
        circle_draw.ellipse(bounds, fill=255)
        system_layer = Image.new("RGBA", icon.size, (0, 0, 0, 0))
        system_draw = ImageDraw.Draw(system_layer)
        system_draw.rectangle((2.0 * scale, 2.0 * scale, 8.0 * scale, 14.0 * scale), fill=yellow)
        system_draw.rectangle((8.0 * scale, 2.0 * scale, 14.0 * scale, 14.0 * scale), fill=system_dark)
        icon.alpha_composite(Image.composite(system_layer, Image.new("RGBA", icon.size, (0, 0, 0, 0)), circle_mask))

        # 中线稍微柔和地分隔明暗两侧，在较大尺寸下也更清晰。
        draw.line(
            (8.0 * scale, 2.4 * scale, 8.0 * scale, 13.6 * scale),
            fill=(255, 255, 255, 90),
            width=max(round(0.35 * scale), 1),
        )

    return icon.resize((icon_size, icon_size), Image.Resampling.LANCZOS)

def make_theme_icon_image(target_theme: str, icon_size: int) -> Image.Image: # 优先使用系统 Emoji 的原始字形，无法渲染时使用几何图标
    symbol = "☀️" if target_theme == "light" else "🌙" if target_theme == "dark" else "🌗"
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
