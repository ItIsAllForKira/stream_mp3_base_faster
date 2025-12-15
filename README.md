# Stream Recorder and Transcriber GUI

**Real-time audio stream recorder and speech-to-text transcriber** powered by [faster-whisper](https://github.com/SYSTRAN/faster-whisper).  
This desktop application captures live audio streams (e.g., news radio, online broadcasts) via FFmpeg, 
transcribes speech in real time using a local Whisper model, and logs both audio and text output.

> **Note**: This is a self-contained PySide6 GUI application designed for Windows (with `ffmpeg.exe` support),
> but can be adapted to other platforms.

---

## ✨ Features

- **Real-time transcription** of live audio streams (HLS, Icecast, HTTP, etc.)
- **Predefined stream presets** (BBC, CNN, Al Jazeera, VOA, Bloomberg, and more)
- **Manual URL input** for custom streams
- **Configurable recording duration** (1–30 minutes)
- **Adjustable audio chunk size** for latency/performance tuning
- **Live transcription display** with color-coded formatting
- **Automatic audio saving** as WAV → MP3 (192 kbps)
- **Usage logging** with stream name, action type, and duration
- **Model-on-demand loading**: Whisper `base` model (int8, CPU-only) loads only when needed
- **Listen-only mode**: transcribe without saving audio
<img width="1022" height="509" alt="stream" src="https://github.com/user-attachments/assets/7521393a-9a40-425d-b776-1950d27378a9" />

---

## 🧠 Model Details

- Uses **faster-whisper** with the `base` model (English-optimized)
- Runs **locally on CPU** (`int8` quantization for efficiency)
- Language is **locked to English** (with VAD filtering enabled)
- Model is **loaded once per session** and reused across recordings

---

## 📦 Requirements

- Python 3.8+
- Required packages:
  ```bash
  pip install faster-whisper pyside6 pyaudio pydub colorama requests numpy
  ```
- FFmpeg (bundled as `ffmpeg.exe` in frozen builds; otherwise must be in `PATH`)
- ~500 MB disk space for model cache (`~/.cache/huggingface/hub`)

---

## 🚀 Quick Start

1. **Clone or download** the project.
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt  # if you create one
   ```
3. **Run the application**:
   ```bash
   python stream.py
   ```
4. **Choose a stream** from the dropdown or enter a custom URL.
5. Set duration (1–30 min), optionally adjust chunk size, and click **Record**.

> The first run will download the Whisper `base` model (~150 MB).

---

## 📁 Output

- **Text**: displayed in real time; each new sentence appears in **red bold**, then turns **blue bold** after processing.
- **Audio**: saved as `StreamName_audio_YYYY-MM-DD_HH-MM-SS.wav` → auto-converted to `.mp3`.
- **Log**: `stream.log` in the app directory with entries like:  
  `2025-12-11 14:30:22 BBC - Record: 2:15`

---

## 🛠️ Configuration Options (UI)

| Control | Purpose |
|--------|--------|
| **Stream selector** | Choose from built-in stations or type a URL |
| **Duration (min)** | Max recording/transcription time |
| **Audio chunk size** | Controls block duration: 160000 = 5s, 320000 = 10s, ..., 1920000 = 60s |
| **Record button** | Start/stop recording + transcription + audio save |
| **Listen button** | Transcribe only (no file saved) |

---

## 📜 License

This project is for personal/educational use.  
Underlying components:
- `faster-whisper` — [MIT License](https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE)
- FFmpeg — [GPL/LGPL](https://ffmpeg.org/legal.html)
- PySide6 — [LGPL/GPL]

---

## 💡 Notes

- Designed for **stable, low-bandwidth English streams** (news, talk radio).
- Not optimized for noisy or multilingual content.
- Avoid very short chunk sizes (<5s) — may reduce transcription accuracy.
- On first launch, ensure internet access for model download and stream validation.

---

> Made with ❤️ using Python, faster-whisper, and PySide6.  
> Version: `V211125`

--- 
