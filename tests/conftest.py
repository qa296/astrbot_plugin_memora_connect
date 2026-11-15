"""
pytest 全局配置：唯一的 astrbot stub 与插件模块加载器。

插件目录名含连字符且测试环境不装 astrbot 包，故约定：
conftest 在此 stub 掉 astrbot.* 全部引用面，并用 importlib 以假包名
``memora.*`` 加载插件子模块；新测试禁止再各自发明 stub。
"""

import logging
import os
import sys
import types
from importlib import util as importlib_util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class _StubCommandGroup:
    """command_group 装饰器的桩：返回带 .command 的对象，供 @memory.command 链式使用。"""

    def command(self, *a, **k):
        return lambda f: f


class _StubFilter:
    """astrbot.api.event.filter 的最小命名空间桩（调用即返回恒等装饰器）。"""

    EventMessageType = type(
        "EventMessageType", (), {"ALL": "all", "GROUP_MESSAGE": "g", "PRIVATE_MESSAGE": "p"}
    )

    def __getattr__(self, name):
        return lambda *a, **k: (lambda f: f)

    command_group = staticmethod(lambda *a, **k: (lambda f: _StubCommandGroup()))


def _module(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


def stub_astrbot() -> None:
    """幂等注册 astrbot.* 桩。"""
    existing = sys.modules.get("astrbot.api")
    if existing is not None and getattr(existing, "logger", None):
        return
    _module("astrbot")
    _module("astrbot.api", logger=logging.getLogger("tests.astrbot"),
            AstrBotConfig=dict)
    _module(
        "astrbot.api.event",
        AstrMessageEvent=type("AstrMessageEvent", (), {}),
        MessageChain=type("MessageChain", (), {}),
        MessageEventResult=type("MessageEventResult", (), {}),
        filter=_StubFilter(),
    )
    _module("astrbot.api.provider", ProviderRequest=type("ProviderRequest", (), {}))

    class _StubStar:
        def __init__(self, context=None):
            self.context = context

    _module(
        "astrbot.api.star",
        Context=type("Context", (), {}),
        Star=_StubStar,
        StarTools=type("StarTools", (), {"get_data_dir": lambda: None}),
        register=lambda *a, **k: (lambda cls: cls),
    )
    _module("astrbot.api.persona_manager")
    _module("astrbot.core")
    _module("astrbot.core.agent")

    class _StubTextPart:
        def __init__(self, text: str = "", **kw):
            self.text = text

        def mark_as_temp(self):
            return self

    _module("astrbot.core.agent.message", TextPart=_StubTextPart)


def _ensure_package(name: str, path: Path) -> None:
    if name in sys.modules:
        return
    mod = types.ModuleType(name)
    mod.__path__ = [str(path)]
    sys.modules[name] = mod
    parent_name, _, child = name.rpartition(".")
    if parent_name and parent_name in sys.modules:
        setattr(sys.modules[parent_name], child, mod)


def load_plugin_modules(module_specs: list[str]) -> dict:
    """按 ``storage.repository`` 这样的 spec 加载插件文件为 ``memora.<spec>``。"""
    stub_astrbot()
    _ensure_package("memora", ROOT)
    loaded: dict = {}
    for spec in module_specs:
        spec = spec.replace("/", ".")
        mod_name = f"memora.{spec}"
        if mod_name in sys.modules:
            loaded[mod_name] = sys.modules[mod_name]
            continue
        file_path = ROOT / (spec.replace(".", os.sep) + ".py")
        spec_obj = importlib_util.spec_from_file_location(mod_name, file_path)
        assert spec_obj and spec_obj.loader, f"cannot load {file_path}"
        module = importlib_util.module_from_spec(spec_obj)
        sys.modules[mod_name] = module
        parent_name, _, child = mod_name.rpartition(".")
        if parent_name in sys.modules:
            setattr(sys.modules[parent_name], child, module)
        spec_obj.loader.exec_module(module)
        loaded[mod_name] = module
    return loaded
