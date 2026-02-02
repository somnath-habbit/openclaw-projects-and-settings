#!/bin/bash

# Configuration
AUDIO_FILE="/tmp/voice_recording.wav"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRANSCRIPT_SCRIPT="$SCRIPT_DIR/transcribe.py"

# 1. Start Recording
# Using pw-record. running in background.
pw-record --format=s16 --rate=16000 --channels=1 "$AUDIO_FILE" &
REC_PID=$!

# 2. Show Dialog to Stop
zenity --info --title="Voice Typing" --text="Recording... Click OK to stop." --icon-name=microphone

# 3. Stop Recording
kill $REC_PID
wait $REC_PID 2>/dev/null

# 4. Notify Transcribing
zenity --notification --text="Transcribing..." --window-icon=info

# 5. Transcribe
# Check if python script exists
if [ ! -f "$TRANSCRIPT_SCRIPT" ]; then
    zenity --error --text="Error: transcribe.py not found at $TRANSCRIPT_SCRIPT"
    exit 1
fi

TEXT=$(python3 "$TRANSCRIPT_SCRIPT" "$AUDIO_FILE")

# 6. Show Result (and allow copy)
if command -v wl-copy >/dev/null; then
    echo -n "$TEXT" | wl-copy
    zenity --info --text="Text copied to clipboard:\n\n$TEXT" --title="Success"
elif command -v xclip >/dev/null; then
    echo -n "$TEXT" | xclip -selection clipboard
    zenity --info --text="Text copied to clipboard:\n\n$TEXT" --title="Success"
else
    # Fallback: Show text box
    echo "$TEXT" | zenity --text-info --title="Transcription Result" --editable --width=400 --height=300
fi

rm "$AUDIO_FILE"
