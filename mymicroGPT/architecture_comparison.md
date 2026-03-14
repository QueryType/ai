# Architecture Comparison: train.py vs train_mps.py

A detailed comparison of the two Devanagari MicroGPT training implementations.

---

## Overview

| | `train.py` (Pure Python) | `train_mps.py` (PyTorch + MPS) |
|---|---|---|
| **Dependencies** | None (stdlib only) | PyTorch |
| **Autograd** | Custom scalar `Value` class | `torch.autograd` |
| **Data type** | Python lists of `Value` objects | `torch.Tensor` (float32) |
| **Device** | CPU only | MPS (Apple Silicon GPU) or CPU |
| **Wall clock (3K steps)** | 36 min 3 sec | 58 sec |
| **Best avg loss** | 3.108 | 2.642 |

---

## 1. Autograd Engine

### Pure Python: Scalar `Value` Class

Every floating-point number is wrapped in a `Value` object that tracks its computation graph:

```python
class Value:
    def __init__(self, data, _children=(), _op=''):
        self.data = data        # the actual float
        self.grad = 0           # accumulated gradient
        self._backward = lambda: None
        self._prev = set(_children)
```

Each arithmetic operation (`+`, `*`, `**`, `exp`, `log`, `relu`) creates a new `Value` node and registers a `_backward` closure. Calling `loss.backward()` does a topological sort of the entire graph and walks it in reverse, calling each node's `_backward`.

For a single training step on a 10-character name with 8,880 parameters, this builds and traverses a graph of **hundreds of thousands** of `Value` nodes.

### PyTorch: Tensor Autograd

Parameters are `torch.Tensor` with `requires_grad=True`:

```python
def init_matrix(nout, nin, std=0.02):
    return (torch.randn(nout, nin) * std).to(device).requires_grad_(True)
```

PyTorch builds a computation graph over tensors (not scalars), and `total_loss.backward()` computes all gradients in one optimized C++/Metal pass. The graph has only **dozens of nodes** (one per tensor operation), each operating on entire matrices.

---

## 2. Linear Algebra

### Pure Python: Element-by-Element Loops

```python
def linear(x, w):
    return [sum(w[o][i] * x[i] for i in range(len(x))) for o in range(len(w))]
```

A matrix-vector multiply is a nested Python loop — O(n*m) individual `Value` multiplications and additions, each creating new graph nodes.

### PyTorch: Vectorized Tensor Operations

```python
q = x_norm @ state_dict[f'layer{li}.attn_wq'].T  # single op, entire matrix
```

One `@` operator dispatches to optimized BLAS/Metal kernels that process the entire matrix multiply in parallel on the GPU.

---

## 3. Multi-Head Attention

### Pure Python: Explicit Per-Head Loop

```python
x_attn = []
for h in range(n_head):
    hs = h * head_dim
    q_h = q[hs:hs+head_dim]
    k_h = [ki[hs:hs+head_dim] for ki in keys[li]]
    v_h = [vi[hs:hs+head_dim] for vi in values[li]]
    attn_logits = [sum(q_h[j] * k_h[t][j] for j in range(head_dim)) / head_dim**0.5
                   for t in range(len(k_h))]
    attn_weights = softmax(attn_logits)
    head_out = [sum(attn_weights[t] * v_h[t][j] for t in range(len(v_h)))
                for j in range(head_dim)]
    x_attn.extend(head_out)
```

Each head is processed sequentially. Attention scores and weighted sums are computed with nested list comprehensions over `Value` objects.

### PyTorch: Reshape + Einsum

```python
q_heads = q.view(n_head, head_dim)
k_heads = k_stack.view(seq_len, n_head, head_dim)
v_heads = v_stack.view(seq_len, n_head, head_dim)

attn_logits = torch.einsum('hd,shd->hs', q_heads, k_heads) / (head_dim ** 0.5)
attn_weights = F.softmax(attn_logits, dim=-1)
head_out = torch.einsum('hs,shd->hd', attn_weights, v_heads)
x_attn = head_out.reshape(n_embd)
```

All heads are processed simultaneously via `view` (zero-copy reshape) and `einsum` (batched tensor contraction). No Python loop over heads.

---

## 4. Softmax and RMSNorm

### Pure Python

```python
def softmax(logits):
    max_val = max(v.data for v in logits)
    exps = [(v - max_val).exp() for v in logits]
    total = sum(exps)
    return [e / total for e in exps]

def rmsnorm(x):
    ms = sum(xi * xi for xi in x) / len(x)
    scale = (ms + 1e-5) ** -0.5
    return [xi * scale for xi in x]
```

Each call creates N new `Value` nodes (one per element).

### PyTorch

```python
# softmax
F.softmax(logits, dim=-1)  # single fused kernel

# rmsnorm
def rmsnorm(x):
    ms = (x * x).mean(dim=-1, keepdim=True)
    return x * (ms + 1e-5).rsqrt()
```

