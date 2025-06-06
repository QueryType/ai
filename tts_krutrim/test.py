import requests
import base64

url = "https://cloud.olakrutrim.com/v1/audio/generations/krutrim-tts"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer YOUR_BEARER_TOKEN"
}
payload = {
    "modelName": "tts",
    "input_text": "From the beginning of the 19th century, the British East India Company's gradual expansion and consolidation of power brought a major change in taxation and agricultural policies. They were very good at it",
    "input_language": "en",
    "input_speaker": "male"
}

try:
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()  # Raise an error for HTTP failure codes

    x = response.json()
    base64_audio = x["output"]

    audio_data = base64.b64decode(base64_audio)
    
    with open("output_audio.wav", "wb") as f:
        f.write(audio_data)
    
    print("Audio file saved as output_audio.wav")
except requests.exceptions.RequestException as e:
    print(f"Error: {e}")