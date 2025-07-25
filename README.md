# YouTube Music Downloader

This script downloads music from YouTube videos and playlists.

## Prerequisites

- Python 3
- `yt-dlp`
- `ffmpeg`

## Installation

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/your-username/youtube-music-downloader.git
    cd youtube-music-downloader
    ```

2.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

3.  **Install FFmpeg:**

    - **macOS (using Homebrew):**
      ```bash
      brew install ffmpeg
      ```
    - **Windows (using Chocolatey):**
      ```bash
      choco install ffmpeg
      ```
    - **Linux (using apt):**
      ```bash
      sudo apt update
      sudo apt install ffmpeg
      ```

## Usage

To download a single song or a playlist, run the script with the YouTube URL as an argument:

```bash
python music_downloader.py <YOUTUBE_URL>
```

### Examples

-   **Single video:**

    ```bash
    python music_downloader.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ```

-   **Playlist:**

    ```bash
    python music_downloader.py "https://www.youtube.com/playlist?list=PL_your_playlist_id"
    ```

## How It Works

This script uses the `yt-dlp` library to extract the audio from YouTube videos. It is configured to:

-   Download the best quality audio.
-   Convert the audio to MP3 format.
-   Save the files with the video title as the filename.
-   Ignore errors in playlists and continue downloading other videos.

Enjoy your music! 🎶
