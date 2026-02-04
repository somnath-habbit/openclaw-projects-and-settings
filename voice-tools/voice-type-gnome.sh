#!/bin/bash

# Configuration
AUDIO_FILE="/tmp/voice_typing.wav"
WORKSPACE_DIR="/home/somnath/.openclaw/workspace"
DB_PATH="$WORKSPACE_DIR/Auto_job_application/data/autobot.db"
TRANSCRIPT_SCRIPT="$WORKSPACE_DIR/voice-tools/transcribe.py"
LOCK_FILE="/tmp/ultron_voice.lock"

# --- Logic ---

if [ -f "$LOCK_FILE" ]; then
    # 1. STOP RECORDING
    REC_PID=$(cat "$LOCK_FILE")
    kill $REC_PID
    rm "$LOCK_FILE"
    
    notify-send "Ultron Voice" "Processing..." -i microphone-sensitivity-high-symbolic
    
    # 2. TRANSCRIBE
    TEXT=$(python3 "$TRANSCRIPT_SCRIPT" "$AUDIO_FILE")
    
    if [[ -z "$TEXT" || "$TEXT" == Error* ]]; then
        notify-send "Ultron Voice" "Error: $TEXT"
        exit 1
    fi

    # 3. CLIPBOARD & PASTE
    echo -n "$TEXT" | wl-copy
    
    # Attempt auto-paste using common Wayland tools if present
    if command -v wtype >/dev/null; then
        wtype "$TEXT"
    elif command -v ydotool >/dev/null; then
        ydotool type "$TEXT"
    fi

    # 4. LOG TO DB
    python3 -c "import sqlite3; conn = sqlite3.connect('$DB_PATH'); conn.cursor().execute('INSERT INTO voice_logs (transcription) VALUES (?)', (\"$TEXT\",)); conn.commit(); conn.close();"

    notify-send "Ultron Voice" "Pasted: $TEXT"
    rm "$AUDIO_FILE"
else
    # 1. START RECORDING
    pw-record --format=s16 --rate=16000 --channels=1 "$AUDIO_FILE" &
    echo $! > "$LOCK_FILE"
    notify-send "Ultron Voice" "Listening... Press shortcut again to stop." -i microphone-sensitivity-muted-symbolic -t 2000
fi
