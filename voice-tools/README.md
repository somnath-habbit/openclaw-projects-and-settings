# Voice-to-Text for Linux (Whisper)

This tool allows you to record your voice and convert it to text using OpenAI's Whisper model.
It is designed to be a robust alternative to `hyprflow` for GNOME/Wayland environments.

## 1. Installation

The AI model requires Python libraries (PyTorch). This is a large download (~1GB).
Please run this command in your terminal:

```bash
pip install --user openai-whisper soundfile numpy llvmlite
```
*(If you don't have pip, install it with `sudo apt install python3-pip`)*

You also need these system tools for audio recording and clipboard access:
```bash
sudo apt install wl-clipboard libnotify-bin zenity ffmpeg
```

## 2. Usage

Run the script:
```bash
~/voice-tools/voice-type-gnome.sh
```

- A dialog will appear saying **"Recording..."**. Speak your text.
- Click **OK** (or press Enter) to stop recording.
- Wait a moment for transcription.
- The text will be shown and copied to your clipboard.

## 3. Keyboard Shortcut (Recommended)

To use this efficiently, bind it to a key (like `Super+V`):

1.  Open **Settings** > **Keyboard** > **View and Customize Shortcuts**.
2.  Select **Custom Shortcuts**.
3.  Add new:
    - **Name**: Voice Type
    - **Command**: `/home/somnath/.openclaw/workspace/voice-tools/voice-type-gnome.sh`
    - **Shortcut**: `Super+V`

## Troubleshooting

-   **First Run**: The first time you use it, it will download the Whisper language model (~150MB). This happens automatically but might take a minute.
-   **No Clipboard**: If text isn't pasting, ensure `wl-clipboard` is installed.
