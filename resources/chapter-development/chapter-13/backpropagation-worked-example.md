# Backpropagation Worked Example

For one sigmoid output:

$$
z=wx+b,\qquad \hat p=\sigma(z)
$$

and binary cross-entropy

$$
L=-[y\log(\hat p)+(1-y)\log(1-\hat p)].
$$

Then

$$
\frac{\partial L}{\partial z}=\hat p-y,
$$

$$
\frac{\partial L}{\partial w}=(\hat p-y)x,
\qquad
\frac{\partial L}{\partial b}=\hat p-y.
$$

With learning rate $\eta$:

$$
w_{new}=w-\eta\frac{\partial L}{\partial w},
\qquad
b_{new}=b-\eta\frac{\partial L}{\partial b}.
$$

The gradient describes sensitivity of the chosen loss to local parameter changes; it does not establish causal meaning.
