import os
from dotenv import load_dotenv, find_dotenv
from huggingface_hub import InferenceClient
import gradio as gr

# Load Hugging Face token from .env
load_dotenv(find_dotenv())
hf_token = os.getenv("HF_TOKEN")

# Define available models
models = {
    "Llama-3.3-70B-Instruct": "meta-llama/llama-3.3-70B-instruct",
    "QwQ-32B-Preview":"Qwen/QwQ-32B-Preview",
    "Qwen2.5-Coder-32B-Instruct": "qwen/qwen2.5-coder-32B-instruct",
    "Mistral-Nemo-Instruct-2407": "mistralai/Mistral-Nemo-Instruct-2407",
    "Hermes-3-Llama-3.2-3B":"NousResearch/Hermes-3-Llama-3.2-3B",
    "Phi-3-mini-4k-instruct": "microsoft/phi-3-mini-4k-instruct"
}

# Initialize the InferenceClient with a selected model
def get_inference_client(selected_model):
    return InferenceClient(
        models[selected_model],
        token=hf_token,
    )

# Function to get a response from the chatbot
def get_response(user_input, history, selected_model, system_prompt, temperature, max_tokens, top_p):
    client = get_inference_client(selected_model)
    
    # Add system message, if not empty
    if (system_prompt != ""):
        messages = [{"role": "system", "content": system_prompt}]
    
    # Include previous conversation history
    for h in history:
        messages.append({"role": h['role'], "content": h['content']})
    
    # Add the current user input to the messages
    messages.append({"role": "user", "content": user_input})
    
    # Get response from the model
    response = client.chat_completion(
        messages, 
        max_tokens=max_tokens, 
        temperature=temperature, 
        top_p=top_p,
    )
    
    bot_response = response.choices[0].message.content
    history.append({"role": "user", "content": user_input})
    history.append({"role": "assistant", "content": bot_response})
    
    return history

# Gradio interface
with gr.Blocks() as demo:
    with gr.Row():
        with gr.Column(scale=2):
            # Set the type to 'messages' to avoid the deprecation warning
            chatbot = gr.Chatbot(type="messages")
            with gr.Row():
                user_input = gr.Textbox(show_label=False, placeholder="Enter your message...")
                send_button = gr.Button("Send")
        with gr.Column(scale=1):
            with gr.Accordion("Settings", open=False):
                # Model selection
                selected_model = gr.Dropdown(choices=list(models.keys()), label="Select Model", value="Llama-3.3-70B-Instruct")
                
                # Chat settings
                system_prompt = gr.Textbox(value="You are a friendly and open-minded chatbot.", label="System Prompt", lines=5)
                temperature = gr.Slider(minimum=0.0, maximum=1.0, step=0.1, value=0.7, label="Temperature")
                max_tokens = gr.Slider(minimum=10, maximum=8192, step=10, value=250, label="Max Tokens")
                top_p = gr.Slider(minimum=0.0, maximum=1.0, step=0.1, value=0.9, label="Top-p")
    
    # Chatbot interaction
    def submit_message(user_input, history, selected_model, system_prompt, temperature, max_tokens, top_p):
        # Get updated history including user input and bot response
        history = get_response(user_input, history, selected_model, system_prompt, temperature, max_tokens, top_p)
        return "", history
    
    # Set up the send button click functionality
    send_button.click(
        submit_message, 
        [user_input, chatbot, selected_model, system_prompt, temperature, max_tokens, top_p], 
        [user_input, chatbot]
    )
    
    # Trigger sending message when Enter key is pressed
    user_input.submit(
        submit_message, 
        [user_input, chatbot, selected_model, system_prompt, temperature, max_tokens, top_p], 
        [user_input, chatbot]
    )

# Launch the Gradio interface
demo.launch()
