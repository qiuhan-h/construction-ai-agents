"""GB 结构化规则数据目录（6a.1）。

本目录存放 5 本国标的机器可判定规则 YAML，由
``agents/compliance_agent/regulation_engine/rule_checker.py``
在运行时通过 ``glob("*.yml")`` 加载。``__init__.py`` 仅用于将该目录标记为
Python 包（规则本身是数据文件，不通过 import 访问）。
"""
