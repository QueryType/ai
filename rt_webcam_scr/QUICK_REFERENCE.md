# Quick Reference Card# Quick Reference Card



## 🚀 Getting Started (3 Steps)## For Mac Users with llama.cpp



### 1️⃣ Start Your Vision Model Server### 1️⃣ Build llama.cpp (one time)

Any OpenAI-compatible API works:```bash

```bashgit clone https://github.com/ggerganov/llama.cpp

# llama.cppcd llama.cpp

./llama-server -m your-vision-model.gguf --port 8080make

```

# Ollama

ollama run llava### 2️⃣ Download a Model (examples)



# Or use OpenAI API directly**Qwen2-VL-2B** (Best balance):

``````bash

huggingface-cli download Qwen/Qwen2-VL-2B-Instruct-GGUF \

### 2️⃣ Open index.html  qwen2-vl-2b-instruct-q4_k_m.gguf --local-dir ./models

Double-click `index.html` or open in your browser.```



### 3️⃣ Configure & Start**SmolVLM-500M** (Fastest):

- API URL: `http://localhost:8080/v1````bash

- Model: Your model namehuggingface-cli download ggml-org/SmolVLM-500M-Instruct-GGUF \

- Click **▶️ Start**  SmolVLM-500M-Instruct-Q4_K_M.gguf --local-dir ./models

```

---

### 3️⃣ Start Server

## ⚡ Interface Controls

**Apple Silicon (M1/M2/M3):**

### Basic Settings```bash

| Setting | Purpose | Default |./llama-server -m ./models/qwen2-vl-2b-instruct-q4_k_m.gguf \

|---------|---------|---------|  -ngl 99 --host 0.0.0.0 --port 8080 -c 4096

| **Input Source** | Webcam or Screen | Webcam |```

| **API Base URL** | Your server endpoint | localhost:8080/v1 |

| **Model Name** | Model identifier | qwen2-vl-2b |**Intel Mac:**

| **Instruction** | What to analyze | Brief description |```bash

| **Interval** | Time between frames | 2000ms (2s) |./llama-server -m ./models/qwen2-vl-2b-instruct-q4_k_m.gguf \

  -t 8 --host 0.0.0.0 --port 8080 -c 4096

### Preset Buttons```

- **Basic Description** - General scene description

- **Detect Changes** - Focus on movements**Or use the interactive script:**

- **Activity Monitor** - Human activity tracking```bash

- **Object Detection** - List visible objects./start_llama_server.sh

```

---

### 4️⃣ Test Server

## 📝 Logging System```bash

curl http://localhost:8080/v1/models

### Quick Setup```

```

☑ Enable Logging### 5️⃣ Open Web Interface

Format: JSON/CSV/TXT```bash

Max logs: 50 (default)# Option A: Direct (modern browsers)

☑ Auto-download when fullopen index.html

```

# Option B: With HTTP server

### Stream Mode (Long Sessions)python3 -m http.server 8000

```# Then open: http://localhost:8000

☑ Stream mode```

↪ Each frame saves immediately

↪ Zero RAM buildup## Web Interface Settings

↪ Perfect for overnight

``````

API Base URL:  http://localhost:8080/v1

### ActionsModel Name:    qwen2-vl-2b

- **💾 Download Logs** - Export all logsInstruction:   Describe what you see in this image.

- **🖼️ Download Images** - Get captured framesInterval:      500ms

- **🗑️ Clear Logs** - Reset (with confirmation)```



---## Common Issues & Fixes



## 🎯 Recommended Settings### Port already in use?

```bash

### Fast Testing (2-5s per frame)# Find what's using it

```lsof -i :8080

Interval: 2000ms

Max logs: 50# Or use different port

Images: OFF./llama-server -m model.gguf --port 8081

Stream: OFF```

```

### Slow on Apple Silicon?

### Long Session (30min - 4hrs)```bash

```# Make sure you're using Metal GPU

Interval: 5000ms./llama-server -m model.gguf -ngl 99

Max logs: 25```

Images: OFF

☑ Auto-download### Server won't start?

``````bash

# Check model file

### Overnight Monitoring (>4hrs)ls -lh path/to/model.gguf

