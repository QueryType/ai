# देवनागरी MicroGPT — Devanagari Name Generator

A pure Python, zero-dependency GPT that learns patterns from Indian names written in Devanagari script and generates new, plausible-sounding ones.

Based on [Karpathy's microgpt](https://karpathy.github.io/2026/02/12/microgpt/) — the same autograd + transformer architecture, adapted for Devanagari Unicode with several practical improvements.

## Quick Start

```bash
# Step 1: Generate the dataset (~32K Devanagari names)
python generate_dataset.py

# Step 2: Train, generate, and save the model
python train.py --num_steps 5000 --save_path model.json

# Step 3: Generate more names anytime (no retraining!)
python inference.py --model model_best.json
```

No pip install, no PyTorch, no GPU needed. Runs on a MacBook Air with 8GB RAM.

## Project Files

| File | Purpose |
|------|---------|
| `generate_dataset.py` | Builds `input.txt` — ~32K Devanagari names from 5 categories |
| `train.py` | Trains the GPT, tracks best checkpoint, saves weights to JSON |
| `inference.py` | Loads saved weights and generates names (fast, no autograd) |
| `README.md` | You are here |

## What It Does

The dataset (`generate_dataset.py`) combines five categories of Devanagari text:

- **Historical figures** (~300): चन्द्रगुप्त, शिवाजी, भगतसिंह, रामानुजन, ...
- **Mythological names** (~500): कृष्ण, हनुमान, युधिष्ठिर, वशिष्ठ, ...
- **Sanskrit/Hindi names** (~800): अभिषेक, प्रकाश, विजय, आनन्द, ...
- **Indian places** (~500): वाराणसी, पाटलिपुत्र, हस्तिनापुर, ...
- **Augmented combinations** (~30K): Sanskrit prefix+suffix combos (सुदेव, महाराज, ...)

The core names are oversampled so the model sees them often. The augmented combos fill out the dataset to ~32K (matching Karpathy's original size) and teach the model a wide variety of valid Devanagari character patterns.

The model learns consonant+matra sequences, common prefixes (सु-, प्र-, महा-), typical suffixes (-देव, -नाथ, -सिंह), and generates new names that *sound* plausibly Sanskrit/Hindi.

## Training

```bash
# Quick test run (~2-3 min)
python train.py --num_steps 500 --n_embd 16 --save_path model_quick.json

# Default run (~15-25 min)
python train.py --save_path model.json

# Better quality (~30-40 min)
python train.py --num_steps 5000 --save_path model.json

# High quality (~1-2 hours)
python train.py --num_steps 5000 --n_embd 32 --save_path model_big.json
```

Training saves **two models** when `--save_path` is specified:

- `model.json` — final weights from the last training step
- `model_best.json` — weights from the step with the lowest running-average loss

The best-model checkpoint uses a rolling average over the last 50 steps to smooth out noise (since each step trains on one random name — "राम" is inherently easier than "चन्द्रशेखर"). The snapshot is held in memory (~70 KB) and only written to disk at the end.

You'll see `*best*` markers in the training log:

```
step  4200 / 5000 | loss 2.84 | avg(last 50) 2.87
step  4300 / 5000 | loss 2.83 | avg(last 50) 2.84 *best*
step  4400 / 5000 | loss 2.92 | avg(last 50) 2.88
step  4500 / 5000 | loss 3.33 | avg(last 50) 2.91
...
Final model saved to model.json
Best model (avg loss 2.84) saved to model_best.json
```

## Generation

```bash
# Use the best checkpoint
python inference.py --model model_best.json

# Conservative names (sounds very real)
python inference.py --model model_best.json --temperature 0.3

# Balanced (default)
python inference.py --model model_best.json --temperature 0.6

# Creative names (more novel, some odd ones)
python inference.py --model model_best.json --temperature 0.9

# Generate 50 names, reproducible
python inference.py --model model_best.json --num_samples 50 --seed 123

# Different names each run (omit --seed)
python inference.py --model model_best.json --num_samples 100
```

`inference.py` uses plain floats (no `Value` objects, no autograd) so generation is near-instant.

## Key Parameters

| Parameter | Default | What it does |
|-----------|---------|-------------|
| `--n_embd` | 24 | Embedding dimension. Wider = smarter but slower |
| `--n_layer` | 1 | Transformer layers. 2 is better but ~4x slower |
| `--n_head` | 4 | Attention heads |
| `--block_size` | 24 | Max name length in characters |
| `--num_steps` | 3000 | Training iterations. More = better |
| `--learning_rate` | 0.01 | Adam learning rate (with linear decay) |
| `--save_path` | *(none)* | Save weights to this path (also saves `_best` variant) |
| `--temperature` | 0.6 | Generation creativity (0.1–1.0) |
| `--num_samples` | 20 | How many names to generate |

## Why Devanagari Needs Adjustments

Karpathy's original uses 27 tokens (a-z + BOS). Devanagari has ~58 tokens:

- Vowels: अ आ इ ई उ ऊ ऋ ए ऐ ओ
- Consonants: क ख ग घ ... श ष स ह
- Matras: ा ि ी ु ू ृ े ै ो ौ
- Modifiers: ं ः ् ़

The 2x larger vocabulary means the model needs wider embeddings (24 vs 16), longer block size (24 vs 8, since Devanagari names can be longer), and more training steps to converge.

## Customizing the Dataset

Edit `generate_dataset.py` to change what the model learns:

- Add more names to any category (historical, mythological, etc.)
- Change the prefix/suffix lists to alter generation style
- Adjust the oversampling ratio between real names and generated combos
- Or replace entirely with your own `input.txt` (one name per line, UTF-8)

## Requirements

- **Python 3.6+** (the `python3` that comes with macOS works)
- **RAM**: ~100-200 MB peak during training. An 8GB MacBook Air is more than enough.
- **Disk**: `model.json` is ~1-2 MB
- **No dependencies**: no pip install, no numpy, no PyTorch
