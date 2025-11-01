# 🖥️ Screen Capture Mode - Use Cases & Examples

This guide covers the screen capture feature - perfect for analyzing your Mac screen in real-time!

## What is Screen Capture Mode?

Instead of using your webcam, the app can capture your Mac screen (or specific windows) and analyze what's displayed. This is incredibly useful for:

- **Coding assistance** - Get help with code on your screen
- **Document analysis** - Read and summarize documents you're viewing
- **Presentation feedback** - Get real-time feedback on your slides
- **Accessibility** - Have your screen content described
- **Learning** - Get explanations of content you're studying
- **Productivity** - Analyze workflows and provide suggestions

## How to Use Screen Capture

1. Open `index.html` in your browser
2. **Select "🖥️ Screen Capture"** from the Input Source dropdown
3. Configure your prompt (see examples below)
4. Click **▶️ Start**
5. macOS will show a dialog - choose what to share:
   - **Entire Screen** - Capture everything
   - **Window** - Capture a specific app window
   - **Chrome Tab** - Capture just a browser tab (in Chrome)

**Pro Tip:** Choose "Window" to share only your code editor or the specific app you want analyzed!

## 📝 Example Prompts for Screen Capture

### 1. Code Review & Programming Help

**Debug Assistance:**
```
You are looking at code on my screen. Identify any bugs, errors, or potential issues. 
Explain what's wrong and how to fix it.
```

**Code Explanation:**
```
Explain what this code does in simple terms. Break down the logic step by step.
```

**Code Quality Review:**
```
Review this code for:
- Best practices
- Performance issues
- Security concerns
- Readability improvements
Provide specific suggestions.
```

**Language Detection & Summary:**
```
What programming language is this? Summarize what the code does in 2-3 sentences.
```

### 2. Document Reading & Analysis

**Document Summary:**
```
Summarize the main points of the document currently visible on screen.
Provide key takeaways in bullet points.
```

**Document Type & Info:**
```
What type of document is this? (email, PDF, article, etc.)
Extract the key information: title, author, date, main topic.
```

**Reading Assistant:**
```
Read the text on the screen and explain it in simpler terms. 
Define any complex terms or jargon.
```

**Extract Specific Info:**
```
Extract all dates, numbers, and important facts from the visible document.
Present them in a structured format.
```

### 3. Presentation & Slide Review

**Slide Feedback:**
```
Analyze this presentation slide:
- Is the text readable?
- Is there too much text?
- Are the visuals effective?
- Suggest improvements
```

**Slide Summary:**
```
Summarize the main message of this slide in one sentence.
```

**Design Critique:**
```
Evaluate this slide's design:
- Color scheme
- Layout and spacing
- Font choices
- Visual hierarchy
Rate it 1-10 and suggest specific improvements.
```

### 4. Learning & Education

**Math Problem Solver:**
```
Solve the math problem visible on the screen. 
Show your work step by step.
```

**Study Helper:**
```
Explain the concept shown on screen as if teaching a beginner.
Use analogies and examples.
```

**Language Learning:**
```
Translate any foreign language text visible on screen to English.
Provide pronunciation tips.
```

**Formula Explanation:**
```
Explain what each symbol and component in this formula means.
Show an example calculation.
```

### 5. Web Page Analysis

**Website Review:**
```
Analyze this website:
- Purpose and clarity
- User experience
- Visual design
- Accessibility
- Suggested improvements
```

**Content Extraction:**
```
Extract the main content from this webpage:
- Headline
- Key points
- Links
- Important information
```

**UI/UX Feedback:**
```
Evaluate this user interface:
- Ease of navigation
- Button placement
- Visual hierarchy
- Mobile-friendliness
- Actionable improvements
```

### 6. Data & Spreadsheet Analysis

**Spreadsheet Summary:**
```
Summarize the data shown in this spreadsheet:
- What type of data is it?
- Key trends or patterns
- Notable values (min, max, outliers)
```

**Chart Interpretation:**
```
Describe this chart/graph:
- Type of visualization
- What it shows
- Key insights
- Trends over time (if applicable)
```

**Data Quality Check:**
```
Review this data for:
- Missing values
- Inconsistencies
- Anomalies
- Suggested corrections
```

### 7. Terminal & Command Line

**Command Explanation:**
```
Explain what this terminal command does in plain English.
Break down each flag and argument.
```

**Error Diagnosis:**
```
Analyze this terminal error message:
- What caused the error?
- How to fix it?
- Preventive measures
```

**Script Review:**
```
Review this shell script for:
- Correctness
- Efficiency
- Security issues
- Best practices
```

### 8. Design & Creative Work

**Design Feedback:**
```
Critique this design:
- Composition and balance
- Color harmony
- Typography
- Visual impact
- Professional suggestions
```

**Layout Analysis:**
```
Analyze this layout:
- Grid system
- Spacing and alignment
- Hierarchy
- Improvements for better flow
```

**Before/After Comparison:**
```
Compare the current design to best practices.
What's working well? What needs improvement?
```

### 9. Accessibility

**Screen Reader Description:**
```
Describe everything visible on screen in detail, as if for a blind user.
Include layout, text, images, and UI elements from top to bottom.
```

**Alt Text Generator:**
```
Generate descriptive alt text for all images currently visible.
```

**Readability Check:**
```
Evaluate the readability of the text on screen:
- Font size and contrast
- Reading level
- Clarity
- Accessibility improvements
```

### 10. Productivity & Workflow

**Meeting Notes:**
```
This is a video call. Describe:
- Number of participants visible
- Current speaker
- Presentation content (if any)
- Key points being discussed
```

