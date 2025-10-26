# Multimodal Image Analyzer & Tagger

This tool automatically analyzes images using multimodal models through OpenAI-compatible APIs. It processes all images in a specified directory, generates descriptions/tags for each image based on various analysis styles, and saves the results to text files.

## Features

- Supports multiple tagging styles through command-line arguments:
  - `simple`: General image descriptions optimized for image generation
  - `booru`: Booru-style tagging for image generation
  - `nsfwclassifier`: NSFW content classification and detailed description
  - `artistic`: Artistic analysis with detailed descriptions
  - `satmet`: Weather forecast analysis for meteorological images
- OpenAI-compatible API usage (works with local llama.cpp server or OpenAI API)
- Batch processes all images in a directory
- Saves analysis results as text files with matching names
- Environment variable support for configuration

## Prerequisites

1. Python 3.6+ with required packages
2. OpenAI API key (or a running llama.cpp server with multimodal support)

## Setup

1. Install the required Python packages:
   ```
   pip install openai python-dotenv
   ```

2. Set up your environment variables in a `.env` file:
   ```
   OPENAI_API_KEY=your_api_key_here
   OPENAI_API_BASE_URL=http://localhost:8080/v1  # Optional: for using a local server
   IMAGES_FOLDER=pics  # Optional: default folder for images
   ```

3. Place your images in the `pics/` directory (or your custom directory).

## Usage

Run the script with:

```
python multimodal_tagger.py [options]
```

### Command Line Arguments

- `--tagtype`: Type of tagging prompt to use (choices: simple, booru, nsfwclassifier, artistic, satmet)
- `--folder`: Folder containing images to process

Examples:

```bash
# Use default settings (booru tagging)
python multimodal_tagger.py

# Use simple tagging style
python multimodal_tagger.py --tagtype simple

# Use artistic tagging with custom folder
python multimodal_tagger.py --tagtype artistic --folder ./my_images

# Run NSFW classification
python multimodal_tagger.py --tagtype nsfwclassifier --folder ./nsfw_pics
```

## Output

For each image processed (e.g., `image1.jpg`), the tool will create a corresponding text file (e.g., `image1.txt`) in the same directory containing the analysis results.

## Implementation Details

The tool uses OpenAI's Python client library to:
1. Encode images to base64
2. Send multimodal requests with both text and image
3. Process and save the responses

For local deployment, you can use a llama.cpp server that implements the OpenAI API compatibility layer. Simply set the `OPENAI_API_BASE_URL` environment variable to point to your local server.

## Extending the Tool

To add a new tagging style:
1. Add a new entry to the `PROMPT_TYPES` dictionary in the script
2. Use the new tag type with `--tagtype your_new_type`