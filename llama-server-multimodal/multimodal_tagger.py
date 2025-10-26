import base64
import os
import glob
import argparse
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Define different prompt types
PROMPT_TYPES = {
    "simple": "You are expert in image description for training image generation models. Please describe this image. Focus on the main subject of the image. Describe the physical build and figure if the subject is a person. Include background information too. Do not include any irrelevant tags. These will be used to train a model to generate images from text. Please do not include any other text in the response.",
    "booru": "You are expert in Booru tagging. Please tag this image. Focus on the main subject of the image. Describe tags for physical structure if the subject is a person. Do not include any irrelevant tags. The tags should be separated by commas. These will be used to train a model to generate images from text. Please do not include any other text in the response.",
    "nsfwclassifier": "You are an expert in content classification. Please classify this image for content appropriateness and provide a general description including the subject matter and context. Focus on overall composition and themes rather than explicit details. Respond in Markdown format.",
    "artistic" : "You are an expert art critic with keen attention to detail. Analyze this image from an artistic perspective. First categorize the image by type (nature, portrait, abstract, etc.), then focus on the central theme. Provide a detailed analysis covering composition, color theory, lighting, style, and artistic techniques used. Respond in Markdown format with professional art criticism.",
    "satmet" : "You are an expert weather analyst. You are provided with a forecast of the weather for the next few days. The image will contain, the location, date and trends of the rainfall, temperature and humidity. Based on the image, please provide a detailed analysis of the weather forecast in the image."
}

# Get custom base URL from environment variables, with fallback to default
base_url = os.environ.get("OPENAI_API_BASE_URL")

# Initialize the OpenAI client once at module level
client = OpenAI(base_url=base_url) if base_url else OpenAI()


def encode_image(image_path):
    """
    Encode an image to base64 string
    
    Args:
        image_path (str): Path to the image file
        
    Returns:
        str: Base64 encoded image string
    """
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def query_multimodal_model(prompt, image_path, model="gpt-4.1"):
    """
    Query a multimodal model with text and image
    
    Args:
        prompt (str): Text prompt to send to the model
        image_path (str): Path to the image file
        model (str): Model identifier
        
    Returns:
        str: Model response text
    """
    # Encode the image
    base64_image = encode_image(image_path)
    
    # Make the API call using the global client
    response = client.chat.completions.create(
        model=model,
        max_tokens=2000,
        messages=[{
                "role": "user",
                "content": [
                    { "type": "text", "text": prompt },
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


def save_output_to_file(image_path, output_text):
    """
    Save the model's output to a text file with the same name as the image
    
    Args:
        image_path (str): Path to the image file
        output_text (str): Text to save to file
    """
    # Get the filename without extension
    path = Path(image_path)
    output_file = path.with_suffix('.txt')
    
    # Save the output to a text file
    with open(output_file, 'w') as f:
        f.write(output_text)
    
    print(f"Output for {path.name} saved to {output_file}")


def process_images_in_folder(folder_path="pics", prompt="What's in this image?"):
    """
    Process all images in the specified folder and save outputs to text files
    
    Args:
        folder_path (str): Path to the folder containing images
        prompt (str): Text prompt to send to the model
    """
    # Get list of image files
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    image_files = []
    
    for ext in image_extensions:
        image_files.extend(glob.glob(f"{folder_path}/*{ext}"))
        image_files.extend(glob.glob(f"{folder_path}/*{ext.upper()}"))
    
    if not image_files:
        print(f"No image files found in folder: {folder_path}")
        return
    
    print(f"Found {len(image_files)} image(s) to process")
    
    # Process each image
    for image_path in image_files:
        print(f"Processing image: {image_path}")
        try:
            # Get response from model
            response_text = query_multimodal_model(prompt, image_path)
            
            print(f"Response: {response_text}")

            # Save output to file
            save_output_to_file(image_path, response_text)
            
        except Exception as e:
            print(f"Error processing {image_path}: {str(e)}")


def main():
    """
    Main function to analyze images with various multimodal analysis styles
    """
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Analyze images with various multimodal analysis styles")
    parser.add_argument("--tagtype", choices=list(PROMPT_TYPES.keys()), default="booru",
                        help="Type of analysis/tagging style to use: " + ", ".join(PROMPT_TYPES.keys()))
    parser.add_argument("--folder", default=os.environ.get("IMAGES_FOLDER", "pics"),
                        help="Folder containing images to process")
    
    # Parse command-line arguments
    args = parser.parse_args()
    folder_path = args.folder
    tag_type = args.tagtype
    
    # Ensure the folder exists
    if not os.path.isdir(folder_path):
        print(f"Error: Folder not found: {folder_path}")
        print("Please create the folder or set the correct path using --folder argument or IMAGES_FOLDER environment variable")
        return
    
    # Get prompt based on tag type
    prompt = PROMPT_TYPES.get(tag_type)
    print(f"Using {tag_type} analysis style")
    
    # Process all images in the folder
    process_images_in_folder(folder_path, prompt)


if __name__ == "__main__":
    main()