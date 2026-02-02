import whisper
import sys
import warnings

# Suppress warnings
warnings.filterwarnings("ignore")

def transcribe(audio_path, model_name="base"):
    try:
        model = whisper.load_model(model_name)
        result = model.transcribe(audio_path)
        return result["text"].strip()
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 transcribe.py <audio_file>")
        sys.exit(1)
    
    audio_file = sys.argv[1]
    text = transcribe(audio_file)
    print(text)
