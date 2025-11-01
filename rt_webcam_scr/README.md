# Real-time Webcam & Screen Capture Vision Analysis

A powerful web-based interface for real-time vision model analysis using webcam or screen capture. Works with any OpenAI-compatible vision API (llama.cpp, Ollama, OpenAI, etc.).

## ✨ Features

### 🎥 Dual Capture Modes
- **Webcam** - Analyze live video feed from your camera
- **Screen Capture** - Monitor your screen, specific windows, or browser tabs

### 🧠 Smart Processing
- **Frame skipping** - Automatically skips frames when inference is slow
- **Performance metrics** - Real-time latency tracking and statistics
- **Auto-adjustment** - Warns when interval needs tuning
- **Brief responses** - Optimized prompts for faster inference

### 📝 Advanced Logging System
- **Multiple formats** - JSON, CSV, or TXT export
- **Memory management** - Auto-save when limits are reached
- **Stream mode** - Zero RAM buildup for long sessions
- **Image capture** - Optional frame saving with logs
- **Memory tracking** - Real-time RAM usage display

### 🎨 Beautiful UI
- **Markdown rendering** - Formatted, readable responses
- **Live indicators** - Processing status and badges
- **Preset prompts** - Quick templates for common tasks
- **Model presets** - One-click model selection

## 🚀 Quick Start

### 1. Start Your Vision Model Server

This client works with any OpenAI-compatible vision API. Examples:

**llama.cpp server:**
```bash
./llama-server -m qwen2-vl-2b-instruct-q4_k_m.gguf --port 8080
```

**Ollama:**
```bash
ollama run llava
# API runs on http://localhost:11434/v1
```

**OpenAI API:**
- Use `https://api.openai.com/v1` as base URL
- Add your API key

### 3. Configure and Start

Configure in the web interface:
- **Input Source**: Choose 📷 Webcam or 🖥️ Screen Capture
- **API Base URL**: Your server URL (e.g., `http://localhost:8080/v1`)
- **Model Name**: Your model name
- **Instruction**: Use preset buttons or write custom prompts
- **Interval**: Start with 2000ms, adjust based on inference speed

Click **▶️ Start** and allow camera/screen access!

## 📊 Logging System

### Basic Logging
1. Check **"Enable Logging"**
2. Choose format: JSON, CSV, or TXT
3. Set memory limit (default: 50 logs)
4. Start capturing
5. Click **"Download Logs"** when done

### Stream Mode (Long Sessions)
- Enable **"Stream mode"**
- Each frame auto-saves immediately
- Zero RAM buildup
- Perfect for overnight monitoring
- Creates timestamped files

### Memory Management
- **Max logs**: Set limit to prevent RAM issues
- **Auto-download**: Saves logs when limit reached
- **Memory display**: Shows current RAM usage
- **Image saving**: Optional (warning: uses more RAM)

## 💡 Usage Examples

### Webcam Analysis
```
Source: 📷 Webcam
Prompt: "Briefly describe what you see"
Interval: 2000ms
Logging: Optional
```

### Screen Monitoring
```
Source: 🖥️ Screen Capture
Prompt: "Briefly note any changes or activities"
Interval: 5000ms
Logging: Stream mode ON (for long sessions)
```

### Code Review
```
Source: �️ Screen (IDE window)
Prompt: "List the main objects, people, and activities visible"
Interval: 10000ms
Format: CSV (for analysis)
```

## ⚙️ Performance Tuning

### Choosing Interval
- **Fast model (<2s)**: 1000-2000ms
- **Medium model (2-5s)**: 2000-3000ms
- **Slow model (5-10s)**: 5000-10000ms
- **Very slow (>10s)**: 15000-30000ms

### Memory Settings
- **Short session (<1hr)**: 50-100 logs, images optional
- **Medium session (1-4hrs)**: 25-50 logs, auto-download ON
- **Long session (>4hrs)**: Stream mode ON, no images

### Optimization Tips
- Use **brief prompts** for faster responses
- Enable **auto-adjust** to get warnings
- Watch **skip rate** - if >30%, increase interval
- **Disable images** if you don't need them
- Use **stream mode** for overnight sessions

## 🔧 Troubleshooting

### "Error" message on start
- **Check server is running** - Test API endpoint
- **Wrong URL** - Verify API base URL is correct
- **CORS issues** - Ensure server allows browser requests
- **Wrong model** - Verify you're using a vision model

### Frames being skipped
- **Increase interval** - Inference is too slow for current setting
- **Check skip rate** - If >30%, interval is too aggressive
- **Use faster model** - Consider smaller/quantized version
- **Reduce max_tokens** - Default is 150, try 100

### Camera/screen not working
- **Browser permissions** - Allow camera/screen access
- **HTTPS required** - Use localhost or secure connection
- **Try different browser** - Chrome and Firefox work best

### Memory issues
- **Disable images** - Uncheck "Save captured images"
- **Lower max logs** - Reduce to 25 or less
- **Enable stream mode** - Auto-saves without RAM buildup
- **Check memory display** - Monitor RAM usage

## 🛠️ Technical Details

**Architecture:**
- Pure HTML/CSS/JavaScript - no build required
- Uses OpenAI-compatible vision API format
- Markdown rendering with marked.js
- Base64 JPEG encoding for frames
- Smart frame skipping when inference is slow

**Request Format:**
```json
{
  "model": "your-model",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "text", "text": "instruction + brief prompt"},
      {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
    ]
  }],
  "max_tokens": 150,
  "temperature": 0.7,
  "seed": "random per frame"
}
```

**Features:**
- Cache-busting headers for fresh responses
- Unique frame IDs and timestamps
- Auto-stabilization delay for video
- Processing state indicators
- Latency tracking and statistics

## 📄 License

MIT License - Free to use and modify

## 🙏 Credits

Based on [ngxson/smolvlm-realtime-webcam](https://github.com/ngxson/smolvlm-realtime-webcam)

Enhanced with:
- Screen capture support
- Advanced logging system
- Memory management
- Performance optimizations
- Markdown rendering
- Stream mode

## License

MIT License - Feel free to modify and use as needed!
