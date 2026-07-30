# -*- coding: utf-8 -*-
# 程序入口：源码运行与 PyInstaller 打包共用此文件
# 入口必须位于包外，因为 PyInstaller 会把它当作 __main__ 分析，包内脚本的相对导入在此情形下不成立

from tchmaterial_parser.app import main

if __name__ == "__main__":
    main()
