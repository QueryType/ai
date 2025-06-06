import gradio as gr
import requests
import base64
import os
from pathlib import Path
import tempfile
import numpy as np
import io
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Maximum allowed input text length
MAX_TEXT_LENGTH = 4000

# Language mapping with display names
LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "ml": "Malayalam",
    "mr": "Marathi",
    "gu": "Gujarati",
    "kn": "Kannada"
}

def generate_audio(input_text, input_language, input_speaker):
    """
    Generate audio from text using Krutrim TTS API
    """
    # Check if text exceeds the character limit
    if len(input_text) > MAX_TEXT_LENGTH:
        return None, f"Error: Input text exceeds the maximum limit of {MAX_TEXT_LENGTH} characters. Your text has {len(input_text)} characters."
    
    # Get API key from environment variable
    api_key = os.getenv("KRUTRIM_API_KEY")
    if not api_key:
        return None, "Error: KRUTRIM_API_KEY environment variable not found. Please check your .env file."
        
    url = "https://cloud.olakrutrim.com/v1/audio/generations/krutrim-tts"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "modelName": "tts",
        "input_text": input_text,
        "input_language": input_language,
        "input_speaker": input_speaker
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()  # Raise an error for HTTP failure codes

        result = response.json()
        base64_audio = result["output"]
        
        audio_data = base64.b64decode(base64_audio)
        
        # Save to a temporary file for download option
        temp_dir = Path(tempfile.gettempdir())
        output_path = temp_dir / "krutrim_output.wav"
        
        with open(output_path, "wb") as f:
            f.write(audio_data)
        
        # Convert to format suitable for browser playback
        try:
            # Convert WAV data to numpy array for Gradio's audio component
            audio_np = np.frombuffer(audio_data, dtype=np.int16)
            # Standard sample rate for most audio
            sample_rate = 16000  # Adjust this if your API returns a different sample rate
            
            return (sample_rate, audio_np), "Audio generated successfully! Click the play button to listen."
        except Exception as e:
            # Fallback to file path if conversion fails
            return str(output_path), f"Audio generated but playback in browser might not work. You can download the file. Error: {e}"
            
    except requests.exceptions.RequestException as e:
        return None, f"Error: {e}"

# Create Gradio interface
with gr.Blocks(title="Krutrim Text-to-Speech") as demo:
    gr.Markdown("# Krutrim Text-to-Speech Generator")
    gr.Markdown("Enter your text below and get it converted to speech using Krutrim's TTS API.")
    
    with gr.Row():
        with gr.Column():
            text_input = gr.Textbox(label="Text to convert to speech", 
                                  placeholder="Type your text here (maximum 4000 characters)...",
                                  lines=5)
            language = gr.Dropdown(label="Language", 
                               choices=list(LANGUAGES.keys()), 
                               value="en")
            speaker = gr.Dropdown(label="Speaker", 
                               choices=["male", "female"], 
                               value="male")
            submit_btn = gr.Button("Generate Audio")
        
        with gr.Column():
            audio_output = gr.Audio(
                label="Generated Audio",
                type="numpy",  # Explicitly set to numpy for better browser compatibility
                autoplay=True,  # Auto play the audio when generated
                show_download_button=True,  # Show the download button for the audio
                waveform_options={"waveform_color": "blue", "waveform_progress_color": "red"},  # Customize waveform appearance
                format="wav"  # Specify output format
            )
            output_message = gr.Textbox(label="Status")
    
    submit_btn.click(
        fn=generate_audio,
        inputs=[text_input, language, speaker],
        outputs=[audio_output, output_message]
    )

if __name__ == "__main__":
    demo.launch()