**Task Extraction:**
```
Extract all action items, tasks, or to-dos visible on the screen.
Format as a checklist.
```

**Dashboard Analysis:**
```
Summarize the key metrics and status shown in this dashboard.
Highlight any alerts or concerning values.
```

### 11. Specialized Use Cases

**Medical Imaging (Educational):**
```
Describe what's visible in this medical image.
Note: For educational purposes only, not for diagnosis.
```

**Architecture/CAD Review:**
```
Describe this architectural drawing/CAD design:
- Type of view (plan, elevation, section)
- Key dimensions
- Notable features
- Potential issues
```

**Scientific Data:**
```
Analyze this scientific visualization:
- What does it represent?
- Scale and units
- Patterns or anomalies
- Scientific interpretation
```

## 🎯 Optimizing Screen Capture Performance

### Recommended Settings

**For Code/Text (Fast, Frequent Updates):**
```
Interval: 1000ms - 2000ms
Instruction: Short and specific
Quality: Can be lower for text
```

**For Detailed Analysis (Design, Complex Data):**
```
Interval: 2000ms - 5000ms
Instruction: Comprehensive
Quality: Higher capture rate
```

**For Real-time Demos/Presentations:**
```
Interval: 500ms - 1000ms
Instruction: Focus on changes or key points
Quality: Balanced
```

### Performance Tips

1. **Share Only What's Needed**
   - Use "Window" mode instead of entire screen
   - Close unnecessary applications
   - Reduces processing load

2. **Adjust Interval Based on Content**
   - Static code: 2000ms is fine
   - Active typing: 1000ms for more updates
   - Slide presentations: 3000-5000ms

3. **Optimize Your Prompt**
   - Shorter prompts = faster responses
   - Be specific about what you want
   - Avoid asking for multiple analyses at once

4. **Model Selection**
   - Qwen2-VL-2B: Good balance for screen content
   - Qwen2-VL-7B: Better for complex analysis
   - SmolVLM: Fast for simple text extraction

## 🔒 Privacy Considerations

When using screen capture mode:

- ⚠️ **Be aware of sensitive information** - The model sees everything on your screen
- ✅ **All processing is local** - Nothing is sent to the cloud
- ✅ **Share specific windows** - Not your entire screen when possible
- ⚠️ **Close sensitive tabs/apps** - Before starting capture
- ✅ **Stop sharing when done** - Don't leave it running unnecessarily

**Remember:** Unlike the webcam, screen capture can see:
- Passwords being typed
- Private messages
- Confidential documents
- Personal information

Always use "Window" mode when working with sensitive content!

## 🎓 Creative Use Cases

### Programming Assistant
```
Window: VS Code
Interval: 1500ms
Prompt: "Review this code. If there are errors, explain them. If it looks good, suggest optimizations."
```

### Live Translation
```
Window: Web Browser
Interval: 2000ms
Prompt: "Translate any non-English text to English. If screen is in English, say 'All English'."
```

### Study Buddy
```
Window: PDF Reader
Interval: 3000ms
Prompt: "Explain the key concept on this page in simple terms. Create a memorable analogy."
```

### Design Critique Bot
```
Window: Figma/Sketch
Interval: 2000ms
Prompt: "Provide one specific design improvement suggestion. Rotate through: layout, colors, typography, spacing."
```

### Documentation Helper
```
Window: Terminal/IDE
Interval: 2000ms
Prompt: "If this is a function/class, write a brief docstring for it. If it's a command, explain what it does."
```

### Meeting Assistant
```
Window: Zoom/Meet
Interval: 5000ms
Prompt: "Who's speaking? What's the current topic? Any action items mentioned?"
```

## 🚀 Advanced Tips

### JSON Output for Automation
```json
{
  "content_type": "code/document/presentation",
  "language": "python",
  "issues": ["issue1", "issue2"],
  "suggestions": ["suggestion1"],
  "confidence": 0.95
}
```

### Chain Multiple Analyses
Switch prompts every few cycles:
1. Cycle 1-3: "What's on screen?"
2. Cycle 4-6: "Any errors or issues?"
3. Cycle 7-9: "Suggest improvements"

### Context-Aware Prompts
```
Remember the previous 3 frames. Has anything changed? 
If yes, explain what changed. If no, say "No changes".
```

## 📊 Comparison: Screen Capture vs Webcam

| Feature | Webcam | Screen Capture |
|---------|--------|----------------|
| Best For | Physical objects, people, scenes | Digital content, code, documents |
| Privacy | Shows physical space | Shows digital workspace |
| Use Cases | Security, detection, AR | Programming, learning, productivity |
| Frame Rate | Can be higher (100ms+) | Usually lower (1000ms+) |
| Resolution | 720p-1080p typical | Full screen resolution |
| Selection | Single camera | Screen/Window/Tab |

## 🛠️ Troubleshooting Screen Capture

**Permission Denied?**
- Go to System Preferences → Security & Privacy → Screen Recording
- Allow your browser to record screen

**Shared Screen is Black?**
- Some apps (like Netflix) block screen capture
- Try sharing a different window
- Check if app has DRM protection

**Performance Issues?**
- Increase interval to 2000ms or more
- Share a single window, not entire screen
- Close other applications
- Use a smaller model

**Can't Select Window?**
- Make sure the app is running and visible
- Minimize then restore the window
- Try using Chrome's "Tab" sharing option

## 🎉 Get Started!

1. Open `index.html`
2. Select **"🖥️ Screen Capture"**
3. Choose a prompt from above
4. Click **Start**
5. Select what to share
6. Watch the AI analyze your screen!

Happy screen capturing! 🖥️✨
