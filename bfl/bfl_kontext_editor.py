import requests
import time
import os
from PIL import Image
from io import BytesIO
import json
import base64

# Load env file
from dotenv import load_dotenv
load_dotenv()

class BFLKontextEditor:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.us1.bfl.ai/v1"
        self.headers = {
            "x-key": self.api_key,
            "Content-Type": "application/json"
        }
        
        # Create output directory if it doesn't exist
        self.output_dir = "output"
        os.makedirs(self.output_dir, exist_ok=True)
    
    def encode_image_to_base64(self, image_path):
        """
        Encode an image file to base64 string
        
        Args:
            image_path (str): Path to the image file
            
        Returns:
            str: Base64 encoded image string, or None if failed
        """
        try:
            with open(image_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                return encoded_string
        except Exception as e:
            print(f"Error encoding image: {e}")
            return None
    
    def generate_or_edit_image(self, prompt, input_image_path=None, aspect_ratio=None, 
                              prompt_upsampling=False, safety_tolerance=2, seed=None,
                              output_format="png", webhook_url=None, webhook_secret=None):
        """
        Generate a new image or edit an existing image using BFL Kontext API
        
        Args:
            prompt (str): Text prompt for image generation/editing
            input_image_path (str, optional): Path to input image for editing. If None, generates new image
            aspect_ratio (str, optional): Image aspect ratio in format "width:height" (e.g., "16:9")
                                        Only used for generation. Ignored when editing (input_image provided).
                                        Supported range: 21:9 to 9:21. Default: "1:1" for generation.
            prompt_upsampling (bool): Whether to use prompt upsampling (default: False)
            safety_tolerance (int): Safety tolerance level 0-2 for editing, 0-6 for generation (default: 2)
            seed (int, optional): Random seed for reproducible results
            output_format (str): Output format - "png" or "jpeg" (default: "png")
            webhook_url (str, optional): Webhook URL for async notifications
            webhook_secret (str, optional): Webhook secret for verification
        
        Returns:
            str: Path to the saved image file, or None if failed
        """
        if input_image_path:
            print(f"Starting Kontext image editing...")
            print(f"Input image: {input_image_path}")
            print("Note: Output dimensions will match input image")
        else:
            print(f"Starting Kontext image generation...")
            # Set default aspect ratio for generation if not provided
            if not aspect_ratio:
                aspect_ratio = "1:1"
        
        print(f"Prompt: {prompt}")
        if not input_image_path and aspect_ratio:
            print(f"Aspect ratio: {aspect_ratio}")
        print(f"Prompt upsampling: {prompt_upsampling}")
        print(f"Safety tolerance: {safety_tolerance}")
        print(f"Output format: {output_format}")
        if seed:
            print(f"Seed: {seed}")
        
        # Step 1: Submit the generation/editing request
        if input_image_path:
            # For editing, don't pass aspect_ratio at all
            request_id = self._submit_request(
                prompt=prompt,
                input_image_path=input_image_path,
                prompt_upsampling=prompt_upsampling,
                safety_tolerance=safety_tolerance,
                seed=seed,
                output_format=output_format,
                webhook_url=webhook_url,
                webhook_secret=webhook_secret
            )
        else:
            # For generation, pass aspect_ratio
            request_id = self._submit_request(
                prompt=prompt,
                input_image_path=input_image_path,
                aspect_ratio=aspect_ratio,
                prompt_upsampling=prompt_upsampling,
                safety_tolerance=safety_tolerance,
                seed=seed,
                output_format=output_format,
                webhook_url=webhook_url,
                webhook_secret=webhook_secret
            )
        if not request_id:
            return None
        
        # Step 2: Poll for completion
        result = self._poll_for_result(request_id)
        if not result:
            return None
        
        # Step 3: Download and save the image
        image_path = self._download_and_save_image(result, prompt, input_image_path is not None)
        return image_path
    
    def _submit_request(self, prompt, input_image_path, prompt_upsampling, 
                       safety_tolerance, seed, output_format, webhook_url, webhook_secret, aspect_ratio=None):
        """Submit the image generation/editing request to Kontext endpoint"""
        payload = {
            "prompt": prompt,
            "output_format": output_format,
            "prompt_upsampling": prompt_upsampling,
            "safety_tolerance": safety_tolerance
        }
        
        # Add aspect ratio only for generation (when no input image)
        if not input_image_path and aspect_ratio:
            payload["aspect_ratio"] = aspect_ratio
        
        # Add input image if provided (for editing)
        if input_image_path:
            if not os.path.exists(input_image_path):
                print(f"Error: Input image file not found: {input_image_path}")
                return None
            
            encoded_image = self.encode_image_to_base64(input_image_path)
            if not encoded_image:
                print("Error: Failed to encode input image")
                return None
            
            payload["input_image"] = encoded_image
        
        # Add optional parameters if provided
        if seed is not None:
            payload["seed"] = seed
        
        if webhook_url:
            payload["webhook_url"] = webhook_url
            
        if webhook_secret:
            payload["webhook_secret"] = webhook_secret
        
        # Debug: Print payload details (remove this after testing)
        print(f"DEBUG: Sending payload with safety_tolerance={safety_tolerance} (type: {type(safety_tolerance).__name__})")
        
        try:
            response = requests.post(
                f"{self.base_url}/flux-kontext-pro",
                headers=self.headers,
                json=payload
            )
    
            response.raise_for_status()
            
            result = response.json()
            request_id = result.get("id")
            
            if request_id:
                print(f"Request submitted successfully. ID: {request_id}")
                return request_id
            else:
                print("Error: No request ID received")
                print(f"Response: {result}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"Error submitting request: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"Response status: {e.response.status_code}")
                
                # Enhanced error handling for 422 validation errors
                if e.response.status_code == 422:
                    try:
                        error_data = e.response.json()
                        print("=== 422 Validation Error Details ===")
                        if "detail" in error_data and isinstance(error_data["detail"], list):
                            for error in error_data["detail"]:
                                print(f"Location: {error.get('loc', 'Unknown')}")
                                print(f"Message: {error.get('msg', 'No message')}")
                                print(f"Type: {error.get('type', 'Unknown')}")
                                if 'input' in error:
                                    print(f"Input: {error['input']}")
                                print("-" * 30)
                        else:
                            print(f"Raw error response: {json.dumps(error_data, indent=2)}")
                    except json.JSONDecodeError:
                        print(f"Could not parse 422 error response: {e.response.text}")
                else:
                    print(f"Response text: {e.response.text}")
            return None
        except json.JSONDecodeError as e:
            print(f"Error parsing response: {e}")
            return None
    
    def _poll_for_result(self, request_id):
        """Poll the API until the image is ready"""
        print("Polling for result...")
        max_attempts = 300  # 5 minutes max
        attempt = 0
        
        while attempt < max_attempts:
            try:
                response = requests.get(
                    f"{self.base_url}/get_result?id={request_id}",
                    headers=self.headers
                )
                response.raise_for_status()
                
                result = response.json()
                status = result.get("status")
                
                if status == "Ready":
                    print("Image generation/editing completed!")
                    return result.get("result")
                elif status == "Pending":
                    print(f"Still processing... (attempt {attempt + 1})")
                elif status == "Request not found":
                    print("Error: Request not found")
                    return None
                elif status == "Content Moderated":
                    print("Error: Content was moderated (blocked by safety filters)")
                    return None
                elif status == "Task Failed":
                    print("Error: Task failed during processing")
                    return None
                else:
                    print(f"Status: {status}")
                
                time.sleep(2)  # Wait 2 seconds before next poll
                attempt += 1
                
            except requests.exceptions.RequestException as e:
                print(f"Error polling for result: {e}")
                time.sleep(2)
                attempt += 1
        
        print("Timeout: Image processing took too long")
        return None
    
    def _download_and_save_image(self, result, prompt, is_edit):
        """Download the image from signed URL and save it"""
        try:
            signed_url = result.get("sample")
            if not signed_url:
                print("Error: No signed URL in result")
                return None
            
            print("Downloading image...")
            
            # Download the image
            response = requests.get(signed_url, timeout=30)
            response.raise_for_status()
            
            # Convert to PIL Image
            image = Image.open(BytesIO(response.content))
            
            # Generate filename
            safe_prompt = "".join(c for c in prompt[:50] if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_prompt = safe_prompt.replace(' ', '_')
            timestamp = int(time.time())
            
            prefix = "edited" if is_edit else "generated"
            filename = f"kontext_{prefix}_{safe_prompt}_{timestamp}.png"
            filepath = os.path.join(self.output_dir, filename)
            
            # Save the image
            image.save(filepath, "PNG")
            
            print(f"Image saved successfully!")
            print(f"File path: {filepath}")
            print(f"Image size: {image.size}")
            
            return filepath
            
        except requests.exceptions.RequestException as e:
            print(f"Error downloading image: {e}")
            return None
        except Exception as e:
            print(f"Error saving image: {e}")
            return None

def main():
    """Main function to run the Kontext image generator/editor"""
    # Get API key from environment variable or prompt user
    api_key = os.getenv("BFL_API_KEY")
    if not api_key:
        api_key = input("Please enter your BFL API key: ").strip()
        if not api_key:
            print("Error: API key is required")
            return
    
    # Create generator instance
    editor = BFLKontextEditor(api_key)
    
    print("BFL Kontext Image Generator & Editor")
    print("====================================")
    print("Generate new images or edit existing ones using the Kontext model")
    
    while True:
        print("\nChoose mode:")
        print("1. Generate new image (text-to-image)")
        print("2. Edit existing image (image + text prompt)")
        print("3. Quit")
        
        mode_choice = input("Enter choice (1/2/3): ").strip()
        
        if mode_choice == "3" or mode_choice.lower() in ['quit', 'exit', 'q']:
            print("Goodbye!")
            break
        
        if mode_choice not in ['1', '2']:
            print("Invalid choice. Please enter 1, 2, or 3.")
            continue
        
        # Get user input
        prompt = input("\nEnter your image prompt (or 'quit' to exit): ").strip()
        
        if prompt.lower() in ['quit', 'exit', 'q']:
            print("Goodbye!")
            break
        
        if not prompt:
            print("Please enter a valid prompt")
            continue
        
        # Get input image path for editing mode
        input_image_path = None
        if mode_choice == "2":
            input_image_path = input("Enter path to input image: ").strip()
            if not input_image_path:
                print("Input image path is required for editing mode")
                continue
            
            if not os.path.exists(input_image_path):
                print(f"Error: File not found: {input_image_path}")
                continue
        
        # Get aspect ratio (only for generation mode)
        if mode_choice == "1":
            print("\nAspect ratio options (width:height):")
            print("- 21:9 (ultra-wide)")
            print("- 16:9 (widescreen)")  
            print("- 4:3 (standard)")
            print("- 1:1 (square)")
            print("- 3:4 (portrait)")
            print("- 9:16 (mobile portrait)")
            print("- 9:21 (tall portrait)")
            print("- Or enter custom ratio like '3:2', '5:4', etc.")
            
            aspect_ratio_input = input("Enter aspect ratio (default 1:1): ").strip()
            
            if not aspect_ratio_input:
                aspect_ratio = "1:1"
            else:
                # Validate aspect ratio format
                try:
                    parts = aspect_ratio_input.split(':')
                    if len(parts) != 2:
                        raise ValueError("Invalid format")
                    
                    width_ratio = float(parts[0])
                    height_ratio = float(parts[1])
                    
                    if width_ratio <= 0 or height_ratio <= 0:
                        raise ValueError("Ratios must be positive")
                    
                    # Check if within supported range (21:9 to 9:21)
                    ratio_value = width_ratio / height_ratio
                    min_ratio = 9 / 21  # 9:21 = 0.429
                    max_ratio = 21 / 9  # 21:9 = 2.333
                    
                    if ratio_value < min_ratio or ratio_value > max_ratio:
                        print(f"Warning: Aspect ratio {aspect_ratio_input} is outside the recommended range (21:9 to 9:21)")
                        print("Using default 1:1")
                        aspect_ratio = "1:1"
                    else:
                        aspect_ratio = aspect_ratio_input
                        
                except (ValueError, IndexError):
                    print("Invalid aspect ratio format. Using default 1:1")
                    aspect_ratio = "1:1"
        else:
            # For editing mode, aspect ratio is determined by input image
            aspect_ratio = "1:1"  # This will be ignored when input_image is provided
        
        # Get output format
        print("\nOutput format options:")
        print("- jpeg (smaller file size)")
        print("- png (higher quality, larger file size)")
        output_format_input = input("Enter output format (default jpeg): ").strip().lower()
        output_format = output_format_input if output_format_input in ['jpeg', 'png'] else 'jpeg'
        
        # Get optional parameters
        upsampling_input = input("Enable prompt upsampling? (y/N): ").strip().lower()
        prompt_upsampling = upsampling_input in ['y', 'yes']
        
        try:
            if mode_choice == "2":  # Editing mode
                safety_input = input("Safety tolerance (0 (strictest) - 2 (relaxed), default 2): ").strip()
                safety_tolerance = int(safety_input) if safety_input else 2
                safety_tolerance = max(0, min(2, safety_tolerance))  # Clamp to 0-2 for editing
            else:  # Generation mode
                safety_input = input("Safety tolerance (0 (strictest) - 6 (relaxed), default 2): ").strip()
                safety_tolerance = int(safety_input) if safety_input else 2
                safety_tolerance = max(0, min(6, safety_tolerance))  # Clamp to 0-6 for generation
        except ValueError:
            safety_tolerance = 2
        
        try:
            seed_input = input("Random seed (optional, press Enter to skip): ").strip()
            seed = int(seed_input) if seed_input else None
        except ValueError:
            seed = None
        
        # Generate or edit image
        print("\n" + "="*50)
        image_path = editor.generate_or_edit_image(
            prompt=prompt,
            input_image_path=input_image_path,
            aspect_ratio=aspect_ratio,
            prompt_upsampling=prompt_upsampling,
            safety_tolerance=safety_tolerance,
            seed=seed,
            output_format=output_format
        )
        
        if image_path:
            action = "edited" if input_image_path else "generated"
            print(f"\n✅ Success! Image {action} and saved to: {image_path}")
        else:
            print(f"\n❌ Failed to {'edit' if input_image_path else 'generate'} image")
        
        print("="*50)

if __name__ == "__main__":
    main()
