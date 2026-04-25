# Fishing Prediction — 纯软件探鱼 / 钓鱼预测姬

基于量化交易的多因子建模思路，做纯软件的鱼情预测 + 市场调研工具。

## 项目结构

| 模块 | 说明 | 状态 |
|------|------|------|
| `module1_market_research` | 钓鱼 App 市场调研爬虫 + 情感分析 | ✅ 可用 |
| `module2_competitive_analysis` | 竞品持续跟踪看板 | ✅ 可用 |
| `module3_prediction_model` | 多因子鱼情预测模型（规则引擎 → ML 增强） | ✅ 可用 |

## 快速开始

### 模块1: 市场调研
```bash
.venv\Scripts\pip install -r requirements-module1.txt
.venv\Scripts\python -m module1_market_research.main all --pages 2
```

### 模块2: 竞品分析
```bash
.venv\Scripts\pip install -r requirements-module2.txt
.venv\Scripts\python -m module2_competitive_analysis.main track
.venv\Scripts\python -m module2_competitive_analysis.main dashboard
```

### 模块3: 鱼情预测
```bash
.venv\Scripts\pip install -r requirements-module3.txt
# 查看因子列表
.venv\Scripts\python -m module3_prediction_model.main info
# 预测指定时间地点 (武汉东湖示例)
.venv\Scripts\python -m module3_prediction_model.main predict --lat 30.5 --lon 114.3 --date 2026-04-26 --hour 6 -v
# 查看全天逐小时预测
.venv\Scripts\python -m module3_prediction_model.main day --lat 30.5 --lon 114.3
```

## License

MIT
