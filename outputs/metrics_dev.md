# ClaimCheck metrics: dev split

- Claims: 2681
- Paid/denied accuracy: 98.4%
- Denied precision: 99.9% | recall: 94.4%
- Missed denials (predicted paid, was denied): 43
- False alarms (predicted denied, was paid): 1
- Exact-code accuracy (paid counts as a code): 98.1%
- Ceiling: 51 claims are D99 (unpredictable), so exact-code accuracy cannot exceed 98.1%
- Routed to human review: 1.6%

## Per code
| Code | Actual | Predicted | Correct | Precision | Recall |
|---|---|---|---|---|---|
| D01 | 127 | 127 | 127 | 100.0% | 100.0% |
| D02 | 45 | 46 | 45 | 97.8% | 100.0% |
| D03 | 153 | 153 | 153 | 100.0% | 100.0% |
| D04 | 26 | 26 | 26 | 100.0% | 100.0% |
| D05 | 19 | 19 | 19 | 100.0% | 100.0% |
| D06 | 55 | 55 | 55 | 100.0% | 100.0% |
| D07 | 53 | 53 | 53 | 100.0% | 100.0% |
| D08 | 48 | 48 | 48 | 100.0% | 100.0% |
| D09 | 167 | 167 | 167 | 100.0% | 100.0% |
| D10 | 25 | 33 | 25 | 75.8% | 100.0% |
| D99 | 51 | 0 | 0 | n/a | 0.0% |
| PAID | 1912 | 1954 | 1911 | 97.8% | 99.9% |

## Largest error groups
| Actual | Predicted | Claims |
|---|---|---|
| D99 | PAID | 43 |
| D99 | D10 | 8 |
| PAID | D02 | 1 |

## Confusion matrix (rows actual, columns predicted)

```
code_pred  D01  D02  D03  D04  D05  D06  D07  D08  D09  D10  PAID
code_true                                                        
D01        127    0    0    0    0    0    0    0    0    0     0
D02          0   45    0    0    0    0    0    0    0    0     0
D03          0    0  153    0    0    0    0    0    0    0     0
D04          0    0    0   26    0    0    0    0    0    0     0
D05          0    0    0    0   19    0    0    0    0    0     0
D06          0    0    0    0    0   55    0    0    0    0     0
D07          0    0    0    0    0    0   53    0    0    0     0
D08          0    0    0    0    0    0    0   48    0    0     0
D09          0    0    0    0    0    0    0    0  167    0     0
D10          0    0    0    0    0    0    0    0    0   25     0
D99          0    0    0    0    0    0    0    0    0    8    43
PAID         0    1    0    0    0    0    0    0    0    0  1911
```
