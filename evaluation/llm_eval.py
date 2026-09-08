# 阶段六/七预留：LLM 输出质量评估器。
# 用途：批量调用智能体 + 对比标注数据集，输出准确率/召回率/幻觉率/延迟报告。
# 接口：Evaluator(agent, dataset).run() -> EvalReport。
# 依赖：evaluation/__init__.py 包初始化 + evaluation/datasets/ 标注数据。
