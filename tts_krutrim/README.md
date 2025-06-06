# Krutrim Text-to-Speech Web App

A simple web application that uses the Krutrim TTS API to convert text to speech. Built with Gradio for an easy-to-use interface.

## Features

- Text-to-speech conversion using Krutrim's TTS API
- Support for multiple languages (English, Hindi)
- Choice of speaker voice (male, female)
- Secure API key handling
- Audio playback directly in the browser

## Installation

1. Clone this repository or download the files

2. Install the required dependencies:

```bash
pip install -r requirements.txt
```

## Usage

1. Run the application:

```bash
python app.py
```

2. Open your web browser and navigate to the URL shown in the terminal (typically http://127.0.0.1:7860)

3. Enter your Krutrim API key in the provided field

4. Type or paste the text you want to convert to speech

5. Select your preferred language and speaker voice

6. Click "Generate Audio" and wait for the audio to be generated

7. Play the audio directly in the browser or download it

## API Key

You need a valid Krutrim API key to use this application. The API key is sent securely with each request.

## Requirements

- Python 3.7+
- Gradio
- Requests

## Files

- `app.py`: Main application with Gradio interface
- `test.py`: Basic script for testing the Krutrim TTS API without Gradio
- `requirements.txt`: List of required Python packages

## Privacy Notice

This application processes text data and sends it to the Krutrim TTS API. Make sure you comply with relevant privacy regulations and Krutrim's terms of service when using this application.
