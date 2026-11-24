# ClaimCheck metrics: test split

- Claims: 1149
- Paid/denied accuracy: 98.4%
- Denied precision: 100.0% | recall: 94.5%
- Missed denials (predicted paid, was denied): 18
- False alarms (predicted denied, was paid): 0
- Exact-code accuracy (paid counts as a code): 98.0%
- Ceiling: 22 claims are D99 (unpredictable), so exact-code accuracy cannot exceed 98.1%
- Routed to human review: 1.7%

## Per code
| Code | Actual | Predicted | Correct | Precision | Recall |
|---|---|---|---|---|---|
| D01 | 54 | 54 | 54 | 100.0% | 100.0% |
| D02 | 20 | 20 | 20 | 100.0% | 100.0% |
| D03 | 65 | 64 | 64 | 100.0% | 98.5% |
| D04 | 11 | 11 | 11 | 100.0% | 100.0% |
| D05 | 8 | 9 | 8 | 88.9% | 100.0% |
| D06 | 24 | 24 | 24 | 100.0% | 100.0% |
| D07 | 22 | 22 | 22 | 100.0% | 100.0% |
| D08 | 22 | 22 | 22 | 100.0% | 100.0% |
| D09 | 72 | 72 | 72 | 100.0% | 100.0% |
| D10 | 10 | 14 | 10 | 71.4% | 100.0% |
| D99 | 22 | 0 | 0 | n/a | 0.0% |
| PAID | 819 | 837 | 819 | 97.8% | 100.0% |

## Largest error groups
| Actual | Predicted | Claims |
|---|---|---|
| D99 | PAID | 18 |
| D99 | D10 | 4 |
| D03 | D05 | 1 |

## Confusion matrix (rows actual, columns predicted)

```
code_pred  D01  D02  D03  D04  D05  D06  D07  D08  D09  D10  PAID
code_true                                                        
D01         54    0    0    0    0    0    0    0    0    0     0
D02          0   20    0    0    0    0    0    0    0    0     0
D03          0    0   64    0    1    0    0    0    0    0     0
D04          0    0    0   11    0    0    0    0    0    0     0
D05          0    0    0    0    8    0    0    0    0    0     0
D06          0    0    0    0    0   24    0    0    0    0     0
D07          0    0    0    0    0    0   22    0    0    0     0
D08          0    0    0    0    0    0    0   22    0    0     0
D09          0    0    0    0    0    0    0    0   72    0     0
D10          0    0    0    0    0    0    0    0    0   10     0
D99          0    0    0    0    0    0    0    0    0    4    18
PAID         0    0    0    0    0    0    0    0    0    0   819
```
