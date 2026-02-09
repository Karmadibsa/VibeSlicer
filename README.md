# VibeSlicer Studio

VibeSlicer Studio is an advanced AI-powered video editor designed to streamline your content creation workflow. It uses Voice Activity Detection (silence removal) and automatic speech transcription to help you edit videos 10x faster.

## Features

-   **Automatic Silence Removal**: Detects and removes dead air from your recordings.
-   **AI Transcription**: Automatically transcribes your video using OpenAI's Whisper (running locally).
-   **Subtitle Generation**: Creates accurate subtitles that you can burn directly into the video.
-   **Text-Based Editing**: Edit your video by double-clicking on the transcribed text segments.
-   **Range Selection (Shift+Click)**: Easily select and deactivate multiple segments at once.
-   **Precision Cutting (Alt+Click)**: Split any segment on the timeline with frame-perfect accuracy.
-   **Music Mixing**: Add background music with auto-ducking (volume lowers when you speak).
-   **Intro Title**: Add a quick intro title over a blurred background freeze-frame.
-   **Customizable Subtitles**: Change font size, color, and vertical position with a live preview.

## Installation

1.  **Install Python 3.10 or 3.11**.
2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Install FFmpeg**: Ensure `ffmpeg` is in your system PATH.
4.  **Install NVIDIA Libraries (for GPU Acceleration)**:
    ```bash
    pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
    ```
    *Note: This is critical for fast transcription. Without it, the app will run on CPU and be very slow.*

## Usage

1.  **Launch the Studio**:
    Run the provided batch file:
    ```bash
    start_vibeslicer_studio.bat
    ```
    Or run via python:
    ```bash
    python vibe_qt.py
    ```

2.  **Workflow**:
    *   **Import**: Click "+" to add your video file(s).
    *   **Analyze**: Click "Démarrer le Studio". The AI will process the audio.
    *   **Edit**:
        *   **Red segments** are silence (removed). **Green segments** are speech (kept).
        *   **Toggle**: Click a segment to enable/disable it.
        *   **Range**: Shift+Click to toggle a range of segments.
        *   **Edit Text**: Double-click a green segment in the list to correct the subtitle text if needed.
        *   **Split**: Alt+Click on the timeline (blue bar) to cut a segment in two.
    *   **Export**:
        *   Set your **Intro Title** (optional).
        *   Adjust **Subtitle Size** and **Position** (slider).
        *   Choose **Background Music**.
        *   Click **TERMINER ->** to render the final video.

## Troubleshooting

-   **"CUDA Error" / Slow Analysis**:
    Ensure you have an NVIDIA GPU and have installed the required libraries (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`). The app attempts to auto-fix missing paths on launch.
-   **Interface Closes Unexpectedly**:
    Check the terminal output for error messages. Usually indicates a memory issue or missing library.

## Credits

Developed by **Antigravity**. Powered by `faster-whisper`, `PyQt6`, and `ffmpeg`.
