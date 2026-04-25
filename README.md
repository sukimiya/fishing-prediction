# Fishing Prediction — 纯软件探鱼 / 钓鱼预测姬

基于量化交易的多因子建模思路，做纯软件的鱼情预测 + 市场调研工具。

## 项目结构

| 模块 | 说明 | 状态 |
|------|------|------|
| `module1_market_research` | 钓鱼 App 市场调研爬虫 + 情感分析 | ✅ 可用 |
| `module2_competitive_analysis` | 竞品持续跟踪看板 | ⏳ 即将开始 |
| `module3_prediction_model` | 多因子鱼情预测模型（规则引擎 → ML 增强） | ⏳ 即将开始 |

## 快速开始

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements-module1.txt
.venv\Scripts\python -m module1_market_research.main all --pages 2
```

## License

MIT
