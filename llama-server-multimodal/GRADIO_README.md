# Multimodal Image Analyzer & Tagger - Gradio Web App

A web-based interface for analyzing images using various styles via OpenAI-compatible multimodal models.

## Features

- Interactive web interface powered by Gradio
- Upload images directly through the browser, webcam, or clipboard
- Choose from pre-defined analysis styles:
  - **simple**: General image descriptions optimized for image generation
  - **booru**: Booru-style tagging for image generation
  - **nsfwclassifier**: NSFW content classification and detailed description
  - **artistic**: Artistic analysis with detailed descriptions
  - **satmet**: Weather forecast analysis for meteorological images
- Option to enter your own custom prompt
- Real-time results displayed in the browser
- Save results to file with a single click
- Clear interface function for batch processing
- Detailed error handling and user feedback
- Markdown formatting support in results

## Prerequisites

1. Python 3.7+ with pip
2. OpenAI API key or a running llama.cpp server with multimodal support

## Installation

1. Install the required packages:

```bash
pip install -r gradio_requirements.txt
```

2. Set up your environment variables in a `.env` file:

```
OPENAI_API_KEY=your_api_key_here
OPENAI_API_BASE_URL=http://localhost:8080/v1  # Optional: for using a local server
GRADIO_HOST=127.0.0.1  # Optional: default host for the Gradio app
GRADIO_PORT=7861  # Optional: default port for the Gradio app
```

## Usage

1. Run the app:

```bash
python gradio_tagger_app.py
```

2. Open your web browser and navigate to:

```
http://127.0.0.1:7861
```

3. Use the web interface:
   - Upload an image by clicking on the image upload area or using the webcam/clipboard
   - Select an analysis style from the radio buttons
   - If you select "custom", a text area will appear for you to enter your own prompt
   - Click "Analyze Image" to get results
   - Use "Save Result" to download the analysis as a text file
   - Use "Clear" to reset the interface for a new analysis

## Using Custom Prompts

When selecting the "custom" option, a text area will appear where you can enter your own prompt. This gives you complete control over how the image is analyzed.

Examples of custom prompts:

- **Technical analysis**: "Analyze this circuit diagram and explain how it works in detail."
- **Medical evaluation**: "Identify any visible skin conditions in this image and provide potential diagnoses."
- **Cultural analysis**: "Explain the cultural and historical significance of the symbols in this image."

## Troubleshooting

- If you encounter CORS errors with a local llama.cpp server, make sure your server has CORS enabled
- For memory errors, try reducing the image size before uploading
- If the app doesn't start, check that the port (default 7861) is not already in use

## Customizing the App

### Adding New Analysis Styles

To add a new analysis style, modify the `PROMPT_TYPES` dictionary in `gradio_tagger_app.py`:

```python
PROMPT_TYPES = {
    # ... existing prompt types ...
    "your_new_style": "Your custom prompt text here...",
}
```

### Changing the Model

By default, the app uses the "gpt-4.1" model. To use a different model, change the `model` parameter in the `query_multimodal_model` call in the `process_image` function.

## Troubleshooting

- If you encounter CORS errors with a local llama.cpp server, make sure your server has CORS enabled
- For memory errors, try reducing the image size before uploading
