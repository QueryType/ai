"""
MicroGPT for Devanagari Names
Based on Karpathy's microgpt (https://gist.github.com/karpathy/8627fe009c40f57531cb18360106ce95)
Modified to train on Devanagari names of great Indian figures and generate new ones.

Usage:
  1. First run: python generate_dataset.py   (creates input.txt with ~32K Devanagari names)
  2. Then run:  python train.py               (trains and generates new names)

Or just run this file directly if input.txt already exists.
"""

import os
import math
import random
import argparse

# CLI arguments — adjusted defaults for Devanagari
parser = argparse.ArgumentParser()
parser.add_argument('--n_embd', type=int, default=24, help='Embedding dimension (wider for larger Devanagari vocab)')
parser.add_argument('--n_layer', type=int, default=1, help='Number of Transformer layers')
parser.add_argument('--block_size', type=int, default=24, help='Max sequence length (Devanagari names can be long)')
parser.add_argument('--num_steps', type=int, default=3000, help='Training steps (more steps for convergence)')
parser.add_argument('--n_head', type=int, default=4, help='Number of attention heads')
parser.add_argument('--learning_rate', type=float, default=1e-2, help='Learning rate')
parser.add_argument('--seed', type=int, default=42, help='Random seed')
parser.add_argument('--num_samples', type=int, default=20, help='Number of names to generate')
parser.add_argument('--temperature', type=float, default=0.6, help='Sampling temperature (0.3=conservative, 1.0=creative)')
parser.add_argument('--save_path', type=str, default='', help='Save trained weights to this file (e.g. model.json)')
args = parser.parse_args()
random.seed(args.seed)
n_embd, block_size, n_layer, n_head = args.n_embd, args.block_size, args.n_layer, args.n_head
head_dim = n_embd // n_head

# ============================================================
# Dataset: Devanagari names (one per line)
# ============================================================
if not os.path.exists('input.txt'):
    print("ERROR: input.txt not found!")
    print("Please run 'python generate_dataset.py' first to create the dataset.")
    exit(1)

with open('input.txt', 'r', encoding='utf-8') as file:
    text = file.read()
docs = [line.strip() for line in text.strip().split('\n') if line.strip()]
random.shuffle(docs)

# ============================================================
# Tokenizer: character-level over Devanagari Unicode
# ============================================================
chars = ['<BOS>', '<EOS>'] + sorted(list(set(''.join(docs))))
vocab_size = len(chars)
stoi = {ch: i for i, ch in enumerate(chars)}
itos = {i: ch for i, ch in enumerate(chars)}
BOS, EOS = stoi['<BOS>'], stoi['<EOS>']
print(f"vocab size: {vocab_size}, num docs: {len(docs)}")

# ============================================================
# Autograd engine (identical to Karpathy's microgpt)
# ============================================================
class Value:
    """Stores a single scalar value and its gradient"""

    def __init__(self, data, _children=(), _op=''):
        self.data = data
        self.grad = 0
        self._backward = lambda: None
        self._prev = set(_children)
        self._op = _op

    def __add__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        out = Value(self.data + other.data, (self, other), '+')
        def _backward():
            self.grad += out.grad
            other.grad += out.grad
        out._backward = _backward
        return out

    def __mul__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        out = Value(self.data * other.data, (self, other), '*')
        def _backward():
            self.grad += other.data * out.grad
            other.grad += self.data * out.grad
        out._backward = _backward
        return out

    def __pow__(self, other):
        assert isinstance(other, (int, float))
        out = Value(self.data**other, (self,), f'**{other}')
        def _backward():
            self.grad += (other * self.data**(other-1)) * out.grad
        out._backward = _backward
        return out

    def log(self):
        out = Value(math.log(self.data), (self,), 'log')
        def _backward():
            self.grad += (1 / self.data) * out.grad
        out._backward = _backward
        return out

    def exp(self):
        out = Value(math.exp(self.data), (self,), 'exp')
        def _backward():
            self.grad += out.data * out.grad
        out._backward = _backward
        return out

    def relu(self):
        out = Value(0 if self.data < 0 else self.data, (self,), 'ReLU')
        def _backward():
            self.grad += (out.data > 0) * out.grad
        out._backward = _backward
        return out

    def backward(self):
        topo = []
        visited = set()
        def build_topo(v):
            if v not in visited:
                visited.add(v)
                for child in v._prev:
                    build_topo(child)
                topo.append(v)
        build_topo(self)
        self.grad = 1
        for v in reversed(topo):
            v._backward()

    def __neg__(self): return self * -1
    def __radd__(self, other): return self + other
    def __sub__(self, other): return self + (-other)
    def __rsub__(self, other): return other + (-self)
    def __rmul__(self, other): return self * other
    def __truediv__(self, other): return self * other**-1
    def __rtruediv__(self, other): return other * self**-1
    def __repr__(self): return f"Value(data={self.data}, grad={self.grad})"

