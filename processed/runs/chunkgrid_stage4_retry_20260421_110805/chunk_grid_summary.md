# Chunking grid eval

- Questions total: `30`
- Top-K: `12`
- Official-only: `True`
- Grid: `2600:520, 3000:650, 3200:700, 3400:750`

## Summary

| config | strict_hit_rate | avg_coverage | critical_miss_count | avg_source_diversity | avg_chunk_chars_in_topk |
|---|---:|---:|---:|---:|---:|
| cs3200_ov700 | 0.6333 | 0.9167 | 11 | 12.000 | 2875.1 |
| cs3400_ov750 | 0.6333 | 0.9167 | 11 | 12.000 | 3043.7 |
| cs3000_ov650 | 0.6000 | 0.9000 | 11 | 12.000 | 2662.0 |
| cs2600_ov520 | 0.6000 | 0.8667 | 11 | 12.000 | 2323.0 |

## List-focused metric

| config | list_question_hit_rate |
|---|---:|
| cs3200_ov700 | 0.4286 |
| cs3400_ov750 | 0.4286 |
| cs3000_ov650 | 0.2857 |
| cs2600_ov520 | 0.2857 |

## Topic slices (best config)

| slice | questions | strict_hit_rate | avg_coverage |
|---|---:|---:|---:|
| docs_submission | 7 | 0.5714 | 0.8571 |
| refusal | 1 | 0.0000 | 0.5000 |
| equipment_requirements | 5 | 0.4000 | 0.9000 |

## Best config

- `cs3200_ov700` (chunk_size=3200, overlap=700)
- strict_hit_rate=0.6333, avg_coverage=0.9167, critical_miss_count=11
- list_question_hit_rate=0.4286

Detailed JSON: `processed/runs/chunkgrid_stage4_retry_20260421_110805/chunk_grid_summary.json`