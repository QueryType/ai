import requests
import time
import os
from PIL import Image
from io import BytesIO
import json

# Load env file
from dotenv import load_dotenv
load_dotenv()

class BFLKontextGenerator:
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
    
    def generate_image(self, prompt, aspect_ratio="1:1", prompt_upsampling=False, 
                      safety_tolerance=2, seed=None):
        """
        Generate an image using BFL Kontext API
        
        Args:
            prompt (str): Text prompt for image generation
            aspect_ratio (str): Image aspect ratio in format "width:height" (default: "1:1")
                               Supported range: 3:7 to 7:3 (~1MP total)
            prompt_upsampling (bool): Whether to use prompt upsampling (default: False)
            safety_tolerance (int): Safety tolerance level 1-6 (default: 2)
            seed (int, optional): Random seed for reproducible results
        
        Returns:
            str: Path to the saved image file, or None if failed
        """
        print(f"Starting Kontext image generation...")
        print(f"Prompt: {prompt}")
        print(f"Aspect ratio: {aspect_ratio}")
        print(f"Prompt upsampling: {prompt_upsampling}")
        print(f"Safety tolerance: {safety_tolerance}")
        if seed:
            print(f"Seed: {seed}")
        
        # Step 1: Submit the generation request
        request_id = self._submit_request(prompt, aspect_ratio, prompt_upsampling, 
                                        safety_tolerance, seed)
        if not request_id:
            return None
        
        # Step 2: Poll for completion
        result = self._poll_for_result(request_id)
        if not result:
            return None
        
        # Step 3: Download and save the image
        image_path = self._download_and_save_image(result, prompt)
        return image_path
    
    def _submit_request(self, prompt, aspect_ratio, prompt_upsampling, safety_tolerance, seed):
        """Submit the image generation request to Kontext endpoint"""
        payload = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "prompt_upsampling": prompt_upsampling,
            "safety_tolerance": safety_tolerance
        }
        
        # Add seed if provided
        if seed is not None:
            payload["seed"] = seed
        
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
                    print("Image generation completed!")
                    return result.get("result")
                elif status == "Pending":
                    print(f"Still generating... (attempt {attempt + 1})")
                elif status == "Request not found":
                    print("Error: Request not found")
                    return None
                elif status == "Content Moderated":
                    print("Error: Content was moderated (blocked by safety filters)")
                    return None
                elif status == "Task Failed":
                    print("Error: Task failed during generation")
                    return None
                else:
                    print(f"Status: {status}")
                
                time.sleep(2)  # Wait 2 seconds before next poll
                attempt += 1
                
            except requests.exceptions.RequestException as e:
                print(f"Error polling for result: {e}")
                time.sleep(2)
                attempt += 1
        
        print("Timeout: Image generation took too long")
        return None
    
    def _download_and_save_image(self, result, prompt):
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
            filename = f"kontext_{safe_prompt}_{timestamp}.png"
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
    """Main function to run the Kontext image generator"""
    # Get API key from environment variable or prompt user
    api_key = os.getenv("BFL_API_KEY")
    if not api_key:
        api_key = input("Please enter your BFL API key: ").strip()
        if not api_key:
            print("Error: API key is required")
            return
    
    # Create generator instance
    generator = BFLKontextGenerator(api_key)
    
    print("BFL Kontext Image Generator")
    print("===========================")
    print("Using the new Kontext model for enhanced image generation")
    
    while True:
        # Get user input
        prompt = input("\nEnter your image prompt (or 'quit' to exit): ").strip()
        
        if prompt.lower() in ['quit', 'exit', 'q']:
            print("Goodbye!")
            break
        
        if not prompt:
            print("Please enter a valid prompt")
            continue
        
        # Get aspect ratio
        print("\nAspect ratio options (width:height):")
        print("- 7:3 (ultra-wide)")
        print("- 16:9 (widescreen)")  
        print("- 4:3 (standard)")
        print("- 1:1 (square)")
        print("- 3:4 (portrait)")
        print("- 9:16 (mobile portrait)")
        print("- 3:7 (tall portrait)")
        print("- Or enter custom ratio within range 3:7 to 7:3")
        print("- Supported range: 3:7 to 7:3 (all outputs are ~1MP total)")
        
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
                
                # Check if within supported range (3:7 to 7:3)
                ratio_value = width_ratio / height_ratio
                min_ratio = 3 / 7  # 3:7 = 0.429
                max_ratio = 7 / 3  # 7:3 = 2.333
                
                if ratio_value < min_ratio or ratio_value > max_ratio:
                    print(f"Warning: Aspect ratio {aspect_ratio_input} is outside the supported range (3:7 to 7:3)")
                    print("Using default 1:1")
                    aspect_ratio = "1:1"
                else:
                    aspect_ratio = aspect_ratio_input
                    
            except (ValueError, IndexError):
                print("Invalid aspect ratio format. Using default 1:1")
                aspect_ratio = "1:1"
        
        # Get optional parameters
        upsampling_input = input("Enable prompt upsampling? (y/N): ").strip().lower()
        prompt_upsampling = upsampling_input in ['y', 'yes']
        
        try:
            safety_input = input("Safety tolerance (0 (strictest) - 6 (relaxed), default 2): ").strip()
            safety_tolerance = int(safety_input) if safety_input else 2
            safety_tolerance = max(0, min(6, safety_tolerance))  # Clamp to valid range
        except ValueError:
            safety_tolerance = 2
        
        try:
            seed_input = input("Random seed (optional, press Enter to skip): ").strip()
            seed = int(seed_input) if seed_input else None
        except ValueError:
            seed = None
        
        # Generate image
        print("\n" + "="*50)
        image_path = generator.generate_image(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            prompt_upsampling=prompt_upsampling,
            safety_tolerance=safety_tolerance,
            seed=seed
        )
        
        if image_path:
            print(f"\n✅ Success! Image saved to: {image_path}")
        else:
            print("\n❌ Failed to generate image")
        
        print("="*50)

if __name__ == "__main__":
    main()
