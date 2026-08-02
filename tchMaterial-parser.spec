# -*- mode: python ; coding: utf-8 -*-
import sys

from PyInstaller.utils.hooks import collect_data_files

is_mac = sys.platform.startswith('darwin')

# sv-ttk 通过 Path(__file__).with_name() 加载主题文件，需把随包的 .tcl 与 .png 一并收集进来；
# 下面 4 个图标文件是程序运行时读取的自有资源，目标目录保持为 assets/，与源码中的相对路径一致
data_files = collect_data_files('sv_ttk') + [
    ('assets/window_icon.png', 'assets'),
    ('assets/sun_3d.png', 'assets'),
    ('assets/crescent_moon_3d.png', 'assets'),
    ('assets/last_quarter_moon_3d.png', 'assets'),
]

a = Analysis(
    # 入口位于包外：PyInstaller 会把入口脚本当作 __main__ 分析，包内脚本的相对导入在此情形下不成立
    # pathex 指向 src/，使入口里的 import tchmaterial_parser 能被解析到
    ['src/main.py'],
    pathex=['src'],
    binaries=[],
    datas=data_files,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)


if is_mac:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='tchMaterial-parser',
        debug=False,
        bootloader_ignore_signals=False,
        strip=True,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='tchMaterial-parser',
    )
    
    app = BUNDLE(
        coll,
        name='tchMaterial-parser.app',
        icon='assets/logo.icns',
        bundle_identifier=None,
    )

else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='tchMaterial-parser',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        version='version_info.txt',
        icon=['assets/icon.ico'],
    )
