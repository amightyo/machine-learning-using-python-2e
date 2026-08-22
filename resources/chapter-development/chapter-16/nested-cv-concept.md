# Nested Cross-Validation Concept

Nested cross-validation separates selection from assessment.

For each outer fold:

1. hold out the outer test fold;
2. use only the remaining outer-training data;
3. run hyperparameter tuning using inner cross-validation;
4. select the best configuration within the inner loop;
5. refit using the outer-training data;
6. evaluate once on the untouched outer test fold.

Conceptually:

$$
\text{outer training}
\rightarrow
\boxed{\text{inner model selection}}
\rightarrow
\text{selected procedure}
\rightarrow
\boxed{\text{outer assessment}}.
$$

The average outer-fold score estimates performance of the complete model-selection procedure.
