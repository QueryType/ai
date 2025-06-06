import gradio as gr
import os
from bfl_kontext_editor import BFLKontextEditor
from dotenv import load_dotenv
import tempfile
import shutil

# Load environment variables
load_dotenv()

class GradioKontextApp:
    def __init__(self):
        self.editor = None
        self.api_key = os.getenv("BFL_API_KEY")
    
    def initialize_editor(self, api_key):
        """Initialize the BFL Kontext Editor with API key"""
        if not api_key:
            return None, "❌ API key is required"
        
        try:
            self.editor = BFLKontextEditor(api_key)
            self.api_key = api_key
            return self.editor, "✅ API key validated successfully"
        except Exception as e:
            return None, f"❌ Error initializing editor: {str(e)}"
    
    def generate_image(self, prompt, aspect_ratio, prompt_upsampling, safety_tolerance, 
                      seed, output_format, api_key):
        """Generate a new image from text prompt"""
        if not self.editor or self.api_key != api_key:
            self.editor, status = self.initialize_editor(api_key)
            if not self.editor:
                return None, status
        
        if not prompt:
            return None, "❌ Please enter a prompt"
        
        try:
            # Convert seed to int if provided
            seed_int = int(seed) if seed else None
            
            # Clamp safety tolerance for generation mode (0-6)
            safety_tolerance = max(0, min(6, int(safety_tolerance)))
            
            image_path = self.editor.generate_or_edit_image(
                prompt=prompt,
                input_image_path=None,
                aspect_ratio=aspect_ratio,
                prompt_upsampling=prompt_upsampling,
                safety_tolerance=safety_tolerance,
                seed=seed_int,
                output_format=output_format
            )
            
            if image_path:
                return image_path, f"✅ Image generated successfully! Saved to: {image_path}"
            else:
                return None, "❌ Failed to generate image"
                
        except Exception as e:
            return None, f"❌ Error: {str(e)}"
    
    def edit_image(self, input_image, prompt, prompt_upsampling, safety_tolerance, 
                   seed, output_format, api_key):
        """Edit an existing image based on text prompt"""
        if not self.editor or self.api_key != api_key:
            self.editor, status = self.initialize_editor(api_key)
            if not self.editor:
                return None, status
        
        if not input_image:
            return None, "❌ Please upload an image"
        
        if not prompt:
            return None, "❌ Please enter an editing prompt"
        
        try:
            # Convert seed to int if provided
            seed_int = int(seed) if seed else None
            
            # Clamp safety tolerance for editing mode (0-2)
            safety_tolerance = max(0, min(2, int(safety_tolerance)))
            
            # Save uploaded image to temporary file
            temp_path = None
            if hasattr(input_image, 'name'):
                temp_path = input_image.name
            else:
                # Handle PIL Image or other formats
                temp_path = tempfile.mktemp(suffix='.png')
                if hasattr(input_image, 'save'):
                    input_image.save(temp_path)
                else:
                    shutil.copy(input_image, temp_path)
            
            image_path = self.editor.generate_or_edit_image(
                prompt=prompt,
                input_image_path=temp_path,
                prompt_upsampling=prompt_upsampling,
                safety_tolerance=safety_tolerance,
                seed=seed_int,
                output_format=output_format
            )
            
            # Clean up temporary file if we created one
            if temp_path and not hasattr(input_image, 'name'):
                try:
                    os.unlink(temp_path)
                except:
                    pass
            
            if image_path:
                return image_path, f"✅ Image edited successfully! Saved to: {image_path}"
            else:
                return None, "❌ Failed to edit image"
                
        except Exception as e:
            return None, f"❌ Error: {str(e)}"

# Initialize the app
app = GradioKontextApp()

# Custom CSS for orange theme
css = """
.gradio-container {
    font-family: 'Arial', sans-serif;
}

.tab-nav button {
    background: linear-gradient(135deg, #ff8c00, #ff6b00) !important;
    border: none !important;
    color: white !important;
    font-weight: bold !important;
}

.tab-nav button.selected {
    background: linear-gradient(135deg, #ff6b00, #ff4500) !important;
}

.btn-primary {
    background: linear-gradient(135deg, #ff8c00, #ff6b00) !important;
    border: none !important;
    color: white !important;
    font-weight: bold !important;
}

.btn-primary:hover {
    background: linear-gradient(135deg, #ff6b00, #ff4500) !important;
}

.progress {
    background: linear-gradient(90deg, #ffe4b5, #ff8c00) !important;
}

h1, h2, h3 {
    color: #ff6b00 !important;
}

.form input, .form textarea, .form select {
    border: 2px solid #ffb366 !important;
    border-radius: 8px !important;
}

.form input:focus, .form textarea:focus, .form select:focus {
    border-color: #ff6b00 !important;
    box-shadow: 0 0 0 3px rgba(255, 107, 0, 0.1) !important;
}
"""

