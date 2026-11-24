# ClaimCheck metrics: dev split

- Claims: 2681
- Paid/denied accuracy: 97.6%
- Denied precision: 99.9% | recall: 91.7%
- Missed denials (predicted paid, was denied): 64
- False alarms (predicted denied, was paid): 1
- Exact-code accuracy (paid counts as a code): 95.2%
- Ceiling: 51 claims are D99 (unpredictable), so exact-code accuracy cannot exceed 98.1%
- Routed to human review: 4.2%

## Per code
| Code | Actual | Predicted | Correct | Precision | Recall |
|---|---|---|---|---|---|
| D01 | 127 | 110 | 110 | 100.0% | 86.6% |
| D02 | 45 | 44 | 40 | 90.9% | 88.9% |
| D03 | 153 | 186 | 153 | 82.3% | 100.0% |
| D04 | 26 | 27 | 26 | 96.3% | 100.0% |
| D05 | 19 | 20 | 19 | 95.0% | 100.0% |
| D06 | 55 | 53 | 53 | 100.0% | 96.4% |
| D07 | 53 | 61 | 53 | 86.9% | 100.0% |
| D08 | 48 | 55 | 48 | 87.3% | 100.0% |
| D09 | 167 | 150 | 140 | 93.3% | 83.8% |
| D10 | 25 | 0 | 0 | n/a | 0.0% |
| D99 | 51 | 0 | 0 | n/a | 0.0% |
| PAID | 1912 | 1975 | 1911 | 96.8% | 99.9% |

## Largest error groups
| Actual | Predicted | Claims |
|---|---|---|
| D99 | PAID | 49 |
| D09 | D03 | 18 |
| D10 | PAID | 15 |
| D01 | D03 | 10 |
| D10 | D09 | 8 |
| D02 | D03 | 5 |
| D01 | D07 | 4 |
| D09 | D07 | 4 |
| D09 | D08 | 4 |
| D01 | D08 | 3 |
| D06 | D02 | 2 |
| D99 | D09 | 2 |

## Confusion matrix (rows actual, columns predicted)

```
code_pred  D01  D02  D03  D04  D05  D06  D07  D08  D09  PAID
code_true                                                   
D01        110    0   10    0    0    0    4    3    0     0
D02          0   40    5    0    0    0    0    0    0     0
D03          0    0  153    0    0    0    0    0    0     0
D04          0    0    0   26    0    0    0    0    0     0
D05          0    0    0    0   19    0    0    0    0     0
D06          0    2    0    0    0   53    0    0    0     0
D07          0    0    0    0    0    0   53    0    0     0
D08          0    0    0    0    0    0    0   48    0     0
D09          0    0   18    1    0    0    4    4  140     0
D10          0    1    0    0    1    0    0    0    8    15
D99          0    0    0    0    0    0    0    0    2    49
PAID         0    1    0    0    0    0    0    0    0  1911
```
