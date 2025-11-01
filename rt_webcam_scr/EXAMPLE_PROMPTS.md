# Example Prompts for Different Use Cases

This file contains ready-to-use prompts for various vision analysis scenarios in both **Webcam Mode** and **Screen Capture Mode**.

## 📷 Webcam Mode Prompts

Use these when analyzing physical scenes through your camera.

## Object Detection

### Simple List
```
List all objects you can see in this image, separated by commas.
```

### Detailed Inventory
```
Create a detailed inventory of all objects visible in the image. For each object, include:
1. The object name
2. Its approximate location (left/right/center, top/bottom)
3. Any notable characteristics
```

### Counting Objects
```
Count and list how many of each type of object you can see. Format: "X chairs, Y books, Z pens"
```

## Scene Description

### Quick Description
```
Describe this scene in one sentence.
```

### Detailed Scene Analysis
```
Provide a comprehensive description of this scene including:
- Overall setting and environment
- Main objects and their arrangement
- Colors and lighting
- Mood or atmosphere
- Any text visible in the image
```

### Professional Photography Analysis
```
Analyze this image from a photography perspective:
- Composition and framing
- Lighting (natural/artificial, quality, direction)
- Color palette and mood
- Subject focus and depth of field
- Suggested improvements
```

## People & Activities

### Person Detection
```
How many people are in this image? Describe their approximate age, gender, and what they're wearing.
```

### Activity Recognition
```
Describe what the person(s) in this image are doing. Be specific about:
- Their primary activity
- Body language and posture
- Facial expressions (if visible)
- Objects they're interacting with
```

### Safety Monitoring
```
Analyze this scene for safety concerns:
- Are people wearing required safety equipment?
- Are there any hazards visible?
- Is the workspace organized appropriately?
- Any immediate safety recommendations?
```

## Text & Document Analysis

### Text Extraction
```
Extract and transcribe all visible text in this image. Preserve formatting where possible.
```

### Document Type
```
What type of document is this? (e.g., receipt, form, book page, sign, etc.) 
Summarize the main information it contains.
```

### Receipt Analysis
```
This is a receipt. Extract:
- Store name
- Date and time
- Items purchased
- Total amount
- Payment method (if visible)
```

## Technical & Specialized

### Code Review (for screens showing code)
```
This image shows code. Analyze:
- Programming language
- What the code does
- Any visible bugs or issues
- Code quality observations
```

### Medical/Health (General)
```
Describe what you see in this image in medical terms. 
Note: This is for informational purposes only, not medical diagnosis.
```

### Plant Identification
```
Describe the plant(s) in this image:
- Type/species (if identifiable)
- Condition (healthy, needs water, etc.)
- Distinctive features
- Growing environment
```

## Creative & Entertainment

### Art Analysis
```
Analyze this artwork:
- Style and medium
- Subject matter
- Color scheme
- Emotional impact
- Historical or cultural context (if apparent)
```

### Fashion Description
```
Describe the clothing and fashion in this image:
- Style and era
- Colors and patterns
- Fabrics and textures
- Overall aesthetic
- Occasion appropriateness
```

### Meme/Humor Detection
```
Describe what makes this image funny or interesting. 
Identify any memes, jokes, or cultural references.
```

## JSON Output (Structured Data)

### Simple Object List
```
Return a JSON object with this structure:
{
  "objects": ["object1", "object2"],
  "count": 0,
  "scene_type": "indoor/outdoor"
}
```

### Detailed Analysis
```
Analyze this image and return JSON:
{
  "scene": "description",
  "objects": [{"name": "object", "location": "position", "count": 1}],
  "people": {"count": 0, "activities": []},
  "colors": ["dominant_color1", "dominant_color2"],
  "lighting": "description",
  "mood": "description"
}
```

### Safety Checklist
```
Safety analysis in JSON:
{
  "people_count": 0,
  "ppe_worn": ["helmet", "gloves"],
  "ppe_missing": [],
  "hazards": [],
  "safety_score": 0-10,
  "recommendations": []
}
```

## Accessibility

### Alt Text Generation
```
Generate descriptive alt text for this image suitable for screen readers. 
Be concise but informative.
```

### Detailed Description for Blind Users
```
Provide a detailed audio description of this image as if describing it to someone who cannot see:
- Start with the overall scene
- Describe main subjects in detail
- Include spatial relationships
- Mention colors, textures, lighting
- Note any text or important details
```

## Quality Control & Inspection

### Product Inspection
```
Inspect this product image for:
- Defects or damage
- Quality of construction
- Completeness (all parts present)
- Packaging condition
- Overall quality rating (1-10)
```

### Food Quality
```
Analyze this food image:
- Freshness indicators
- Appearance and presentation
- Potential issues
- Estimated temperature (hot/cold/room temp)
- Appeal rating (1-10)
```

## Tips for Writing Your Own Prompts