```

Interval: 10000ms# Check llama.cpp version

☑ Stream modecd llama.cpp && git pull && make clean && make

Images: Optional```

```

### Camera not working?

---- Use Chrome or Firefox

- Allow camera permissions

## 🔍 Monitoring Performance- Use localhost or HTTPS



### Status Bar Shows:## Performance Tuning

- **Latency** - Time per inference

- **Avg** - Average response time| Parameter | Description | Recommended |

- **Processed** - Successful frames|-----------|-------------|-------------|

- **Skipped** - Frames dropped (if slow)| `-ngl 99` | GPU layers (Apple Silicon) | Always use |

- **📝 Logging** - When logging is active| `-t 8` | CPU threads (Intel) | CPU cores - 1 |

| `-c 4096` | Context size | 2048-4096 |

### Warning Signs| `--port` | Server port | 8080 |

- **Skipped > 30%** → Increase interval

- **⚠️ Inference too slow** → Use faster model or higher interval## Model Recommendations

- **Memory warning** → Enable auto-download or stream mode

| Use Case | Model | File Size | Speed |

---|----------|-------|-----------|-------|

| Testing | SmolVLM-500M | ~300MB | Very Fast |

## 🐛 Quick Troubleshooting| Daily use | Qwen2-VL-2B | ~1.5GB | Fast |

| Best quality | Qwen2-VL-7B | ~4GB | Medium |

| Problem | Solution |

|---------|----------|## Useful Commands

| Error on start | Check server is running |

| Frames skipped | Increase interval |**Stop server:** `Ctrl+C`

| Memory growing | Enable stream mode |

| Camera denied | Check browser permissions |**Check memory:**

| Slow responses | Reduce max_tokens or use faster model |```bash

vm_stat

---```



## 💡 Pro Tips**Monitor GPU (Apple Silicon):**

```bash

1. **Use brief prompts** → Faster responsessudo powermetrics --samplers gpu_power

2. **Watch skip rate** → Tune interval accordingly```

3. **Stream mode for long sessions** → No RAM issues

4. **Disable images** → Save memory**Test API:**

5. **CSV format** → Easy to analyze in Excel```bash

curl http://localhost:8080/v1/chat/completions \

---  -H "Content-Type: application/json" \

  -d '{

## 🎨 Common Use Cases    "messages": [{"role":"user","content":"Hello"}],

    "max_tokens": 50

### Webcam  }'

- Security monitoring```

- Activity recognition

- Object tracking## Files Included

- Accessibility assistance

- `index.html` - Web interface

### Screen Capture- `README.md` - Full documentation

- Code review- `MAC_SETUP.md` - Detailed Mac setup guide

- Document analysis- `start_llama_server.sh` - Interactive startup script

- Design feedback- `QUICK_REFERENCE.md` - This file

- Tutorial assistance

- Error debugging## Getting Help



---1. Check `MAC_SETUP.md` for detailed troubleshooting

2. Look at llama.cpp logs for error messages

## 📊 Export Formats3. Visit: https://github.com/ggerganov/llama.cpp

4. Check model documentation on HuggingFace

### JSON

```json## Next Steps

{

  "timestamp": "2025-11-01T14:30:45.123Z",After you get it running:

  "sourceType": "Webcam",- Try different prompts/instructions

  "response": "A person sitting at a desk...",- Adjust interval for your needs

  "latencyMs": 2340- Test different models

}- Experiment with context size

```

Happy vision modeling! 🎥✨

### CSV
```csv
Frame,Timestamp,Source Type,Latency (s),Instruction,Response
1,11/1/2025 2:30 PM,Webcam,2.34,"Describe scene","A person..."
```

### TXT
```
═══════════════════════════════════
Frame #1
═══════════════════════════════════
Timestamp:    11/1/2025, 2:30:45 PM
Source:       Webcam
Latency:      2.34s
Response:     A person sitting at a desk...
```

---

## 🔗 Resources

- **README.md** - Full documentation
- **EXAMPLE_PROMPTS.md** - Prompt templates
- **SCREEN_CAPTURE_GUIDE.md** - Screen capture use cases