Single kernel launches operating on entire tensors.

---

## 5. Backward Pass Strategy

### Pure Python: Per-Position Backward

```python
for pos_id in range(len(tokens) - 1):
    logits = gpt(tokens[pos_id], pos_id, keys, values)
    probs = softmax(logits)
    loss = -probs[tokens[pos_id + 1]].log()
    loss = (1 / (len(tokens) - 1)) * loss
    loss.backward()  # backward called at EACH position
```

Gradients are accumulated across positions via repeated `backward()` calls. Each call triggers a full topological sort and graph traversal for that position's subgraph.

### PyTorch: Single Backward for Entire Sequence

```python
total_loss = torch.tensor(0.0, device=device)
for pos_id in range(len(tokens) - 1):
    logits = gpt(token_id, pos_id, keys, values)
    prob = F.softmax(logits, dim=-1)
    loss = -torch.log(prob[next_token] + 1e-10)
    total_loss = total_loss + loss / (len(tokens) - 1)

total_loss.backward()  # single backward for entire sequence
```

The computation graph for all positions is built up, then a single `backward()` call computes all gradients at once. This is more memory-efficient and numerically stable.

---

## 6. Adam Optimizer

### Pure Python: Flat Scalar List

```python
params = [p for mat in state_dict.values() for row in mat for p in row]  # 8,880 Values
m = [0.0] * len(params)
v = [0.0] * len(params)

for i, p in enumerate(params):
    m[i] = beta1 * m[i] + (1 - beta1) * p.grad
    v[i] = beta2 * v[i] + (1 - beta2) * p.grad ** 2
    m_hat = m[i] / (1 - beta1 ** (step + 1))
    v_hat = v[i] / (1 - beta2 ** (step + 1))
    p.data -= lr_t * m_hat / (v_hat ** 0.5 + eps_adam)
    p.grad = 0
```

8,880 iterations of a Python loop, each doing ~10 float operations.

### PyTorch: Tensor-Level Updates

```python
adam_m = {name: torch.zeros_like(p) for name, p in state_dict.items()}
adam_v = {name: torch.zeros_like(p) for name, p in state_dict.items()}

with torch.no_grad():
    for name, p in state_dict.items():
        g = p.grad
        adam_m[name] = beta1 * adam_m[name] + (1 - beta1) * g
        adam_v[name] = beta2 * adam_v[name] + (1 - beta2) * g * g
        m_hat = adam_m[name] / (1 - beta1 ** (step + 1))
        v_hat = adam_v[name] / (1 - beta2 ** (step + 1))
        p -= lr_t * m_hat / (v_hat.sqrt() + eps_adam)
        p.grad.zero_()
```

~10 tensor-level iterations (one per named parameter matrix), each updating entire tensors in a single vectorized operation on the GPU.

---

## 7. KV Cache

### Pure Python

```python
keys[li].append(k)     # k is a Python list of Value objects
values[li].append(val)  # same

k_h = [ki[hs:hs+head_dim] for ki in keys[li]]  # list slicing per head
```

### PyTorch

```python
keys[li].append(k)                    # k is a 1D tensor [n_embd]
values[li].append(v)

k_stack = torch.stack(keys[li])       # [seq_len, n_embd] — new tensor
k_heads = k_stack.view(seq_len, n_head, head_dim)  # zero-copy reshape
```

---

## 8. What's Identical

Despite the implementation differences, these are exactly the same:

- **Model architecture**: GPT-2 style — token + position embeddings, multi-head self-attention, RMSNorm, squared ReLU MLP, residual connections, weight tying
- **Hyperparameter defaults**: `n_embd=24`, `n_layer=1`, `n_head=4`, `block_size=24`, `lr=0.01`
- **Adam configuration**: `beta1=0.9`, `beta2=0.95`, `eps=1e-8`, linear LR decay
- **Dataset loading**: Same `input.txt` format, same character-level tokenizer, same BOS/EOS tokens
- **Save format**: Identical JSON structure (`hyperparams`, `vocab`, `state_dict`) — models from either trainer work with `inference.py`
- **Best-model checkpointing**: Rolling avg over last 50 steps, snapshot every 10 steps
- **CLI arguments**: Same flags (MPS adds `--device`)

---

## Why MPS Achieves Lower Loss

The 37x speedup is expected (vectorized GPU ops vs scalar Python loops). The **lower loss** (2.64 vs 3.11) is more surprising and comes from two sources:

1. **Numerical precision**: PyTorch's float32 tensor operations accumulate fewer rounding errors than thousands of scalar `Value` multiplications chained through Python.

2. **Single backward pass**: The pure Python version calls `loss.backward()` per position, rebuilding and traversing the topological sort each time. The PyTorch version accumulates the full sequence loss and calls `backward()` once, computing gradients through the complete computation graph in a single pass.

The result is that MPS doesn't just train faster — it trains *better* on the same data with the same architecture.
