"""
PyTorch + MPS version of MicroGPT for Devanagari Names.

This script provides GPU-accelerated training on Apple Silicon using MPS (Metal Performance Shaders).
It produces model.json files in the exact same format as train.py,
ensuring full compatibility with the original inference.py.

Usage:
  1. Generate dataset first: python generate_dataset.py
  2. Train with MPS:  python train_mps.py --num_steps 5000
  3. Run inference:   python inference.py --model model_mps.json
"""

import os
import math
import random
import argparse
import torch
import torch.nn.functional as F

# ============================================================
# CLI arguments (same as train.py, plus --device)
# ============================================================
parser = argparse.ArgumentParser()
parser.add_argument('--n_embd', type=int, default=24, help='Embedding dimension')
parser.add_argument('--n_layer', type=int, default=1, help='Number of Transformer layers')
parser.add_argument('--block_size', type=int, default=24, help='Max sequence length')
parser.add_argument('--num_steps', type=int, default=3000, help='Training steps')
parser.add_argument('--n_head', type=int, default=4, help='Number of attention heads')
parser.add_argument('--learning_rate', type=float, default=1e-2, help='Learning rate')
parser.add_argument('--seed', type=int, default=42, help='Random seed')
parser.add_argument('--num_samples', type=int, default=20, help='Number of names to generate')
parser.add_argument('--temperature', type=float, default=0.6, help='Sampling temperature')
parser.add_argument('--save_path', type=str, default='', help='Save trained weights to this file')
parser.add_argument('--device', type=str, default='auto', help='Device: auto, mps, or cpu')
args = parser.parse_args()

# Set device
if args.device == 'auto':
    if torch.backends.mps.is_available():
        device = torch.device('mps')
        print("Using MPS (Apple Silicon GPU)")
    else:
        device = torch.device('cpu')
        print("MPS not available, using CPU")
else:
    device = torch.device(args.device)
print(f"Device: {device}")

random.seed(args.seed)
torch.manual_seed(args.seed)

n_embd, block_size, n_layer, n_head = args.n_embd, args.block_size, args.n_layer, args.n_head
head_dim = n_embd // n_head

# ============================================================
# Dataset: Devanagari names (one per line) - same as train.py
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
# Tokenizer: character-level over Devanagari Unicode - identical to train.py
# ============================================================
chars = ['<BOS>', '<EOS>'] + sorted(list(set(''.join(docs))))
vocab_size = len(chars)
stoi = {ch: i for i, ch in enumerate(chars)}
itos = {i: ch for i, ch in enumerate(chars)}
BOS, EOS = stoi['<BOS>'], stoi['<EOS>']
print(f"vocab size: {vocab_size}, num docs: {len(docs)}")

# ============================================================
# State dict: identical structure to train.py
# All tensors have requires_grad=True for autograd
# ============================================================
def init_matrix(nout, nin, std=0.02):
    return (torch.randn(nout, nin) * std).to(device).requires_grad_(True)

def zero_matrix(nout, nin):
    return torch.zeros(nout, nin, device=device).requires_grad_(True)

state_dict = {
    'wte': init_matrix(vocab_size, n_embd),
    'wpe': init_matrix(block_size, n_embd),
}

for i in range(n_layer):
    state_dict[f'layer{i}.attn_wq'] = init_matrix(n_embd, n_embd)
    state_dict[f'layer{i}.attn_wk'] = init_matrix(n_embd, n_embd)
    state_dict[f'layer{i}.attn_wv'] = init_matrix(n_embd, n_embd)
    state_dict[f'layer{i}.attn_wo'] = zero_matrix(n_embd, n_embd)
    state_dict[f'layer{i}.mlp_fc1'] = init_matrix(4 * n_embd, n_embd)
    state_dict[f'layer{i}.mlp_fc2'] = zero_matrix(n_embd, 4 * n_embd)

# Collect all parameters for the optimizer
params = list(state_dict.values())
num_params = sum(p.numel() for p in params)
print(f"num params: {num_params}")

# ============================================================
# Model functions
# ============================================================
def rmsnorm(x):
    ms = (x * x).mean(dim=-1, keepdim=True)
    return x * (ms + 1e-5).rsqrt()

def gpt(token_id, pos_id, keys, values):
    """
    Forward pass for single position.
    keys/values: list of n_layer lists, each accumulating K/V tensors.
    """
    tok_emb = state_dict['wte'][token_id]
    pos_emb = state_dict['wpe'][pos_id % block_size]
    x = tok_emb + pos_emb  # [n_embd]

    for li in range(n_layer):
        # --- Multi-head attention ---
        x_residual = x

        x_norm = rmsnorm(x.unsqueeze(0)).squeeze(0)

        q = x_norm @ state_dict[f'layer{li}.attn_wq'].T  # [n_embd]
        k = x_norm @ state_dict[f'layer{li}.attn_wk'].T  # [n_embd]
        v = x_norm @ state_dict[f'layer{li}.attn_wv'].T  # [n_embd]

        keys[li].append(k)
        values[li].append(v)

        # Stack cached keys/values: [seq_len, n_embd]
        k_stack = torch.stack(keys[li])
        v_stack = torch.stack(values[li])

        # Reshape for multi-head: [seq_len, n_head, head_dim]
        seq_len = k_stack.shape[0]
        q_heads = q.view(n_head, head_dim)           # [n_head, head_dim]
        k_heads = k_stack.view(seq_len, n_head, head_dim)  # [seq_len, n_head, head_dim]
        v_heads = v_stack.view(seq_len, n_head, head_dim)  # [seq_len, n_head, head_dim]

        # Attention scores: [n_head, seq_len]
        attn_logits = torch.einsum('hd,shd->hs', q_heads, k_heads) / (head_dim ** 0.5)
        attn_weights = F.softmax(attn_logits, dim=-1)  # [n_head, seq_len]

        # Weighted sum of values: [n_head, head_dim]
        head_out = torch.einsum('hs,shd->hd', attn_weights, v_heads)

        # Concatenate heads: [n_embd]
        x_attn = head_out.reshape(n_embd)

        # Output projection + residual
        x = x_residual + x_attn @ state_dict[f'layer{li}.attn_wo'].T

        # --- MLP ---
        x_residual = x

        x_norm = rmsnorm(x.unsqueeze(0)).squeeze(0)

        x_mlp = x_norm @ state_dict[f'layer{li}.mlp_fc1'].T  # [4*n_embd]
        x_mlp = F.relu(x_mlp) ** 2  # squared ReLU
        x_mlp = x_mlp @ state_dict[f'layer{li}.mlp_fc2'].T   # [n_embd]

        x = x_residual + x_mlp

    # Output logits with weight tying
    logits = x @ state_dict['wte'].T  # [vocab_size]
    return logits

