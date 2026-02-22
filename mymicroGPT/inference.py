"""
Inference-only script for Devanagari MicroGPT.
Loads a model saved by train.py and generates new names.

Usage:
  python train.py --save_path model.json          # train and save
  python inference.py --model model.json           # generate names
  python inference.py --model model.json --temperature 0.3 --num_samples 50
"""

import json
import math
import random
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--model', type=str, required=True, help='Path to saved model JSON')
parser.add_argument('--num_samples', type=int, default=20, help='Number of names to generate')
parser.add_argument('--temperature', type=float, default=0.6, help='Sampling temperature')
parser.add_argument('--seed', type=int, default=None, help='Random seed (omit for different names each run)')
args = parser.parse_args()

if args.seed is not None:
    random.seed(args.seed)

# ============================================================
# Load model
# ============================================================
print(f"Loading model from {args.model}...")
with open(args.model, 'r', encoding='utf-8') as f:
    save_data = json.load(f)

hp = save_data['hyperparams']
n_embd = hp['n_embd']
n_layer = hp['n_layer']
n_head = hp['n_head']
block_size = hp['block_size']
head_dim = hp['head_dim']

chars = save_data['vocab']['chars']
vocab_size = save_data['vocab']['vocab_size']
stoi = {ch: i for i, ch in enumerate(chars)}
itos = {i: ch for i, ch in enumerate(chars)}
BOS, EOS = stoi['<BOS>'], stoi['<EOS>']

# Reconstruct state_dict as plain floats (no autograd needed for inference)
state_dict = {
    name: [list(row) for row in mat]
    for name, mat in save_data['state_dict'].items()
}

print(f"Loaded: vocab_size={vocab_size}, n_embd={n_embd}, n_layer={n_layer}, n_head={n_head}")

# ============================================================
# Model architecture (inference only — plain floats, no Value)
# ============================================================
def linear(x, w):
    return [sum(w[o][i] * x[i] for i in range(len(x))) for o in range(len(w))]

def softmax(logits):
    max_val = max(logits)
    exps = [math.exp(v - max_val) for v in logits]
    total = sum(exps)
    return [e / total for e in exps]

def rmsnorm(x):
    ms = sum(xi * xi for xi in x) / len(x)
    scale = (ms + 1e-5) ** -0.5
    return [xi * scale for xi in x]

def gpt(token_id, pos_id, keys, values):
    tok_emb = list(state_dict['wte'][token_id])
    pos_emb = list(state_dict['wpe'][pos_id % block_size])
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
        x = [max(0, xi) ** 2 for xi in x]  # squared ReLU, same as training
        x = linear(x, state_dict[f'layer{li}.mlp_fc2'])
        x = [a + b for a, b in zip(x, x_residual)]

    logits = linear(x, state_dict['wte'])
    return logits

# ============================================================
# Generate names
# ============================================================
print(f"\n--- generated names (temperature={args.temperature}) ---")
for sample_idx in range(args.num_samples):
    keys, values = [[] for _ in range(n_layer)], [[] for _ in range(n_layer)]
    token_id = BOS
    generated = []
    for pos_id in range(block_size):
        logits = gpt(token_id, pos_id, keys, values)
        scaled = [l / args.temperature for l in logits]
        probs = softmax(scaled)
        token_id = random.choices(range(vocab_size), weights=probs)[0]
        if token_id == EOS or token_id == BOS:
            break
        generated.append(itos[token_id])
    print(f"  {sample_idx+1:2d}. {''.join(generated)}")

print(f"\nGenerated {args.num_samples} names.")
print("Try: --temperature 0.3 (safe) | 0.6 (balanced) | 0.9 (creative)")
print("Try: --seed 123 (reproducible) | omit seed (different each run)")
