# Model results

Selected model: **hgb** (version `hgb-v1`), chosen on validation PR-AUC; a more complex model must win by at least 0.02.

`*_at_capacity` = flag the top 10 transactions per day for analyst review.

| Split | Rows | Fraud cases | Fraud rate |
|---|---:|---:|---:|
| train (2026-02-01 to 2026-04-30) | 21116 | 309 | 1.46% |
| validation (2026-05-01 to 2026-05-31) | 7236 | 111 | 1.53% |
| test (2026-06-01 to 2026-06-30) | 6902 | 84 | 1.22% |

| split | model | pr_auc | precision_at_capacity | recall_at_capacity | f1_at_capacity | accuracy_at_capacity | tp | fp | fn | tn |
|---|---|---|---|---|---|---|---|---|---|---|
| validation | always_legit | 0.0153 | 0.0 | 0.0 | 0.0 | 0.9847 | 0 | 0 | 111 | 7125 |
| validation | rules | 0.8428 | 0.3226 | 0.9009 | 0.4751 | 0.9695 | 100 | 210 | 11 | 6915 |
| validation | logreg | 0.93 | 0.329 | 0.9189 | 0.4846 | 0.97 | 102 | 208 | 9 | 6917 |
| validation | hgb | 0.9659 | 0.3323 | 0.9279 | 0.4893 | 0.9703 | 103 | 207 | 8 | 6918 |
| test | always_legit | 0.0122 | 0.0 | 0.0 | 0.0 | 0.9878 | 0 | 0 | 84 | 6818 |
| test | rules | 0.8802 | 0.2667 | 0.9524 | 0.4167 | 0.9675 | 80 | 220 | 4 | 6598 |
| test | logreg | 0.9597 | 0.27 | 0.9643 | 0.4219 | 0.9678 | 81 | 219 | 3 | 6599 |
| test | hgb | 0.9838 | 0.2667 | 0.9524 | 0.4167 | 0.9675 | 80 | 220 | 4 | 6598 |