# ============================================================
# Adam optimizer state (vectorized, operates on full tensors)
# ============================================================
learning_rate = args.learning_rate
beta1, beta2, eps_adam = 0.9, 0.95, 1e-8

adam_m = {name: torch.zeros_like(p) for name, p in state_dict.items()}
adam_v = {name: torch.zeros_like(p) for name, p in state_dict.items()}

# ============================================================
# Training loop
# ============================================================
print(f"\n--- training ({args.num_steps} steps) ---")
best_avg_loss = float('inf')
best_state = None
recent_losses = []
avg_window = 50

def snapshot_params():
    """Snapshot current parameter values as nested Python lists (same format as train.py)."""
    return {name: p.cpu().detach().tolist() for name, p in state_dict.items()}

for step in range(args.num_steps):

    doc = docs[step % len(docs)]
    tokens = [BOS] + [stoi[ch] for ch in doc] + [EOS]
    tokens = tokens[:block_size]

    # Per-layer KV caches
    keys = [[] for _ in range(n_layer)]
    values = [[] for _ in range(n_layer)]

    total_loss = torch.tensor(0.0, device=device)
    for pos_id in range(len(tokens) - 1):
        token_id = tokens[pos_id]
        next_token = tokens[pos_id + 1]

        logits = gpt(token_id, pos_id, keys, values)

        prob = F.softmax(logits, dim=-1)
        loss = -torch.log(prob[next_token] + 1e-10)
        total_loss = total_loss + loss / (len(tokens) - 1)

    total_loss.backward()
    lossf = total_loss.item()

    # LR decay (same formula as train.py)
    lr_t = learning_rate * (1 - step / args.num_steps)

    # Adam update on each tensor directly (no element-by-element loop)
    with torch.no_grad():
        for name, p in state_dict.items():
            if p.grad is None:
                continue
            g = p.grad
            adam_m[name] = beta1 * adam_m[name] + (1 - beta1) * g
            adam_v[name] = beta2 * adam_v[name] + (1 - beta2) * g * g
            m_hat = adam_m[name] / (1 - beta1 ** (step + 1))
            v_hat = adam_v[name] / (1 - beta2 ** (step + 1))
            p -= lr_t * m_hat / (v_hat.sqrt() + eps_adam)
            p.grad.zero_()

    # Track loss
    recent_losses.append(lossf)
    if (step + 1) % 100 == 0 or step == 0:
        avg_loss = sum(recent_losses[-avg_window:]) / len(recent_losses[-avg_window:])
        best_marker = ""
        if avg_loss < best_avg_loss:
            best_avg_loss = avg_loss
            best_state = snapshot_params()
            best_marker = " *best*"
        print(f"step {step+1:5d} / {args.num_steps} | loss {lossf:.4f} | avg(last {min(avg_window, len(recent_losses))}) {avg_loss:.4f}{best_marker}")

    # Check for best model every 10 steps
    if len(recent_losses) >= avg_window and (step + 1) % 10 == 0:
        avg_loss = sum(recent_losses[-avg_window:]) / avg_window
        if avg_loss < best_avg_loss:
            best_avg_loss = avg_loss
            best_state = snapshot_params()

# ============================================================
# Save weights (identical format to train.py)
# ============================================================
if args.save_path:
    import json

    def save_model(param_dict, path):
        save_data = {
            'hyperparams': {
                'n_embd': n_embd,
                'n_layer': n_layer,
                'n_head': n_head,
                'block_size': block_size,
                'head_dim': head_dim,
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
# Inference: generate new Devanagari names (same logic as train.py)
# ============================================================
print(f"\n--- generated names (temperature={args.temperature}) ---")

with torch.no_grad():
    for sample_idx in range(args.num_samples):
        keys = [[] for _ in range(n_layer)]
        values = [[] for _ in range(n_layer)]

        generated = []
        token_id = BOS

        for pos_id in range(block_size):
            logits = gpt(token_id, pos_id, keys, values)

            next_logits = logits / args.temperature
            probs = F.softmax(next_logits, dim=-1).cpu().numpy()

            token_id = random.choices(range(vocab_size), weights=probs)[0]

            if token_id == EOS or token_id == BOS:
                break

            generated.append(itos[token_id])

        print(f"  {sample_idx+1:2d}. {''.join(generated)}")

print("\nDone! These are hallucinated Devanagari names that don't (necessarily) exist.")
print("Try different temperatures: --temperature 0.3 (conservative) to 1.0 (creative)")
print("Try more training: --num_steps 5000 for better results")
