# -*- coding: utf-8 -*-
# 本地配置的读写（Windows 用注册表，其余平台用 JSON 文件）与 Access Token 的维护

import json, os
from pathlib import Path

from .network import headers
from .platform_utils import os_name, print_error, winreg

access_token: str | None = None

REGISTRY_PATH = "Software\\tchMaterial-parser" # Windows 下存放配置的注册表键
CONFIG_KEYS = { "access_token": "AccessToken", "theme": "Theme" } # 配置项名称到注册表值名称的映射（JSON 文件直接使用配置项名称）

def config_file_path() -> Path | None: # 获取配置文件路径
    if os_name == "Windows": # 在 Windows 上，配置存放于 %LOCALAPPDATA%\tchMaterial-parser\data.json（此处为备用）
        return Path(
            os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local",
            "tchMaterial-parser",
            "data.json",
        )
    elif os_name in ("Linux", "Android"): # 在 Linux 上，配置存放于 ~/.config/tchMaterial-parser/data.json
        return Path.home() / ".config" / "tchMaterial-parser" / "data.json"
    elif os_name == "Darwin": # 在 macOS 上，配置存放于 ~/Library/Application Support/tchMaterial-parser/data.json
        return Path.home() / "Library" / "Application Support" / "tchMaterial-parser" / "data.json"

def config_location() -> str: # 获取配置存放位置的描述文本，用于提示用户
    if os_name == "Windows":
        return f"已写入注册表：HKEY_CURRENT_USER\\{REGISTRY_PATH}"
    elif os_name in ("Linux", "Android"):
        return "已保存至文件：~/.config/tchMaterial-parser/data.json"
    elif os_name == "Darwin":
        return "已保存至文件：~/Library/Application Support/tchMaterial-parser/data.json"
    else:
        return "本工具尚未支持该操作系统下 Access Token 的持久化，下次启动时仍需手动输入 Access Token。"

def load_config() -> dict[str, str]: # 读取本地存储的配置
    config: dict[str, str] = {}

    if os_name == "Windows": # 在 Windows 上，从注册表读取
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH, 0, winreg.KEY_READ) as key:
                for name, value_name in CONFIG_KEYS.items():
                    try:
                        value, _ = winreg.QueryValueEx(key, value_name)
                    except FileNotFoundError: # 该配置项尚未写入
                        continue
                    if not isinstance(value, str):
                        print_error(TypeError(f"配置项 {name} 必须是字符串"))
                        continue
                    config[name] = value
            return config
        except FileNotFoundError: # 注册表键不存在，即从未保存过配置
            return {}
        except Exception as e:
            print_error(e)
            return {}

    try:
        target_file = config_file_path() # 在其他平台上，从 JSON 文件读取
        if not target_file or not os.path.exists(target_file): # 文件不存在表示尚未保存过配置
            return {}
        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            print_error(TypeError("配置文件的根节点必须是对象"))
            return {}
        for name in CONFIG_KEYS:
            if name not in data:
                continue
            value = data[name]
            if not isinstance(value, str):
                print_error(TypeError(f"配置项 {name} 必须是字符串"))
                continue
            config[name] = value
        return config
    except Exception as e:
        print_error(e)
        return {}

def save_config(**updates: str) -> None: # 保存配置，并与已有配置合并
    if os_name == "Windows": # 在 Windows 上，写入注册表
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH) as key:
            for name, value in updates.items():
                winreg.SetValueEx(key, CONFIG_KEYS[name], 0, winreg.REG_SZ, value)
        return

    target_file = config_file_path() # 在其他平台上，写入 JSON 文件
    data = load_config() # 先读取已有配置，避免覆盖其他配置项
    data.update(updates)
    os.makedirs(os.path.dirname(target_file), exist_ok=True)
    with open(target_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_access_token(config: dict[str, str]) -> None: # 从已读取的配置中加载 Access Token
    global access_token

    token = config.get("access_token")
    if token:
        access_token = token
        headers["Authorization"] = f"Bearer {access_token}"
        headers["X-ND-AUTH"] = f'MAC id="{access_token}",nonce="0",mac="0"'

def set_access_token(token: str) -> str: # 设置并更新 Access Token
    global access_token
    save_config(access_token=token)
    access_token = token
    headers["Authorization"] = f"Bearer {access_token or '0'}"
    headers["X-ND-AUTH"] = f'MAC id="{access_token or "0"}",nonce="0",mac="0"'
    return f"Access Token 已保存！\n{config_location()}"
