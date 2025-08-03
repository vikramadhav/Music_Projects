import os
import re
import concurrent.futures
import logging
import threading
import yt_dlp
import shutil # Added for moving files
from yt_dlp.utils import DownloadError, ExtractorError

# --- Thread-Safe Logger Setup ---
def setup_logging():
    """Configures the logging system for thread-safe, verbose output.

    Logs will be written to 'rename.log' and also output to the console.
    The log format includes timestamp, thread name, log level, and message.
    """
    log_formatter = logging.Formatter(
        '%(asctime)s - %(threadName)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Log to a file
    file_handler = logging.FileHandler('rename.log', mode='w')
    file_handler.setFormatter(log_formatter)
    
    # Log to the console
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(log_formatter)
    
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

# --- Custom Logger for yt-dlp (to suppress excessive output) ---
class YdlLogger:
    """Custom logger for yt-dlp to integrate its output with the application's logging system.
    This version is more concise for renaming purposes.
    """
    def debug(self, msg):
        pass # Suppress debug messages

    def info(self, msg):
        if "Downloading webpage" in msg or "Extracting information" in msg:
            logging.debug(msg) # Log these as debug to keep info level cleaner
        else:
            logging.info(msg)

    def warning(self, msg):
        logging.warning(msg)

    def error(self, msg):
        logging.error(msg)

# --- Helper Function to Sanitize Filenames ---
def sanitize_filename(filename):
    """Removes invalid characters from a filename."""
    sanitized = re.sub(r'[\\/:*?"<>|]+', '', filename).strip()
    return sanitized

# --- Check if filename is already "sensible" ---
def is_sensible_filename(filename):
    """
    Checks if a filename already appears to be in a sensible format (e.g., "Artist - Song Title").
    This is a basic heuristic and can be improved.
    """
    # Look for patterns like "Artist - Song Title", "Song Title (feat. Artist)"
    # or if it contains common delimiters like '-' or '()' indicating some structure.
    if re.search(r' - | \(|\)', filename) or len(filename.split()) > 2:
        return True
    return False

# --- Genre Mapping ---
GENRE_MAPPING = {
    "arabic": "Arabic & Middle Eastern",
    "middle eastern": "Arabic & Middle Eastern",
    "bollywood": "Bollywood & Indian Pop",
    "indian pop": "Bollywood & Indian Pop",
    "chill": "Chill & Acoustic",
    "acoustic": "Chill & Acoustic",
    "electronic": "Electronic & EDM",
    "edm": "Electronic & EDM",
    "pop": "Pop",
    "rock": "Rock",
    "sufi": "Sufi & Devotional",
    "devotional": "Sufi & Devotional",
    "upbeat": "Upbeat & Party",
    "party": "Upbeat & Party",
    # Add more keywords as needed
}

# --- Determine Genre from YouTube Info ---
def determine_genre(info_dict):
    """
    Determines the genre based on YouTube info_dict (categories, tags, title, description).
    """
    if not info_dict:
        return "Other"

    text_to_analyze = []
    if 'categories' in info_dict and info_dict['categories']:
        text_to_analyze.extend(info_dict['categories'])
    if 'tags' in info_dict and info_dict['tags']:
        text_to_analyze.extend(info_dict['tags'])
    if 'title' in info_dict:
        text_to_analyze.append(info_dict['title'])
    if 'description' in info_dict:
        text_to_analyze.append(info_dict['description'])

    for text in text_to_analyze:
        for keyword, genre_folder in GENRE_MAPPING.items():
            if keyword.lower() in text.lower():
                return genre_folder
    return "Other"

# --- Search YouTube and Get Music Details ---
def get_music_details_from_youtube(query):
    """
    Searches YouTube for the given query and returns the info_dict of the first result.
    """
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True, # Do not download playlists
        'quiet': True, # Suppress console output
        'extract_flat': True, # Extract info without downloading
        'force_generic_extractor': True, # Try to extract info from any URL
        'default_search': 'ytsearch', # Search YouTube by default
        'logger': YdlLogger(),
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(query, download=False)
            if info_dict and 'entries' in info_dict and info_dict['entries']:
                return info_dict['entries'][0] # Return the first entry's info_dict
    except (DownloadError, ExtractorError) as e:
        logging.debug(f"YouTube search failed for '{query}'. Reason: {e}") # Changed to debug
    except Exception as e:
        logging.debug(f"An unexpected error occurred during YouTube search for '{query}': {e}") # Changed to debug
    return None



# --- Process Single File ---
def process_music_file(filepath, base_music_folder):
    """
    Processes a single music file: checks if it needs renaming, searches YouTube, and renames/moves if necessary.
    """
    thread_name = threading.current_thread().name
    filename = os.path.basename(filepath)
    name_without_ext, ext = os.path.splitext(filename)

    logging.info(f"[{thread_name}] Processing file: {filename}")

    if is_sensible_filename(name_without_ext):
        logging.info(f"[{thread_name}] Skipping '{filename}' - filename already seems sensible.")
        return f"Skipped '{filename}' (sensible name)"

    logging.debug(f"[{thread_name}] Searching YouTube for '{name_without_ext}'...")
    youtube_info = get_music_details_from_youtube(name_without_ext)

    if youtube_info and 'title' in youtube_info:
        new_title = youtube_info['title']
        logging.debug(f"[{thread_name}] Found title from YouTube: {new_title}")
    else:
        logging.info(f"[{thread_name}] No suitable YouTube match found for '{filename}'. Skipping rename.")
        return f"No match for '{filename}'"

    sanitized_new_title = sanitize_filename(new_title)
    if not sanitized_new_title:
        logging.warning(f"[{thread_name}] Sanitized title for '{filename}' is empty. Skipping rename.")
        return f"Skipped '{filename}' (empty sanitized title)"

    # Determine genre and create target directory
    genre_folder_name = determine_genre(youtube_info)
    target_genre_path = os.path.join(base_music_folder, genre_folder_name)
    os.makedirs(target_genre_path, exist_ok=True) # Ensure genre folder exists

    new_filename = f"{sanitized_new_title}{ext}"
    new_filepath = os.path.join(target_genre_path, new_filename) # New path includes genre folder

    if filepath == new_filepath:
        logging.info(f"[{thread_name}] Filename '{filename}' is already optimal and in correct genre folder. No rename/move needed.")
        return f"No change for '{filename}'"

    if os.path.exists(new_filepath):
        logging.warning(f"[{thread_name}] Target file '{new_filename}' already exists. Skipping rename/move for '{filename}'.")
        return f"Skipped '{filename}' (target exists)"

    try:
        shutil.move(filepath, new_filepath) # Use shutil.move for robustness
        logging.info(f"[{thread_name}] Renamed and moved '{filename}' to '{new_filepath}'")
        return f"Renamed and moved '{filename}' to '{new_filepath}'"
    except Exception as e: # Catch broader exceptions for moving
        logging.error(f"[{thread_name}] Error renaming/moving '{filename}' to '{new_filepath}': {e}")
        return f"Failed to rename/move '{filename}' (Error: {e})"

# --- Main Execution Block ---
if __name__ == "__main__":
    setup_logging()
    CONCURRENCY_LEVEL = 4 # Adjust as needed
    music_folder = 'music' # Assuming music files are in the 'music' directory

    if not os.path.exists(music_folder):
        logging.error(f"Music folder '{music_folder}' not found. Please ensure it exists.")
        exit()

    # Get all files in the music folder (including subdirectories)
    music_files = []
    for root, dirs, files in os.walk(music_folder):
        # Exclude the genre subdirectories from being re-scanned for files to process
        # This prevents trying to rename files that have already been moved
        dirs[:] = [d for d in dirs if d not in GENRE_MAPPING.values() and d != 'thumbnails']

        for file in files:
            # Exclude hidden files and common non-music files
            if not file.startswith('.') and not file.lower().endswith(('.db', '.ini', '.log', '.txt')):
                music_files.append(os.path.join(root, file))

    if not music_files:
        logging.info(f"No music files found in '{music_folder}'.")
        exit()

    logging.info(f"Found {len(music_files)} files. Starting renaming with {CONCURRENCY_LEVEL} parallel workers...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY_LEVEL, thread_name_prefix='Renamer') as executor:
        future_to_filepath = {executor.submit(process_music_file, filepath, music_folder): filepath for filepath in music_files}

        for future in concurrent.futures.as_completed(future_to_filepath):
            filepath = future_to_filepath[future]
            try:
                result = future.result()
                logging.info(f"Result for {os.path.basename(filepath)}: {result}")
            except Exception as exc:
                logging.error(f'{os.path.basename(filepath)} generated an exception: {exc}')

    logging.info("All file renaming tasks have been processed! ✨")