# Create the Gradio interface
with gr.Blocks(css=css, title="BFL Kontext Generator & Editor", theme=gr.themes.Base()) as demo:
    gr.Markdown(
        """
        # 🎨 BFL Kontext Image Generator & Editor
        
        Create stunning images with AI or edit existing ones using the powerful Kontext model.
        """,
        elem_classes="header"
    )
    
    # API Key input (persistent across tabs) - Hidden but functional
    api_key_input = gr.Textbox(
        label="🔑 BFL API Key",
        type="password",
        value=app.api_key or "",
        placeholder="Enter your BFL API key...",
        info="Your API key will be remembered during this session",
        visible=False  # Hide the API key input
    )
    
    with gr.Tabs() as tabs:
        # Text-to-Image Generation Tab
        with gr.TabItem("🖼️ Generate Image", id=0):
            with gr.Row():
                with gr.Column(scale=1):
                    gen_prompt = gr.Textbox(
                        label="📝 Image Prompt",
                        placeholder="Describe the image you want to create...",
                        lines=3
                    )
                    
                    with gr.Row():
                        aspect_ratio = gr.Dropdown(
                            label="📐 Aspect Ratio",
                            choices=[
                                "1:1 (Square)",
                                "16:9 (Widescreen)",
                                "9:16 (Portrait)",
                                "4:3 (Standard)",
                                "3:4 (Portrait)",
                                "7:3 (Ultra-wide)",
                                "3:7 (Tall Portrait)"
                            ],
                            value="1:1 (Square)",
                            info="Supported range: 3:7 to 7:3 (~1MP total)"
                        )
                        
                        gen_output_format = gr.Dropdown(
                            label="💾 Output Format",
                            choices=["png", "jpeg"],
                            value="png"
                        )
                    
                    with gr.Row():
                        gen_prompt_upsampling = gr.Checkbox(
                            label="🔄 Prompt Upsampling",
                            value=False,
                            info="Enhance prompt for better results"
                        )
                        
                        gen_safety_tolerance = gr.Slider(
                            label="🛡️ Safety Tolerance",
                            minimum=0,
                            maximum=6,
                            value=2,
                            step=1,
                            info="0 = Strictest, 6 = Most Relaxed (generation mode)"
                        )
                    
                    gen_seed = gr.Textbox(
                        label="🎲 Seed (Optional)",
                        placeholder="Enter a number for reproducible results...",
                        info="Leave empty for random generation"
                    )
                    
                    gen_button = gr.Button(
                        "🚀 Generate Image",
                        variant="primary",
                        size="lg"
                    )
                
                with gr.Column(scale=1):
                    gen_output_image = gr.Image(
                        label="Generated Image",
                        type="filepath"
                    )
                    gen_status = gr.Textbox(
                        label="Status",
                        interactive=False,
                        lines=2
                    )
        
        # Image Editing Tab
        with gr.TabItem("✏️ Edit Image", id=1):
            with gr.Row():
                with gr.Column(scale=1):
                    edit_input_image = gr.Image(
                        label="📤 Upload Image to Edit",
                        type="filepath"
                    )
                    
                    edit_prompt = gr.Textbox(
                        label="📝 Editing Prompt",
                        placeholder="Describe how you want to modify the image...",
                        lines=3
                    )
                    
                    with gr.Row():
                        edit_output_format = gr.Dropdown(
                            label="💾 Output Format",
                            choices=["png", "jpeg"],
                            value="png"
                        )
                        
                        edit_prompt_upsampling = gr.Checkbox(
                            label="🔄 Prompt Upsampling",
                            value=False,
                            info="Enhance prompt for better results"
                        )
                    
                    with gr.Row():
                        edit_safety_tolerance = gr.Slider(
                            label="🛡️ Safety Tolerance",
                            minimum=0,
                            maximum=2,
                            value=2,
                            step=1,
                            info="0 = Strictest, 2 = Most Relaxed (editing mode)"
                        )
                        
                        edit_seed = gr.Textbox(
                            label="🎲 Seed (Optional)",
                            placeholder="Enter a number for reproducible results...",
                            info="Leave empty for random generation"
                        )
                    
                    edit_button = gr.Button(
                        "✨ Edit Image",
                        variant="primary",
                        size="lg"
                    )
                
                with gr.Column(scale=1):
                    edit_output_image = gr.Image(
                        label="Edited Image",
                        type="filepath"
                    )
                    edit_status = gr.Textbox(
                        label="Status",
                        interactive=False,
                        lines=2
                    )
    
    # Event handlers
    gen_button.click(
        fn=lambda prompt, ar, upsampling, safety, seed, format, api_key: app.generate_image(
            prompt, ar.split()[0] if ar else "1:1", upsampling, safety, seed, format, api_key
        ),
        inputs=[
            gen_prompt, aspect_ratio, gen_prompt_upsampling, gen_safety_tolerance,
            gen_seed, gen_output_format, api_key_input
        ],
        outputs=[gen_output_image, gen_status],
        show_progress=True
    )
    
    edit_button.click(
        fn=app.edit_image,
        inputs=[
            edit_input_image, edit_prompt, edit_prompt_upsampling, edit_safety_tolerance,
            edit_seed, edit_output_format, api_key_input
        ],
        outputs=[edit_output_image, edit_status],
        show_progress=True
    )
    
    # Footer
    gr.Markdown(
        """
        ---
        🔥 **Powered by BFL Kontext** | Made with ❤️ using Gradio
        
        💡 **Tips:**
        - Use descriptive prompts for better results
        - Try different aspect ratios for varied compositions
        - Enable prompt upsampling for enhanced quality
        - Use seeds to reproduce your favorite generations
        """,
        elem_classes="footer"
    )

if __name__ == "__main__":
    demo.launch(
        server_name="localhost",
        server_port=7860,
        share=False,
        debug=True,
        show_error=True
    )
