# Ensemble Design Canvas

| Element | Specification |
|---|---|
| Target and prediction time | |
| Baseline | |
| Component model 1 | |
| Component model 2 | |
| Component model 3 | |
| Expected diversity source | |
| Bagging/boosting/voting/stacking | |
| Probability calibration needed? | |
| Meta-model | |
| Out-of-fold strategy | |
| Hyperparameter selection | |
| Validation design | |
| Final test boundary | |
| Computational cost | |
| Error correlation/shared failures | |
| External validation | |
| Meaningful gain threshold | |
| Unsupported claims | |

## Ensemble admission test

Before adding a model, ask:

1. What new predictive structure might it contribute?
2. How are its errors different from existing components?
3. Does it share the same leakage or measurement weaknesses?
4. Does the ensemble improve the metric that matters?
5. Is the improvement larger than evaluation uncertainty?
6. Is the gain worth added complexity, latency, and maintenance?
