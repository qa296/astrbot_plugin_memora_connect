"""Web界面模块"""
from .server import MemoryWebServer
from .assets import DEFAULT_INDEX_HTML, DEFAULT_STYLE_CSS, DEFAULT_APP_JS

__all__ = ['MemoryWebServer', 'DEFAULT_INDEX_HTML', 'DEFAULT_STYLE_CSS', 'DEFAULT_APP_JS']
