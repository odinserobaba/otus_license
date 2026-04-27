# Chunking grid eval

- Questions total: `30`
- Top-K: `12`
- Official-only: `True`
- Grid: `2200:320, 2800:560, 3200:700, 3800:800`

## Summary

| config | strict_hit_rate | avg_coverage | critical_miss_count | avg_source_diversity | avg_chunk_chars_in_topk |
|---|---:|---:|---:|---:|---:|
| cs3200_ov700 | 0.6333 | 0.9167 | 11 | 12.000 | 2129.1 |
| cs3800_ov800 | 0.6333 | 0.9167 | 11 | 12.000 | 2328.3 |
| cs2800_ov560 | 0.6000 | 0.8833 | 11 | 12.000 | 1928.0 |
| cs2200_ov320 | 0.5333 | 0.8833 | 13 | 12.000 | 1530.1 |

## Best config

- `cs3200_ov700` (chunk_size=3200, overlap=700)
- strict_hit_rate=0.6333, avg_coverage=0.9167, critical_miss_count=11

Detailed JSON: `processed/chunk_grid_summary.json`