# ============================================================
# Model parameter initialization
# ============================================================
matrix = lambda nout, nin, std=0.02: [[Value(random.gauss(0, std)) for _ in range(nin)] for _ in range(nout)]
state_dict = {'wte': matrix(vocab_size, n_embd), 'wpe': matrix(block_size, n_embd)}
for i in range(n_layer):
    state_dict[f'layer{i}.attn_wq'] = matrix(n_embd, n_embd)
    state_dict[f'layer{i}.attn_wk'] = matrix(n_embd, n_embd)
    state_dict[f'layer{i}.attn_wv'] = matrix(n_embd, n_embd)
    state_dict[f'layer{i}.attn_wo'] = matrix(n_embd, n_embd, std=0)
    state_dict[f'layer{i}.mlp_fc1'] = matrix(4 * n_embd, n_embd)
    state_dict[f'layer{i}.mlp_fc2'] = matrix(n_embd, 4 * n_embd, std=0)
params = [p for mat in state_dict.values() for row in mat for p in row]
print(f"num params: {len(params)}")

# ============================================================
# Model architecture (GPT-2 style, identical to microgpt)
# ============================================================
def linear(x, w):
    return [sum(w[o][i] * x[i] for i in range(len(x))) for o in range(len(w))]

def softmax(logits):
    max_val = max(v.data for v in logits)
    exps = [(v - max_val).exp() for v in logits]
    total = sum(exps)
    return [e / total for e in exps]

def rmsnorm(x):
    ms = sum(xi * xi for xi in x) / len(x)
    scale = (ms + 1e-5) ** -0.5
    return [xi * scale for xi in x]

def gpt(token_id, pos_id, keys, values):
    tok_emb = state_dict['wte'][token_id]
    pos_emb = state_dict['wpe'][pos_id % block_size]
    x = [t + p for t, p in zip(tok_emb, pos_emb)]

    for li in range(n_layer):
        # Multi-head attention
        x_residual = x
        x = rmsnorm(x)
        q = linear(x, state_dict[f'layer{li}.attn_wq'])
        k = linear(x, state_dict[f'layer{li}.attn_wk'])
        val = linear(x, state_dict[f'layer{li}.attn_wv'])
        keys[li].append(k)
        values[li].append(val)
        x_attn = []
        for h in range(n_head):
            hs = h * head_dim
            q_h = q[hs:hs+head_dim]
            k_h = [ki[hs:hs+head_dim] for ki in keys[li]]
            v_h = [vi[hs:hs+head_dim] for vi in values[li]]
            attn_logits = [sum(q_h[j] * k_h[t][j] for j in range(head_dim)) / head_dim**0.5 for t in range(len(k_h))]
            attn_weights = softmax(attn_logits)
            head_out = [sum(attn_weights[t] * v_h[t][j] for t in range(len(v_h))) for j in range(head_dim)]
            x_attn.extend(head_out)
        x = linear(x_attn, state_dict[f'layer{li}.attn_wo'])
        x = [a + b for a, b in zip(x, x_residual)]
        # MLP
        x_residual = x
        x = rmsnorm(x)
        x = linear(x, state_dict[f'layer{li}.mlp_fc1'])
        x = [xi.relu() ** 2 for xi in x]
        x = linear(x, state_dict[f'layer{li}.mlp_fc2'])
        x = [a + b for a, b in zip(x, x_residual)]

    # Weight tying with wte
    logits = linear(x, state_dict['wte'])
    return logits

# ============================================================
# Adam optimizer
# ============================================================
learning_rate = args.learning_rate
beta1, beta2, eps_adam = 0.9, 0.95, 1e-8
m = [0.0] * len(params)
v = [0.0] * len(params)

