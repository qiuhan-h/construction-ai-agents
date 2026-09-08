"""agents 公共 API。

阶段二仅暴露抽象基类与注册装饰器；具体业务智能体
（safety_audit / compliance / site_monitor）在阶段三/四实装。
"""

from agents.base_agent import BaseAgent, register_agent

__all__ = [
    "BaseAgent",
    "register_agent",
]
