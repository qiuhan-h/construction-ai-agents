"""core.gis：GIS 集成层顶层入口（占位）。

状态：5b 阶段占位未实装。实际 GIS 功能在
``agents/site_monitor_agent/gis_monitoring/`` 已实现（geofencing /
spatial_monitor 等）。

5c 阶段计划：
- ``engine.py``：GIS 引擎基类（坐标变换 / 空间索引 / 图层管理）
- ``services/coordinate_transform.py``：WGS84 ↔ GCJ-02 ↔ BD-09
- ``services/geocoding.py``：地址 ↔ 坐标
- ``services/routing.py``：路径规划
- ``layers/``：安全 / 环境 / 施工图层

当前请直接从 ``agents.site_monitor_agent.gis_monitoring`` 导入 GIS 工具。
"""
