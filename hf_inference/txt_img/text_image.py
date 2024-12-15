import os
from dotenv import load_dotenv, find_dotenv
from huggingface_hub import InferenceClient
import gradio as gr

load_dotenv(find_dotenv())
hf_token = os.getenv("HF_TOKEN")

headers ={
    "x-wait-for-model" : "true",
    "x-use-cache" : "true",
}

model="black-forest-labs/FLUX.1-schnell"

output_folder = "txt_img/output"
client = InferenceClient(model=model, headers=headers, token=hf_token)

# generate_image function
def generate_image(model, prompt, guidance, width, height, num_inference_steps, seed):
    print(f"""Generating image with following parameters: 
          Model: {model}, Prompt: {prompt}, Guidance Scale: {guidance}, Width: {width}, Height: {height},""")
    image = client.text_to_image(
        model=model,
        prompt=prompt,
        guidance_scale=guidance,
        height=height,
        width=width,
        num_inference_steps=num_inference_steps,
        seed=seed
    )
    return image

iface = gr.Interface(
    fn=generate_image,
    inputs=[
        gr.Textbox(label="Model", value=model),
        gr.Textbox(label="Prompt", lines=5, value="Astronaut floating in space"),
        gr.Slider(0, 10, step=0.1, label="Guidance Scale", value=0),
        gr.Slider(256, 2048, step=32, label="Width", value=768),
        gr.Slider(256, 2048, step=32, label="Height", value=1024),
        gr.Slider(1, 100, step=1, label="Number of Inference Steps", value=4),
        gr.Number(label="Seed", value=0)
    ],
    outputs=gr.Image(type="pil", format="png"),
    title="Text to Image Generation",
    description="Generate images from text prompts using the HF Inference API",
)

iface.launch()
