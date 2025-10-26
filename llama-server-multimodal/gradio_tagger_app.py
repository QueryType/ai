import os
import base64
import tempfile
import gradio as gr
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Define different prompt types (same as in multimodal_tagger.py)
PROMPT_TYPES = {
    "simple": "You are expert in image description for training image generation models. Please describe this image. Focus on the main subject of the image. Describe the physical build and figure if the subject is a person. Include background information too. Do not include any irrelevant tags. These will be used to train a model to generate images from text. Please do not include any other text in the response.",
    "booru": "You are expert in Booru tagging. Please tag this image. Focus on the main subject of the image. Describe tags for physical structure if the subject is a person. Do not include any irrelevant tags. The tags should be separated by commas. These will be used to train a model to generate images from text. Please do not include any other text in the response.",
    "nsfwclassifier": "You are an expert in content classification. Please classify this image for content appropriateness and provide a general description including the subject matter and context. Focus on overall composition and themes rather than explicit details. Respond in Markdown format.",
    "artistic": "You are an expert art critic with keen attention to detail. Analyze this image from an artistic perspective. First categorize the image by type (nature, portrait, abstract, etc.), then focus on the central theme. Provide a detailed analysis covering composition, color theory, lighting, style, and artistic techniques used. Respond in Markdown format with professional art criticism.",
    "satmet": "You are an expert weather analyst. You are provided with a forecast of the weather for the next few days. The image will contain, the location, date and trends of the rainfall, temperature and humidity. Based on the image, please provide a detailed analysis of the weather forecast in the image."
}

# Define prompt enhancement styles
ENHANCEMENT_STYLES = {
    "cinematic": {
        "name": "Cinematic",
        "description": "Movie-like quality with dramatic lighting and composition",
        "keywords": "cinematic lighting, dramatic composition, film grain, depth of field, bokeh"
    },
    "photorealistic": {
        "name": "Photorealistic",
        "description": "Ultra-realistic photography style",
        "keywords": "photorealistic, highly detailed, 8k uhd, dslr, soft lighting, high quality"
    },
    "artistic": {
        "name": "Artistic/Painterly",
        "description": "Artistic interpretation with painterly qualities",
        "keywords": "artistic, painterly, expressive brushstrokes, vibrant colors, creative composition"
    },
    "fantasy": {
        "name": "Fantasy",
        "description": "Magical and fantastical elements",
        "keywords": "fantasy art, magical atmosphere, ethereal lighting, mystical, enchanting"
    },
    "scifi": {
        "name": "Sci-Fi",
        "description": "Futuristic and science fiction themed",
        "keywords": "sci-fi, futuristic, neon lights, cyberpunk, technological, advanced"
    },
    "vintage": {
        "name": "Vintage",
        "description": "Retro and nostalgic aesthetics",
        "keywords": "vintage, retro, nostalgic, film photography, faded colors, classic"
    },
    "minimalist": {
        "name": "Minimalist",
        "description": "Clean and simple composition",
        "keywords": "minimalist, clean composition, simple, negative space, elegant"
    },
    "dramatic": {
        "name": "Dramatic",
        "description": "High contrast and moody atmosphere",
        "keywords": "dramatic lighting, high contrast, moody, shadows, intense atmosphere"
    },
    "mature": {
        "name": "Mature Themes",
        "description": "Content with mature artistic themes and sophisticated subject matter",
        "keywords": "mature artistic themes, sophisticated composition, tasteful presentation"
    }
}

# System prompt for prompt enhancement
PROMPT_ENHANCER_SYSTEM = """You are an expert prompt engineer specializing in image generation prompts. Your task is to take a user's basic image description and enhance it into a detailed, vivid prompt that will produce high-quality results in image generation models.

When enhancing prompts:
1. Expand on the core concept while staying true to the user's vision
2. Add specific details about composition, lighting, colors, and atmosphere
3. Include technical photography terms when relevant
4. Incorporate the selected style and mood effectively
5. Keep the enhanced prompt clear and well-structured
6. Aim for 2-4 sentences that flow naturally
7. Do not add any explanations or meta-text, just return the enhanced prompt

The enhanced prompt should be ready to use directly in an image generation model."""

# Get custom base URL from environment variables, with fallback to default
base_url = os.environ.get("OPENAI_API_BASE_URL")

model = os.environ.get("VISION_MODEL", "dummy")

# Initialize the OpenAI client once at module level
client = OpenAI(base_url=base_url) if base_url else OpenAI()


def encode_image_from_path(image_path):
    """
    Encode an image to base64 string from a file path
    
    Args:
        image_path (str): Path to the image file
        
    Returns:
        str: Base64 encoded image string
    """
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def encode_image_from_bytes(image_bytes):
    """
    Encode an image to base64 string from bytes
    
    Args:
        image_bytes (bytes): Image bytes
        
    Returns:
        str: Base64 encoded image string
    """
    return base64.b64encode(image_bytes).decode("utf-8")


