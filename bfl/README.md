# BFL Kontext Suite

A comprehensive Python toolkit for AI image generation and editing using the BFL (Black Forest Labs) Kontext API. This suite provides both interactive and programmatic interfaces for creating and editing high-quality AI-generated images.

## Features

### Text-to-Image Generation
- **Interactive CLI**: Easy-to-use command-line interface
- **Programmatic API**: Use in your own Python scripts
- **Full Kontext Support**: All Kontext model parameters supported
- **Automatic Downloads**: Images are automatically downloaded and saved
- **Error Handling**: Robust error handling and retry logic
- **Progress Tracking**: Real-time status updates during generation

### Image Editing
- **Advanced AI Editing**: Object modification, text editing, style changes
- **Interactive Editor**: CLI interface for image editing workflows
- **Multiple Output Formats**: PNG and JPEG support
- **Automatic Image Processing**: Handles resizing and format conversion
- **Iterative Editing**: Edit images multiple times while maintaining consistency

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Get Your API Key

1. Visit [BFL API](https://docs.bfl.ml/) to get your API key
2. Set it as an environment variable (recommended):

```bash
export BFL_API_KEY="your_api_key_here"
```

Or the program will prompt you to enter it when you run it.

## Usage

### Combined Demo (Recommended)

Run the comprehensive demo that includes both generation and editing:

```bash
python bfl_kontext_demo.py
```

This interactive menu lets you:
- Generate new images from text prompts
- Edit existing images with AI
- List available images in your output folder
- Perform generate-then-edit workflows
- See editing examples and techniques

### Text-to-Image Generation

Run the image generator:

```bash
python bfl_kontext_generator.py
```

### Image Editing

Run the image editor:

```bash
python bfl_kontext_image_editor.py
```

Follow the prompts to:
- Enter your text prompt
- Set image dimensions (default: 1024x1024)
- Configure prompt upsampling (enhances prompts for better results)
- Set safety tolerance (1-6, where 1 is strictest)
- Optionally set a seed for reproducible results

### Programmatic Usage

#### Text-to-Image Generation

Use the generator in your own scripts:

```python
from bfl_kontext_generator import BFLKontextGenerator
import os

# Initialize the generator
api_key = os.getenv("BFL_API_KEY")
generator = BFLKontextGenerator(api_key)

# Generate an image
image_path = generator.generate_image(
    prompt="A beautiful sunset over mountains",
    width=1024,
    height=1024,
    prompt_upsampling=True,
    safety_tolerance=2,
    seed=42  # Optional, for reproducible results
)

if image_path:
    print(f"Image saved to: {image_path}")
```

#### Image Editing

Use the editor in your own scripts:

```python
from bfl_kontext_image_editor import BFLKontextImageEditor
import os

# Initialize the editor
api_key = os.getenv("BFL_API_KEY")
editor = BFLKontextImageEditor(api_key)

# Edit an image
edited_image_path = editor.edit_image(
    input_image_path="path/to/your/image.jpg",
    prompt="Change the car color to red",
    safety_tolerance=2,
    output_format="png",
    seed=42  # Optional, for reproducible results
)

if edited_image_path:
    print(f"Edited image saved to: {edited_image_path}")
```

### Example Scripts

Run example scripts to see different usage patterns:

**Text-to-Image Examples:**
```bash
python example_usage.py
```

**Image Editing Examples:**
```bash
python example_image_editing.py
```

## Parameters

### Text-to-Image Generation

#### Required
- **prompt** (str): Text description of the image to generate

#### Optional
- **width** (int): Image width in pixels (default: 1024)
- **height** (int): Image height in pixels (default: 1024)
- **prompt_upsampling** (bool): Enhance prompt for better results (default: False)
- **safety_tolerance** (int): Content filtering level 1-6 (default: 2)
  - 1: Strictest filtering
  - 6: Most permissive
- **seed** (int): Random seed for reproducible results (optional)

### Image Editing

#### Required
- **input_image_path** (str): Path to the input image file
- **prompt** (str): Text description of the edit to perform

#### Optional
- **seed** (int): Random seed for reproducible results (optional)
- **safety_tolerance** (int): Content filtering level 0-6 (default: 2)
  - 0: Strictest filtering
  - 6: Most permissive
- **output_format** (str): Output format "png" or "jpeg" (default: "png")

## Output

Images are saved in the `output/` directory with descriptive filenames:

**Generated Images:**
- Format: `kontext_{safe_prompt}_{timestamp}.png`
- Example: `kontext_beautiful_sunset_1733555123.png`

**Edited Images:**
- Format: `edited_{original_name}_{edit_description}_{timestamp}.{extension}`
- Example: `edited_photo_red_car_1733555123.png`

## Error Handling

The tools handle various error conditions:
- Network timeouts and retries
- Content moderation (if prompt/edit violates safety guidelines)
- API rate limits
- Invalid parameters
- File not found errors (for image editing)
- Image format conversion issues

## Image Editing Techniques

### Object Modifications
- `"Change the car color to red"`
- `"Make the flowers purple"`
- `"Turn the building into glass"`

### Text Editing
- `"Replace 'Hello' with 'Goodbye'"` (use quotes for specific text)
- `"Change the sign text to 'OPEN'"`
- `"Replace 'joy' with 'BFL'"`

### Style Changes
- `"Make it look like a watercolor painting"`
- `"Convert to black and white"`
- `"Add vintage film effect"`

### Object Addition/Removal
- `"Add glasses to the person"`
- `"Remove the background"`
- `"Add clouds to the sky"`

### Lighting and Atmosphere
- `"Make it sunset lighting"`
- `"Add dramatic shadows"`
- `"Make it look like nighttime"`

## File Structure

```
.
├── bfl_kontext_generator.py      # Text-to-image generation
├── bfl_kontext_image_editor.py   # Image editing functionality  
├── bfl_kontext_demo.py           # Combined interactive demo
├── example_usage.py              # Text-to-image examples
├── example_image_editing.py      # Image editing examples
├── requirements.txt              # Python dependencies
├── README.md                     # Main documentation
├── README_IMAGE_EDITING.md       # Image editing documentation
└── output/                       # Generated and edited images
    ├── kontext_sunset_1733555123.png
    └── edited_photo_red_car_1733555456.png
```

## API Documentation

For more details about the BFL Kontext API, see the official documentation:
https://docs.bfl.ml/kontext/kontext_text_to_image

## License

This project is provided as-is for educational and development purposes.
