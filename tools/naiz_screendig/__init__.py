"""
NP2kai 截图调试工具

专门用于 NP2kai 模拟器渲染问题的调试。
支持连续截图、自动分析、报告生成。
"""

from .capture import NP2kaiCapture

__version__ = "1.0.0"


def ScreenDig(*args, **kwargs):
    """Lazy import of ScreenDig (requires PIL/numpy)"""
    from .screendig import ScreenDig as _ScreenDig
    return _ScreenDig(*args, **kwargs)


def NP2kaiAnalyzer(*args, **kwargs):
    """Lazy import of NP2kaiAnalyzer (requires PIL/numpy)"""
    from .analyze import NP2kaiAnalyzer as _NP2kaiAnalyzer
    return _NP2kaiAnalyzer(*args, **kwargs)
