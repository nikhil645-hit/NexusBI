# 📊 Text-to-SQL Accuracy Benchmark Report

- **Timestamp**: `2026-11-09T09:29:16.512599+00:00`
- **Benchmark Mode**: `live`
- **Evaluation Set**: `heldout`
- **LLM Evaluated**: `GroqCloudAdapter`
- **Total Test Questions**: `10`
- **Strict Accuracy**: **`100.0%`** (10/10)
- **Lenient Accuracy**: **`100.0%`** (10/10)
- **Average Query Latency**: `1625.43 ms`

> [!NOTE]
> **Strict scoring** requires exact matrix shape match (1:1 column projection).
> **Lenient scoring** requires matching row count and all expected column values, but permits harmless extra helper columns.

## 🎯 Accuracy by Difficulty

| Difficulty | Total Questions | Strict Passed | Strict % | Lenient Passed | Lenient % |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Easy** | 4 | 4 | 100.0% | 4 | 100.0% |
| **Medium** | 4 | 4 | 100.0% | 4 | 100.0% |
| **Hard** | 2 | 2 | 100.0% | 2 | 100.0% |

## 🔬 Failure Analysis (Strict Scoring)

All benchmark questions passed strict semantic validation against ground truth.