def query_multimodal_model(prompt, image, model=model):
    """
    Query a multimodal model with text and image
    
    Args:
        prompt (str): Text prompt to send to the model
        image: Image data (can be path or bytes)
        model (str): Model identifier
        
    Returns:
        str: Model response text
    """
    try:
        # Handle different image input types for Gradio
        if isinstance(image, str):
            # Image is a file path
            base64_image = encode_image_from_path(image)
        else:
            # Handle temporary file from Gradio
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(image)
                temp_file_path = temp_file.name
            
            base64_image = encode_image_from_path(temp_file_path)
            # Clean up the temporary file
            os.unlink(temp_file_path)
        
        # Make the API call using the global client
        response = client.chat.completions.create(
            model=model,
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                        },
                    },
                ],
            }],
        )
        
        return response.choices[0].message.content
    except Exception as e:
        # More descriptive error messages
        if "API key" in str(e):
            return "Error: Missing or invalid API key. Please check your .env file."
        elif "base_url" in str(e):
            return "Error: Cannot connect to API endpoint. Please check your connection and server settings."
        else:
            return f"Error querying model: {str(e)}"


def save_output_to_file(image_path, output_text):
    """
    Save the model's output to a text file with the same name as the image
    
    Args:
        image_path (str): Path to the image file
        output_text (str): Text to save to file
        
    Returns:
        str: Path to the saved output file
    """
    # Get the filename without extension
    path = Path(image_path)
    output_file = path.with_suffix('.txt')
    
    # Save the output to a text file
    with open(output_file, 'w') as f:
        f.write(output_text)
    
    return str(output_file)


def enhance_text_prompt(user_prompt, style, mood, additional_details=""):
    """
    Enhance a user's text prompt for image generation
    
    Args:
        user_prompt (str): The user's basic prompt
        style (str): Selected visual style
        mood (str): Selected mood/ambience
        additional_details (str): Optional additional details to include
        
    Returns:
        str: Enhanced prompt
    """
    if not user_prompt or user_prompt.strip() == "":
        return "Error: Please enter a prompt to enhance."
    
    try:
        # Build the user message
        style_info = ENHANCEMENT_STYLES.get(style, {})
        style_keywords = style_info.get("keywords", "")
        
        user_message = f"""Please enhance this image generation prompt:

Original prompt: {user_prompt}

Style: {style_info.get('name', style)} - {style_info.get('description', '')}
Mood/Ambience: {mood}
{f'Additional details to include: {additional_details}' if additional_details else ''}

Create an enhanced, detailed prompt that incorporates the {style} style with a {mood} mood. Include relevant technical and artistic details."""

        # Make the API call
        response = client.chat.completions.create(
            model=model,
            max_tokens=500,
            messages=[
                {"role": "system", "content": PROMPT_ENHANCER_SYSTEM},
                {"role": "user", "content": user_message}
            ],
        )
        
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error enhancing prompt: {str(e)}"


def process_image(image, prompt_type, custom_prompt=None):
    """
    Process an image with the selected prompt type or custom prompt
    
    Args:
        image: Image data from Gradio
        prompt_type (str): The type of prompt to use (or 'custom')
        custom_prompt (str, optional): Custom prompt text if prompt_type is 'custom'
        
    Returns:
        tuple: (status message, model's response)
    """
    if image is None:
        return "Please upload an image to analyze.", ""
    
    # Determine which prompt to use
    if prompt_type == "custom":
        if not custom_prompt or custom_prompt.strip() == "":
            return "Please enter a custom prompt in the text area.", ""
        prompt = custom_prompt.strip()
        print(f"Using custom prompt: {prompt}")
    else:
        prompt = PROMPT_TYPES.get(prompt_type, "Describe this image in detail.")
        print(f"Using {prompt_type} analysis style")
    
    # Save uploaded image to a temporary file
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
        if isinstance(image, dict) and "image" in image:  # Gradio image object
            temp_file.write(image["image"])
            image_path = temp_file.name
        elif isinstance(image, str):  # Already a file path
            image_path = image
        else:
            return "Error: Invalid image format", ""
    
    try:
        # Query the model
        status_message = f"*Analyzing image with {prompt_type if prompt_type != 'custom' else 'custom'} style...*"
        result = query_multimodal_model(prompt, image_path, model="gpt-4.1")
        
        # Save the result to a file if it's a real file path (not a temp file)
        if not image_path.startswith(tempfile.gettempdir()):
            save_output_to_file(image_path, result)
        
        # Clean up temp file if it was created
        if image_path.startswith(tempfile.gettempdir()):
            os.unlink(image_path)
        
        status_message = f"*Analysis complete using {prompt_type if prompt_type != 'custom' else 'custom'} style*"
        return status_message, result
    except Exception as e:
        if image_path.startswith(tempfile.gettempdir()) and os.path.exists(image_path):
            os.unlink(image_path)
        error_message = f"Error processing image: {str(e)}"
        return error_message, ""


