# From MicroGPT to देवनागरी MicroGPT
### A short report on adapting Karpathy's microgpt for Devanagari name generation

---

## What We Started With

On February 12, 2026, Andrej Karpathy published **microgpt** — a 200-line pure Python script that trains and runs a GPT language model with zero dependencies. It is a remarkable distillation: autograd engine, transformer architecture, Adam optimizer, training loop, and inference — all in one file. The model trains on ~32K English names (one per line) and generates new plausible-sounding English names.

Our goal was to adapt this for **Devanagari script**: train on names of great Indians — historical figures, mythological characters, Sanskrit names, place names — and generate new ones that sound plausibly Sanskrit/Hindi.

---

## What We Changed (and Why)

### 1. Dataset: From English Names to Devanagari Names

**Karpathy's original**: Downloads `names.txt` — 32K English names like "emma", "olivia", "sophia".

**Our version**: `generate_dataset.py` constructs a ~32K Devanagari dataset from five sources:

| Category | Count | Examples |
|----------|-------|---------|
| Historical figures | ~300 | चन्द्रगुप्त, शिवाजी, भगतसिंह |
| Mythological names | ~500 | कृष्ण, हनुमान, युधिष्ठिर |
| Sanskrit/Hindi names | ~800 | अभिषेक, प्रकाश, आनन्द |
| Indian places | ~500 | वाराणसी, पाटलिपुत्र, कुरुक्षेत्र |
| Augmented combinations | ~30K | prefix+suffix combos like सुदेव, महाराज |

The core names are oversampled (repeated 5x) so the model sees authentic patterns frequently, while the augmented combos provide volume and variety. The augmentation uses 50 Sanskrit prefixes (सु-, प्र-, महा-, चन्द्र-, ...) and 40 suffixes (-देव, -नाथ, -सिंह, -गुप्त, ...) combined with fragments from real names.

**Why this matters**: With only ~2,100 real names, the model would memorize rather than generalize. The augmentation teaches it the *compositional* structure of Sanskrit names — that a valid name can be a prefix + root + suffix — while the oversampled real names anchor it in authentic patterns.

### 2. Vocabulary: 27 → 58 Tokens

Karpathy's tokenizer discovers 26 lowercase English letters + 1 BOS token = **27 tokens**.

Our tokenizer discovers Devanagari characters automatically — vowels, consonants, matras, virama, anusvara, visarga, nukta — totaling **58 tokens**. This is a 2x larger vocabulary, which has cascading effects:

- The embedding table (`wte`) is 58×24 instead of 27×16
- The output projection is also 58-wide
- The model needs to learn more complex patterns: consonant + matra combinations (क + ा = का), conjuncts via virama (क + ् + ष = क्ष), anusvara placement (ं), etc.

### 3. Hyperparameters: Tuned for Devanagari

| Parameter | Karpathy | Ours | Rationale |
|-----------|----------|------|-----------|
| `n_embd` | 16 | 24 | Wider embeddings for 2x larger vocab |
| `block_size` | 8 | 24 | Devanagari names are longer (चन्द्रशेखर = 10 chars) |
| `num_steps` | 1000 | 3000 | More steps needed to converge with richer character space |
| `n_head` | 4 | 4 | Unchanged |
| `n_layer` | 1 | 1 | Unchanged |
| Total params | ~4,192 | ~8,880 | Scales with vocab × embedding |

### 4. BOS/EOS Bug Fix

Karpathy's original uses a single `BOS` token as both beginning and end delimiter. The gist version uses separate `<BOS>` and `<EOS>` tokens, but the inference loop only checked for `EOS` — if `BOS` was sampled instead, it appeared as literal text in the output (`<BOS>चचिलललञ`).

**Fix**: The generation loop now breaks on *both* `BOS` and `EOS`:

```python
if token_id == EOS or token_id == BOS:
    break
```

### 5. Save/Load: Train Once, Generate Many Times

Karpathy's microgpt is a single script — train and generate in one run. If you want different temperatures or more samples, you retrain from scratch.

**Our addition**: `--save_path model.json` serializes the full model state (hyperparameters, vocabulary, all parameter values) to a JSON file after training. A separate `inference.py` loads this file and generates names using plain floats (no `Value` objects, no autograd) — making inference near-instant.

```bash
python train.py --num_steps 5000 --save_path model.json    # train once (~30 min)
python inference.py --model model.json --temperature 0.3    # generate instantly
python inference.py --model model.json --temperature 0.9    # try creative mode
python inference.py --model model.json --num_samples 100    # bulk generate
```

The JSON format was chosen deliberately: human-readable, zero dependencies (no pickle, no numpy), and portable across platforms.

### 6. Best-Model Checkpointing

Since training processes one random name per step, the per-step loss is noisy — a short name like "राम" will have lower loss than "विश्वेश्वरैया" regardless of model quality. Saving only the final weights means you might miss the model's best point.

**Our addition**: A rolling average over the last 50 steps smooths out this noise. Every 10 steps, if the running average is a new low, we snapshot all parameters to memory (~70 KB). At the end of training, both the final and best models are saved:

```
model.json       ← final weights (step 5000)
model_best.json  ← best weights (lowest avg loss, e.g., step 4300)
```

The training log shows `*best*` markers so you can see when checkpoints happen:

```
step  4300 / 5000 | loss 2.83 | avg(last 50) 2.84 *best*
```

---

## What We Didn't Change

The core of microgpt is preserved exactly:

- **Autograd engine** (`Value` class): Identical scalar-level backpropagation
- **GPT-2 architecture**: Same token embeddings + position embeddings → multi-head attention → MLP → logits, with RMSNorm and residual connections
- **Adam optimizer**: Same update rule with bias correction and linear LR decay
- **Training loop**: Same one-document-at-a-time forward → loss → backward → update cycle
- **Character-level tokenization**: Same approach of discovering unique characters in the dataset

The architectural simplicity that makes microgpt beautiful is fully preserved. Our changes are purely practical additions layered on top.

---

## Summary of Additions

| Feature | Karpathy's microgpt | Our version |
|---------|-------------------|-------------|
| Script | Single `train.py` | `generate_dataset.py` + `train.py` + `inference.py` |
| Dataset | English names (downloaded) | Devanagari names (generated from 5 categories) |
| Vocab | 27 tokens (a-z + BOS) | 58 tokens (Devanagari Unicode) |
| Save/Load | None | JSON serialization of full model state |
| Best checkpoint | None | Rolling-average tracking with in-memory snapshots |
| Inference | Coupled to training | Separate script, plain floats, no autograd |
| BOS in output | Possible bug | Fixed (breaks on both BOS and EOS) |

---

## What's Next

The pure Python approach tops out at ~5,000 steps before patience runs thin (~30 min on a MacBook Air). For better results, the natural next step is a **PyTorch + MPS** version that would train 50-100x faster on Apple Silicon GPU, enabling 50K+ steps in under a minute. The architecture would be identical — just replacing scalar `Value` operations with vectorized `torch.Tensor` operations.
