# BFL Kontext Image Editor

A Python client for editing images using the BFL (Black Forest Labs) Kontext API. This tool provides both interactive and programmatic interfaces for AI-powered image editing using the advanced Kontext model.

## Features

- **Interactive CLI**: Easy-to-use command-line interface for image editing
- **Programmatic API**: Use in your own Python scripts
- **Advanced Image Editing**: Object modification, text editing, style changes, and more
- **Automatic Image Processing**: Handles image conversion, resizing, and format conversion
- **Error Handling**: Robust error handling and retry logic
- **Multiple Output Formats**: Support for PNG and JPEG output
- **Progress Tracking**: Real-time status updates during editing

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

## Usage

### Interactive Mode

Run the interactive image editor:

```bash
python bfl_kontext_image_editor.py
```

Follow the prompts to:
- Select your input image file
- Enter your edit prompt
- Configure safety tolerance (0-6)
- Choose output format (PNG/JPEG)
- Optionally set a seed for reproducible results

### Programmatic Usage

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

### Example Script

Run the example script to see different editing techniques:

```bash
python example_image_editing.py
```

## Editing Techniques

### 1. Object Modifications
Change colors, materials, or properties of objects in your images:
- `"Change the car color to red"`
- `"Make the flowers purple"`
- `"Turn the building into glass"`

### 2. Text Editing
Directly edit text that appears in images:
- `"Replace 'Hello' with 'Goodbye'"` 
- `"Change the sign text to 'OPEN'"`
- `"Replace 'joy' with 'BFL'"` (note: use quotes for specific text)

### 3. Style Changes
Apply artistic styles and effects:
- `"Make it look like a watercolor painting"`
- `"Convert to black and white"`
- `"Add vintage film effect"`

### 4. Object Addition/Removal
Add or remove elements from your images:
- `"Add glasses to the person"`
- `"Remove the background"`
- `"Add clouds to the sky"`

### 5. Lighting and Atmosphere
Modify the mood and lighting:
- `"Make it sunset lighting"`
- `"Add dramatic shadows"`
- `"Make it look like nighttime"`

### 6. Iterative Editing
Perform multiple edits in sequence while maintaining consistency:
- Use the output of one edit as input for the next
- Kontext maintains character and object consistency across multiple edits

## Parameters

### Required
- **input_image_path** (str): Path to the input image file
- **prompt** (str): Text description of the edit to perform

### Optional
- **seed** (int): Random seed for reproducible results (optional)
- **safety_tolerance** (int): Content filtering level 0-6 (default: 2)
  - 0: Strictest filtering
  - 6: Most permissive
- **output_format** (str): Output format "png" or "jpeg" (default: "png")

## Input Image Requirements

- **Supported formats**: JPEG, PNG, WebP, and other PIL-supported formats
- **Automatic processing**: Images are automatically resized if larger than 2048x2048
- **Color mode handling**: RGBA/LA images are converted to RGB as needed
- **Base64 conversion**: Images are automatically converted to base64 for API submission

## Output

Edited images are saved in the `output/` directory with descriptive filenames:
- Format: `edited_{original_name}_{edit_description}_{timestamp}.{extension}`
- Example: `edited_photo_red_car_1733555123.png`

## Error Handling

The editor handles various error conditions:
- File not found errors
- Image format conversion issues
- Network timeouts and retries
- Content moderation (if edit violates safety guidelines)
- API rate limits
- Invalid parameters

## Best Practices

### Prompting Tips
1. **Be specific**: Instead of "change the color", use "change the car color to bright red"
2. **Use quotes for text**: When editing text, use quotes around the specific text to change
3. **Describe the desired outcome**: Focus on what you want the result to look like
4. **Consider the context**: Make sure your edit makes sense within the image context

### Technical Tips
1. **Image quality**: Use high-quality input images for best results
2. **File size**: Large images are automatically resized but may lose detail
3. **Format choice**: Use PNG for images with transparency, JPEG for photographs
4. **Safety tolerance**: Adjust based on your content requirements
5. **Seeds**: Use seeds when you want to reproduce the same edit result

## File Structure

```
.
├── bfl_kontext_image_editor.py   # Main editor class and CLI
├── example_image_editing.py      # Example usage patterns and techniques
├── requirements.txt              # Python dependencies
├── README_IMAGE_EDITING.md       # This file
└── output/                       # Edited images saved here
    ├── edited_photo_red_car_1733555123.png
    └── edited_landscape_sunset_1733555456.jpg
```

## API Documentation

For more details about the BFL Kontext Image Editing API:
- [Kontext Image Editing Guide](https://docs.bfl.ml/kontext/kontext_image_editing)
- [Prompting Guide for Image-to-Image](https://docs.bfl.ml/guides/prompting_guide_kontext_i2i)

## Limitations

- **Signed URL validity**: Downloaded images must be retrieved within 10 minutes
- **Content filtering**: Some edits may be blocked by safety filters
- **Processing time**: Complex edits may take several minutes to complete
- **API limits**: Subject to BFL API rate limits and usage policies

## License

This project is provided as-is for educational and development purposes.