# ============================================================
# Training loop
# ============================================================
print(f"\n--- training ({args.num_steps} steps) ---")
best_avg_loss = float('inf')
best_state = None
recent_losses = []
avg_window = 50  # running average over last 50 steps

def snapshot_params():
    """Snapshot current parameter values (plain floats, no autograd)."""
    return {
        name: [[p.data for p in row] for row in mat]
        for name, mat in state_dict.items()
    }

for step in range(args.num_steps):

    doc = docs[step % len(docs)]
    tokens = [BOS] + [stoi[ch] for ch in doc] + [EOS]
    tokens = tokens[:block_size]

    keys, values = [[] for _ in range(n_layer)], [[] for _ in range(n_layer)]
    lossf = 0.0
    for pos_id in range(len(tokens) - 1):
        logits = gpt(tokens[pos_id], pos_id, keys, values)
        probs = softmax(logits)
        loss = -probs[tokens[pos_id + 1]].log()
        loss = (1 / (len(tokens) - 1)) * loss
        loss.backward()
        lossf += loss.data

    lr_t = learning_rate * (1 - step / args.num_steps)
    for i, p in enumerate(params):
        m[i] = beta1 * m[i] + (1 - beta1) * p.grad
        v[i] = beta2 * v[i] + (1 - beta2) * p.grad ** 2
        m_hat = m[i] / (1 - beta1 ** (step + 1))
        v_hat = v[i] / (1 - beta2 ** (step + 1))
        p.data -= lr_t * m_hat / (v_hat ** 0.5 + eps_adam)
        p.grad = 0

    if (step + 1) % 100 == 0 or step == 0:
        recent_losses.append(lossf)
        avg_loss = sum(recent_losses[-avg_window:]) / len(recent_losses[-avg_window:])
        best_marker = ""
        if avg_loss < best_avg_loss:
            best_avg_loss = avg_loss
            best_state = snapshot_params()
            best_marker = " *best*"
        print(f"step {step+1:5d} / {args.num_steps} | loss {lossf:.4f} | avg(last {min(avg_window, len(recent_losses))}) {avg_loss:.4f}{best_marker}")
    else:
        recent_losses.append(lossf)
    
    # Check for best model every 10 steps
    if len(recent_losses) >= avg_window and (step + 1) % 10 == 0:
        avg_loss = sum(recent_losses[-avg_window:]) / avg_window
        if avg_loss < best_avg_loss:
            best_avg_loss = avg_loss
            best_state = snapshot_params()

# ============================================================
# Save weights (if --save_path specified)
# ============================================================
if args.save_path:
    import json

    def save_model(param_dict, path):
        save_data = {
            'hyperparams': {
                'n_embd': n_embd, 'n_layer': n_layer, 'n_head': n_head,
                'block_size': block_size, 'head_dim': head_dim,
            },
            'vocab': {'chars': chars, 'vocab_size': vocab_size},
            'state_dict': param_dict,
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False)

    # Save final model
    final_state = snapshot_params()
    save_model(final_state, args.save_path)
    print(f"\nFinal model saved to {args.save_path}")

    # Save best model
    if best_state is not None:
        base, ext = os.path.splitext(args.save_path)
        best_path = f"{base}_best{ext}"
        save_model(best_state, best_path)
        print(f"Best model (avg loss {best_avg_loss:.4f}) saved to {best_path}")

# ============================================================
# Inference: generate new Devanagari names
# ============================================================
print(f"\n--- generated names (temperature={args.temperature}) ---")
for sample_idx in range(args.num_samples):
    keys, values = [[] for _ in range(n_layer)], [[] for _ in range(n_layer)]
    token_id = BOS
    generated = []
    for pos_id in range(block_size):
        logits = gpt(token_id, pos_id, keys, values)
        probs = softmax([l / args.temperature for l in logits])
        token_id = random.choices(range(vocab_size), weights=[p.data for p in probs])[0]
        if token_id == EOS or token_id == BOS:
            break
        generated.append(itos[token_id])
    print(f"  {sample_idx+1:2d}. {''.join(generated)}")

print("\nDone! These are hallucinated Devanagari names that don't (necessarily) exist.")
print("Try different temperatures: --temperature 0.3 (conservative) to 1.0 (creative)")
print("Try more training: --num_steps 5000 for better results")
