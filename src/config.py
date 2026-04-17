"""
配置加载模块
- 读取 config.yaml
- 环境变量替换 ${VAR} 占位符
- 根据 mode 自动选择 test/daily 参数
"""

import os
import re
import yaml
import logging

logger = logging.getLogger(__name__)

_config = None


def _resolve_env_vars(value):
    """递归替换配置值中的 ${ENV_VAR} 为环境变量。"""
    if isinstance(value, str):
        def replacer(match):
            var_name = match.group(1)
            env_val = os.environ.get(var_name, "")
            if not env_val:
                logger.warning(f"环境变量 {var_name} 未设置")
            return env_val
        return re.sub(r'\$\{(\w+)\}', replacer, value)
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value


def load_config(config_path: str = None) -> dict:
    """加载并缓存配置。"""
    global _config
    if _config is not None:
        return _config

    if config_path is None:
        # 从项目根目录找 config.yaml
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(root, "config.yaml")

    logger.info(f"加载配置: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    _config = _resolve_env_vars(raw)
    return _config


def get_mode() -> str:
    """返回当前模式: test 或 daily。"""
    cfg = load_config()
    return cfg.get("mode", "daily")


def get_mode_value(section: dict):
    """从含 test/daily 键的 section 中取当前模式对应的值。

    例如: get_mode_value(cfg["discover"]["keyword_pages"])
    在 test 模式下返回 2，daily 模式下返回 1。
    """
    mode = get_mode()
    if isinstance(section, dict) and mode in section:
        return section[mode]
    return section


def setup_logging():
    """根据配置初始化日志。"""
    cfg = load_config()
    log_dir = cfg.get("logging", {}).get("dir", "logs")
    level_map = cfg.get("logging", {}).get("level", {})
    mode = get_mode()
    level_name = level_map.get(mode, "INFO")
    level = getattr(logging, level_name.upper(), logging.INFO)

    # 确保日志目录存在
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_path = os.path.join(root, log_dir)
    os.makedirs(log_path, exist_ok=True)

    log_file = os.path.join(log_path, "monitor.log")

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    logging.info(f"日志初始化完成 mode={mode} level={level_name}")