### Be Specific
Instead of: "Describe this"
Try: "Describe the lighting, composition, and mood of this photograph"

### Use Structure
```
Analyze this image in three parts:
1. [First aspect]
2. [Second aspect]
3. [Third aspect]
```

### Request Format
- For structured output, specify JSON schema
- For lists, specify separator (commas, bullets, numbered)
- For narratives, specify length (brief, detailed, comprehensive)

### Focus on Action Verbs
- Identify, List, Count, Describe, Analyze, Compare, Evaluate
- Extract, Summarize, Categorize, Detect, Recognize

### Combine Multiple Requests
```
Describe this scene, then list all visible objects, 
and finally suggest what might be happening here.
```

## Adjusting for Performance

**Fast/Real-time (100-250ms):**
- Short, specific prompts
- Single focus (e.g., "List objects")
- Avoid complex analysis

**Balanced (500ms):**
- Moderate detail
- 2-3 specific requests
- Basic analysis

**Detailed (1000-2000ms):**
- Comprehensive descriptions
- Multiple aspects
- Deep analysis
- Structured output

## Model-Specific Tips

**Qwen2-VL:**
- Excellent at: Detailed descriptions, Chinese text, technical content
- Strong multilingual support

**SmolVLM:**
- Excellent at: Fast object detection, basic scene understanding
- Keep prompts simple for best speed

**LLaVA:**
- Excellent at: General descriptions, conversation-style responses
- Good balance of speed and detail

Happy prompting! 🎨✨

---

## 🖥️ Screen Capture Mode Prompts

Use these when analyzing your Mac screen content. See **SCREEN_CAPTURE_GUIDE.md** for detailed use cases.

### Programming & Code

**Debug Assistant:**
```
Analyze this code for bugs or errors. Explain what's wrong and suggest fixes.
```

**Code Explainer:**
```
Explain what this code does in simple terms, line by line.
```

**Best Practices Review:**
```
Review this code for best practices, performance, and security. Provide 3 specific improvements.
```

### Document Analysis

**Quick Summary:**
```
Summarize this document in 3 bullet points.
```

**Key Information Extraction:**
```
Extract: title, author, date, main topic, and 3 key takeaways.
```

**Technical Document Parser:**
```
This is technical documentation. Extract: API endpoints, parameters, return values, and examples.
```

### Terminal & Command Line

**Command Explainer:**
```
Explain this terminal command in plain English. Break down each flag and option.
```

**Error Diagnosis:**
```
This is an error message. What caused it? How do I fix it? Step by step.
```

**Script Reviewer:**
```
Review this shell script for correctness, security issues, and improvements.
```

### Design & UI/UX

**Design Critique:**
```
Critique this design: layout, colors, typography, spacing. Rate 1-10 and suggest improvements.
```

**Accessibility Check:**
```
Evaluate this UI for accessibility: contrast, font size, button placement, screen reader compatibility.
```

**Mobile Responsiveness:**
```
Is this design mobile-friendly? What would break on smaller screens?
```

### Data & Spreadsheets

**Data Summary:**
```
Summarize this data: type, range, trends, outliers, and key insights.
```

**Chart Analysis:**
```
Describe this visualization: type, what it shows, trends, and main takeaway.
```

### Learning & Education

**Concept Explainer:**
```
Explain this concept as if I'm a beginner. Use analogies and examples.
```

**Study Helper:**
```
Create 3 quiz questions based on the content visible on screen.
```

**Formula Breakdown:**
```
Break down this formula: what each part means and a worked example.
```

### Presentation Review

**Slide Critique:**
```
Evaluate this slide: message clarity, text amount, visual appeal. One specific improvement.
```

**Speaker Notes:**
```
Generate brief speaker notes for this slide in 3 bullet points.
```

### Web Development

**HTML/CSS Review:**
```
Review this HTML/CSS: semantic correctness, accessibility, and modern best practices.
```

**Responsive Design Check:**
```
Analyze this webpage layout. Will it work on mobile? Suggest breakpoint improvements.
```

### Quick Screen Capture Prompts

**Universal Analyzer:**
```
What am I looking at? Identify the type of content and summarize it briefly.
```

**Error Helper:**
```
If this is an error, help me fix it. If not, summarize what's on screen.
```

**Readability Check:**
```
Rate the readability of this content 1-10. Suggest improvements for clarity.
```

**Text Extraction:**
```
Extract all visible text, preserving structure and formatting.
```

**Action Items:**
```
Extract all tasks, to-dos, or action items from this screen. Format as a checklist.
```

---

**Pro Tip:** Combine screen capture with specific window sharing:
- Share VS Code → Code review prompts
- Share Terminal → Command/error prompts  
- Share Browser → Web analysis prompts
- Share PDF Reader → Document prompts

See **SCREEN_CAPTURE_GUIDE.md** for 50+ more examples! 🚀
