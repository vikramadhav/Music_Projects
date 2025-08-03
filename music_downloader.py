"""
music_downloader.py
------------------
A threaded music downloader using yt-dlp. Downloads audio from YouTube URLs or playlists, sanitizes filenames, organizes files by genre, and enriches metadata using MP3MetaEnricher. Logs all actions and supports parallel downloads.

Classes:
    YdlLogger: Custom logger for yt-dlp output.
    SanitizeFilenamePP: Post-processor for filename sanitation.

Functions:
    setup_logging(): Configures logging for the application.
    map_genre(genre): Maps genre to one of five main genres.
    move_to_genre_folder(filepath): Moves MP3 to genre folder and enriches metadata.
    enrich_if_missing_metadata(filepath): Enriches MP3 metadata if missing.
    download_music(url, use_cookies=False): Downloads and processes a single URL or playlist.

Usage:
    python music_downloader.py

Environment Variables:
    None required, but uses cookies.txt and input.txt for URLs and authentication.
"""

import yt_dlp
import os
import re
import concurrent.futures
import logging
import threading
from yt_dlp.utils import DownloadError, ExtractorError
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from mp3_meta_enricher import MP3MetaEnricher

# --- Thread-Safe Logger Setup ---
def setup_logging():
    """Configures the logging system for thread-safe, verbose output.

    Logs will be written to 'download.log' and also output to the console.
    The log format includes timestamp, thread name, log level, and message.
    """
    log_formatter = logging.Formatter(
        '%(asctime)s - %(threadName)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Log to a file
    file_handler = logging.FileHandler('download.log', mode='w')
    file_handler.setFormatter(log_formatter)
    
    # Log to the console
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(log_formatter)
    
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

# --- Custom Logger for yt-dlp ---
class YdlLogger:
    """
    Custom logger for yt-dlp to integrate its output with the application's logging system.

    This class routes yt-dlp's internal log messages (debug, info, warning, error)
    to the Python `logging` module, allowing for centralized log management and
    thread-safe logging to both file and console.
    """
    def debug(self, msg):
        """Handles debug messages from yt-dlp.

        Args:
            msg (str): The debug message from yt-dlp.
        """
        if msg.startswith('[debug]'):
            pass
        else:
            self.info(msg)

    def info(self, msg):
        """Handles info messages from yt-dlp.

        Args:
            msg (str): The info message from yt-dlp.
        """
        logging.info(msg)

    def warning(self, msg):
        """Handles warning messages from yt-dlp.

        Args:
            msg (str): The warning message from yt-dlp.
        """
        logging.warning(msg)

    def error(self, msg):
        """Handles error messages from yt-dlp.

        Args:
            msg (str): The error message from yt-dlp.
        """
        logging.error(msg)

# --- Post-Processor for Sanitizing Filenames ---
class SanitizeFilenamePP(yt_dlp.postprocessor.common.PostProcessor):
    """
    PostProcessor to sanitize filenames by removing invalid characters and renaming the file.

    This ensures that downloaded files have names that are compatible with various
    file systems and avoid issues with special characters.
    """
    def run(self, info):
        """Executes the filename sanitization process.

        Args:
            info (dict): A dictionary containing information about the downloaded file,
                         including its filepath, title, and ID.

        Returns:
            tuple: A tuple containing an empty list (for compatibility with yt-dlp's
                   postprocessor API) and the modified info dictionary.
        """
        logging.info('Sanitizing file name...')
        filepath = info.get('filepath')
        if not filepath or not os.path.exists(filepath):
            logging.warning(f"File not found for sanitation: {filepath}")
            return [], info

        dirname = os.path.dirname(filepath)
        basename = os.path.basename(filepath)
        title = info.get('title', '')
        file_ext = filepath.split('.')[-1]

        sanitized_title = re.sub(r'[\\/:*?"<>|]+', '', title).strip()
        if not sanitized_title:
            sanitized_title = info.get('id', 'default_id')

        new_basename = f"{sanitized_title}.{file_ext}"
        new_filepath = os.path.join(dirname, new_basename)

        if filepath == new_filepath:
            logging.info(f'Filename is already sanitized: {basename}')
            return [], info

        logging.info(f'Renaming "{basename}" to "{new_basename}"')
        try:
            if os.path.exists(new_filepath):
                logging.warning(f'File "{new_basename}" already exists. Skipping download.')
                return [], info
            os.rename(filepath, new_filepath)
            info['filepath'] = new_filepath
        except OSError as e:
            logging.error(f'Error renaming file: {e}')

        return [], info

def map_genre(genre):
    """
    Maps a genre string to one of five main genres.

    Args:
        genre (str): The genre string.
    Returns:
        str: Mapped genre.
    """
    genre_map = {
        'pop': 'Pop',
        'rock': 'Rock',
        'electronic': 'Electronic',
        'edm': 'Electronic',
        'classical': 'Classical',
        'hip hop': 'Pop',
        'rap': 'Pop',
        'jazz': 'Other',
        'folk': 'Other',
        'country': 'Other',
        'metal': 'Rock',
        'indie': 'Rock',
        'dance': 'Electronic',
        'blues': 'Other',
        'reggae': 'Other',
        'soul': 'Other',
        'r&b': 'Pop',
        'soundtrack': 'Other',
        'other': 'Other',
    }
    if not genre:
        return 'Other'
    genre_lower = genre.lower()
    for key in genre_map:
        if key in genre_lower:
            return genre_map[key]
    return 'Other'

def move_to_genre_folder(filepath):
    """
    Moves the MP3 file to its mapped genre folder and enriches metadata if missing.

    Args:
        filepath (str): Path to the MP3 file.
    Returns:
        str: New file path after moving.
    """
    try:
        audio = MP3(filepath, ID3=EasyID3)
        genre = audio.get('genre', ['Other'])[0]
        mapped_genre = map_genre(genre)
        genre_folder = os.path.join('music', mapped_genre)
        os.makedirs(genre_folder, exist_ok=True)
        new_path = os.path.join(genre_folder, os.path.basename(filepath))
        if os.path.abspath(filepath) != os.path.abspath(new_path):
            os.rename(filepath, new_path)
            logging.info(f"Moved {filepath} to {new_path}")
            enrich_if_missing_metadata(new_path)
        else:
            enrich_if_missing_metadata(filepath)
        return new_path
    except Exception as e:
        logging.error(f"Error moving {filepath} to genre folder: {e}")
    return filepath

def enrich_if_missing_metadata(filepath):
    """
    Enriches MP3 metadata using MP3MetaEnricher if required tags are missing.

    Args:
        filepath (str): Path to the MP3 file.
    """
    try:
        audio = MP3(filepath, ID3=EasyID3)
        required_tags = ['artist', 'genre', 'title', 'album', 'date', 'tracknumber', 'composer', 'albumartist', 'discnumber', 'length', 'comment']
        missing = [k for k in required_tags if k not in audio]
        if missing:
            enricher = MP3MetaEnricher(os.path.dirname(filepath))
            enricher.enrich_file(filepath)
            logging.info(f"Enriched metadata for {filepath} using MP3MetaEnricher.")
    except Exception as e:
        logging.error(f"Error checking/enriching metadata for {filepath}: {e}")

# --- Download Function (executed by each thread) ---
def download_music(url, use_cookies=False):
    """
    Downloads and processes a single audio URL or a playlist.

    This function handles both single video URLs and playlist URLs. For playlists,
    it iterates through each video and attempts to download it. It gracefully
    skips videos that are private, geo-restricted, or otherwise unavailable
    without stopping the entire download process.

    Args:
        url (str): The URL of the video or playlist to download.
        use_cookies (bool, optional): Whether to use cookies for authentication.
                                      Defaults to False.

    Returns:
        str: A message indicating the success or failure of the download operation
             for the given URL or playlist.
    """
    thread_name = threading.current_thread().name
    logging.info(f"Task started for URL: {url}")

    os.makedirs('music/thumbnails', exist_ok=True)

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }, {
            'key': 'EmbedThumbnail',
        }],
        'writethumbnail': True,
        'keepvideo': False,  # Only keep mp3, not video
        'outtmpl': {
            'default': 'music/%(title)s.%(ext)s',
            'thumbnail': 'music/thumbnails/%(title)s.%(ext)s',
        },
        'ignoreerrors': True,  # Crucial for skipping unavailable videos in playlists
        'retries': 3,
        'logger': YdlLogger(),
        'verbose': True,
        'extract_flat': True, # Extract info without downloading for playlist
    }

    if use_cookies:
        ydl_opts['cookiefile'] = 'cookies.txt'
    else:
        ydl_opts['cookiefile'] = None

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.add_post_processor(SanitizeFilenamePP(), when='post_process')
            
            info_dict = ydl.extract_info(url, download=False) # Extract info first

            if '_type' in info_dict and info_dict['_type'] == 'playlist':
                logging.info(f"Processing playlist: {info_dict.get('title', url)}")
                video_urls = [entry['url'] for entry in info_dict['entries'] if entry and 'url' in entry]
                
                # Remove extract_flat for actual video download
                del ydl_opts['extract_flat'] 
                
                for video_url in video_urls:
                    try:
                        logging.info(f"Attempting to download video from playlist: {video_url}")
                        with yt_dlp.YoutubeDL(ydl_opts) as video_ydl:
                            video_ydl.add_post_processor(SanitizeFilenamePP(), when='post_process')
                            video_ydl.download([video_url])
                        # Find the downloaded file and move it
                        info = video_ydl.extract_info(video_url, download=False)
                        title = info.get('title', info.get('id', 'unknown'))
                        ext = info.get('ext', 'mp3')
                        filename = f"music/{title}.{ext}"
                        if os.path.exists(filename):
                            move_to_genre_folder(filename)
                            enrich_if_missing_metadata(filename)
                        logging.info(f"Successfully downloaded video: {video_url}")
                    except (DownloadError, ExtractorError) as e:
                        logging.warning(f"Skipping unavailable video {video_url} in playlist. Reason: {e}")
                    except Exception as e:
                        logging.error(f"An unexpected error occurred while downloading {video_url}: {e}")
                return f"Finished processing playlist {url}"
            else:
                # It's a single video, proceed with download
                del ydl_opts['extract_flat']
                with yt_dlp.YoutubeDL(ydl_opts) as single_ydl:
                    single_ydl.add_post_processor(SanitizeFilenamePP(), when='post_process')
                    single_ydl.download([url])
                # Find the downloaded file and move it
                # Try to infer filename from yt-dlp output template
                info = ydl.extract_info(url, download=False)
                title = info.get('title', info.get('id', 'unknown'))
                ext = info.get('ext', 'mp3')
                filename = f"music/{title}.{ext}"
                if os.path.exists(filename):
                    move_to_genre_folder(filename)
                    enrich_if_missing_metadata(filename)
                return f"Successfully downloaded {url}"

    except (DownloadError, ExtractorError) as e:
        logging.warning(f"Skipping unavailable URL {url}. Reason: {e}")
        return f"Skipped {url} due to unavailability."
    except Exception as e:
        logging.error(f"An unexpected error occurred while processing {url}: {e}")
        return f"Failed to process {url}. Error: {e}"

