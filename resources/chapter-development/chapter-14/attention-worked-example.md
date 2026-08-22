# Attention Worked Example

For token representations $X$, define

$$
Q=XW_Q,\qquad K=XW_K,\qquad V=XW_V.
$$

Scaled dot-product attention is

$$
Attention(Q,K,V)
=
softmax\left(\frac{QK^\top}{\sqrt{d_k}}\right)V.
$$

## Interpretation

1. Queries describe what each position is seeking.
2. Keys describe what each position offers for matching.
3. Query-key dot products produce compatibility scores.
4. Division by $\sqrt{d_k}$ stabilizes score scale.
5. Softmax converts scores to normalized weights.
6. Values are combined using those weights.

For token $i$:

$$
h_i=\sum_j\alpha_{ij}v_j.
$$

The result is contextual because the representation of token $i$ depends on other tokens.

## Scientific caution

Attention weights describe an internal computational relationship. They are not automatically causal effects, human cognitive attention, or complete explanations.
