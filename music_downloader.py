import yt_dlp
import os
import re
import concurrent.futures
import logging
import threading

# --- Thread-Safe Logger Setup ---
def setup_logging():
    """Configures the logging system for thread-safe, verbose output."""
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
    """A custom logger to capture yt-dlp output and route it to our logger."""
    def debug(self, msg):
        if msg.startswith('[debug]'):
            pass
        else:
            self.info(msg)

    def info(self, msg):
        logging.info(msg)

    def warning(self, msg):
        logging.warning(msg)

    def error(self, msg):
        logging.error(msg)

# --- Post-Processor for Sanitizing Filenames ---
class SanitizeFilenamePP(yt_dlp.postprocessor.common.PostProcessor):
    def run(self, info):
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
                logging.warning(f'File "{new_basename}" already exists. Overwriting.')
                os.remove(new_filepath)
            os.rename(filepath, new_filepath)
            info['filepath'] = new_filepath
        except OSError as e:
            logging.error(f'Error renaming file: {e}')

        return [], info

# --- Download Function (executed by each thread) ---
def download_music(url, use_cookies=False):
    """
    Downloads and processes a single audio URL with detailed logging.
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
        'keepvideo': True,
        'outtmpl': {
            'default': 'music/%(title)s.%(ext)s',
            'thumbnail': 'music/thumbnails/%(title)s.%(ext)s',
        },
        'ignoreerrors': False,
        'retries': 3,
        'logger': YdlLogger(),
        'verbose': True,
    }

    if use_cookies:
        ydl_opts['cookiefile'] = 'cookies.txt'
    else:
        ydl_opts['cookiefile'] = None

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.add_post_processor(SanitizeFilenamePP(), when='post_process')
            ydl.download([url])
        return f"Successfully downloaded {url}"
    except Exception as e:
        logging.error(f"An error occurred while processing {url}. Details: {e}")
        raise

# --- Main Execution Block ---
if __name__ == "__main__":
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
                logging.info(f"Task finished for URL: {url}. Result: {result}")
            except Exception:
                logging.error(f"Task failed for URL: {url} after multiple retries.")

    logging.info("All download tasks have been processed! ✨")