# --- Main Execution Block ---
if __name__ == "__main__":
    """Main execution block of the script.

    This block sets up logging, reads URLs from 'input.txt', determines whether
    to use cookies for authentication, and then initiates parallel downloads
    of music using a ThreadPoolExecutor. It processes both single video URLs
    and playlist URLs, handling exceptions for unavailable videos.
    """
    setup_logging()
    CONCURRENCY_LEVEL = 4
    input_file = 'input.txt'
    cookie_file = 'cookies.txt'

    if not os.path.exists(input_file):
        logging.error(f"{input_file} not found. Please create it and add URLs.")
        exit()

    use_cookies = os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 0
    if use_cookies:
        logging.info(f"'{cookie_file}' found. Will use for authentication.")
    else:
        logging.warning(f"'{cookie_file}' not found. Private videos/playlists may fail.")

    with open(input_file, 'r') as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        logging.info("No URLs found in input.txt.")
        exit()

    logging.info(f"Found {len(urls)} URLs. Starting download with {CONCURRENCY_LEVEL} parallel workers...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY_LEVEL, thread_name_prefix='Downloader') as executor:
        future_to_url = {executor.submit(download_music, url, use_cookies): url for url in urls}

        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                result = future.result()
                logging.info(f"Result for {url}: {result}")
            except Exception as exc:
                logging.error(f'{url} generated an exception: {exc}')

    logging.info("All download tasks have been processed! ✨")