"""
Pytest 配置文件
"""
import os
import sys

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# 配置 pytest
@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_logger():
    """模拟日志器"""
    class MockLogger:
        def __init__(self):
            self.logs = []

        def debug(self, msg, *args, **kwargs):
            self.logs.append(("DEBUG", msg % args if args else msg))

        def info(self, msg, *args, **kwargs):
            self.logs.append(("INFO", msg % args if args else msg))

        def warning(self, msg, *args, **kwargs):
            self.logs.append(("WARNING", msg % args if args else msg))

        def error(self, msg, *args, **kwargs):
            self.logs.append(("ERROR", msg % args if args else msg))