# Define Gradio interface components
def create_gradio_interface():
    with gr.Blocks(title="Multimodal Image Analyzer & Tagger", theme=gr.themes.Soft()) as app:
        gr.Markdown("# 🖼️ Multimodal Image Analyzer & Tagger")
        gr.Markdown("Upload an image and select an analysis style to get detailed tags or descriptions of your image.")
        gr.Markdown("*Use the 'Custom' option to create your own custom prompt for image analysis.*")
        
        with gr.Tabs():
            with gr.TabItem("📊 Image Analysis"):
                with gr.Row():
                    with gr.Column(scale=1):
                        # Input components
                        image_input = gr.Image(
                            type="filepath", 
                            label="Upload Image",
                            sources=["upload", "webcam", "clipboard"]
                        )
                        
                        # Prompt type selection with radio
                        prompt_types = list(PROMPT_TYPES.keys()) + ["custom"]
                        prompt_type = gr.Radio(
                            prompt_types, 
                            label="Select Analysis Style", 
                            value="booru",
                            info="Choose one of the predefined styles or 'custom' to write your own prompt"
                        )
                        
                        # Custom prompt input area - initially hidden
                        custom_prompt = gr.Textbox(
                            label="Custom Prompt",
                            lines=4,
                            placeholder="Enter your custom prompt here to analyze the image...",
                            visible=False
                        )
                        
                        # Add analyze button at bottom of left column
                        analyze_btn = gr.Button("✨ Analyze Image", variant="primary", size="lg")
                    
                    with gr.Column(scale=1):
                        # Output components
                        status_text = gr.Markdown("*Ready for analysis. Upload an image and select an analysis style.*")
                        output_text = gr.Markdown(label="Analysis Result")
                        with gr.Row():
                            clear_btn = gr.Button("🗑️ Clear", variant="secondary")
                            save_btn = gr.Button("💾 Save Result", variant="secondary", interactive=False)
                        result_file = gr.File(label="Saved Result", visible=False)
                
                # Show/hide custom prompt based on selection
                def update_custom_prompt_visibility(choice):
                    return gr.update(visible=(choice == "custom"))
                
                prompt_type.change(
                    fn=update_custom_prompt_visibility,
                    inputs=prompt_type,
                    outputs=custom_prompt
                )
            
            with gr.TabItem("✨ Prompt Enhancer"):
                gr.Markdown("## Visual Prompt Enhancer")
                gr.Markdown("Describe the image you have in mind, and get an enhanced, detailed prompt perfect for image generation models.")
                
                with gr.Row():
                    with gr.Column(scale=1):
                        # Input components
                        basic_prompt = gr.Textbox(
                            label="Your Image Description",
                            lines=3,
                            placeholder="E.g., A cat sitting on a windowsill at sunset...",
                            info="Describe the image you want to create"
                        )
                        
                        # Style selection
                        style_choices = list(ENHANCEMENT_STYLES.keys())
                        style_select = gr.Dropdown(
                            choices=style_choices,
                            label="Visual Style",
                            value="cinematic",
                            info="Choose the overall visual style"
                        )
                        
                        # Style description display
                        style_description = gr.Markdown(ENHANCEMENT_STYLES["cinematic"]["description"])
                        
                        # Mood/Ambience selection
                        mood_select = gr.Radio(
                            choices=["Bright and cheerful", "Dark and moody", "Calm and serene", 
                                    "Energetic and vibrant", "Mysterious", "Warm and cozy", "Cold and stark"],
                            label="Mood/Ambience",
                            value="Bright and cheerful",
                            info="Set the overall mood of the scene"
                        )
                        
                        # Additional details
                        additional_details = gr.Textbox(
                            label="Additional Details (Optional)",
                            lines=2,
                            placeholder="E.g., Include golden hour lighting, shallow depth of field...",
                            info="Any specific elements you want to emphasize"
                        )
                        
                        enhance_btn = gr.Button("✨ Enhance Prompt", variant="primary", size="lg")
                    
                    with gr.Column(scale=1):
                        # Output components
                        enhanced_status = gr.Markdown("*Ready to enhance your prompt.*")
                        enhanced_output = gr.Textbox(
                            label="Enhanced Prompt",
                            lines=8,
                            show_copy_button=True
                        )
                        
                        with gr.Row():
                            clear_enhance_btn = gr.Button("🗑️ Clear", variant="secondary")
                            copy_btn = gr.Button("📋 Copy to Clipboard", variant="secondary", interactive=False)
                
                # Update style description when style changes
                def update_style_info(style):
                    info = ENHANCEMENT_STYLES.get(style, {})
                    return f"**{info.get('name', style)}**: {info.get('description', '')}"
                
                style_select.change(
                    fn=update_style_info,
                    inputs=style_select,
                    outputs=style_description
                )
                
                # Clear function for enhancer
                def clear_enhancer():
                    return [
                        "",  # basic_prompt
                        "cinematic",  # style_select
                        "Bright and cheerful",  # mood_select
                        "",  # additional_details
                        "*Ready to enhance your prompt.*",  # enhanced_status
                        "",  # enhanced_output
                        gr.update(interactive=False)  # copy_btn
                    ]
                
                # Enhance button click
                enhance_btn.click(
                    fn=lambda: "*Enhancing your prompt...*",
                    inputs=None,
                    outputs=enhanced_status
                ).then(
                    fn=enhance_text_prompt,
                    inputs=[basic_prompt, style_select, mood_select, additional_details],
                    outputs=enhanced_output
                ).then(
                    fn=lambda x: [
                        "*Enhancement complete! Copy the enhanced prompt to use in your image generator.*",
                        gr.update(interactive=(x is not None and x != "" and not x.startswith("Error")))
                    ],
                    inputs=enhanced_output,
                    outputs=[enhanced_status, copy_btn]
                )
                
                clear_enhance_btn.click(
                    fn=clear_enhancer,
                    inputs=None,
                    outputs=[basic_prompt, style_select, mood_select, additional_details, 
                            enhanced_status, enhanced_output, copy_btn]
                )
                
                # Copy button uses JavaScript to copy to clipboard
                copy_btn.click(
                    fn=lambda x: x,
                    inputs=enhanced_output,
                    outputs=None,
                    js="(text) => {navigator.clipboard.writeText(text); return text;}"
                )
            
            with gr.TabItem("ℹ️ Help & Information"):
                gr.Markdown("## Analysis Style Descriptions")
                gr.Markdown("Choose one of the following analysis styles based on your needs:")
                for key, value in PROMPT_TYPES.items():
                    gr.Markdown(f"### {key.title()}")
                    gr.Markdown(value)
                
                gr.Markdown("### How to Use")
                gr.Markdown("""
                1. Upload an image using the upload button, webcam, or clipboard
                2. Select an analysis style or choose 'custom' to write your own prompt
                3. Click 'Analyze Image' to get results
                4. Use the 'Save Result' button to save the analysis to a text file
                5. Click 'Clear' to reset the interface and analyze another image
                """)
                
        # Clear button function
        def clear_interface():
            # Reset all input and output components with a list of values corresponding to the outputs
            return [
                None,                                                                    # Reset image_input
                "booru",                                                                 # Reset prompt_type to default
                "",                                                                      # Reset custom_prompt text
                gr.update(visible=False),                                                # Hide custom_prompt
                "*Ready for analysis. Upload an image and select an analysis style.*",   # Reset status_text
                "",                                                                      # Reset output_text
                gr.update(visible=False),                                                # Hide result_file
                gr.update(interactive=False)                                             # Disable save button
            ]
        
        # Save result to file function
        def save_result(result):
            if not result or result == "":
                return gr.update(visible=False)
            
            # Create a temporary file with the result
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as temp_file:
                temp_file.write(result)
                result_path = temp_file.name
            
            return gr.update(value=result_path, visible=True)
                
        # Set up the click events
        analyze_btn.click(
            fn=lambda: "*Analyzing image...*",
            inputs=None,
            outputs=status_text
        ).then(
            fn=process_image,
            inputs=[image_input, prompt_type, custom_prompt],
            outputs=[status_text, output_text]
        ).then(
            fn=lambda x: gr.update(interactive=(x is not None and x != "")),
            inputs=output_text,
            outputs=save_btn
        )
        
        clear_btn.click(
            fn=clear_interface,
            inputs=None,
            outputs=[image_input, prompt_type, custom_prompt, custom_prompt, status_text, output_text, result_file, save_btn]
        )
        
        save_btn.click(
            fn=save_result,
            inputs=[output_text],
            outputs=[result_file]
        )
        
    return app


# Launch the Gradio app
if __name__ == "__main__":
    app = create_gradio_interface()
    # Get host and port from environment or use defaults
    host = os.environ.get("GRADIO_HOST", "127.0.0.1")
    port = int(os.environ.get("GRADIO_PORT", 7861))
    # Launch with the specified host and port
    app.launch(server_name=host, server_port=port)
