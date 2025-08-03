import os
import re
import json
import time
import logging
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
import requests
from googletrans import Translator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    filename='mp3_metadata.log',
    filemode='a'
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

class MP3MetaEnricher:
    def __init__(self, music_dir, processed_log='processed_files.json'):
        self.music_dir = music_dir
        self.processed_log = processed_log
        self.processed = self.load_processed()
        self.translator = Translator()

    def load_processed(self):
        if os.path.exists(self.processed_log):
            with open(self.processed_log, 'r') as f:
                return set(json.load(f))
        return set()

    def save_processed(self):
        with open(self.processed_log, 'w') as f:
            json.dump(list(self.processed), f)

    def clean_filename(self, filename):
        # Remove special symbols, numbers, and non-English words, translate if needed
        name, ext = os.path.splitext(filename)
        # Remove special symbols and numbers
        name = re.sub(r'[^A-Za-z\s]', '', name)
        # Remove non-English words
        name = ' '.join([w for w in name.split() if w.isascii()])
        # Translate if not English
        if not all(ord(c) < 128 for c in name):
            try:
                name = self.translator.translate(name, dest='en').text
            except Exception as e:
                logging.error(f"Translation failed for {filename}: {e}")
        return name.strip() + ext

    def fetch_metadata(self, filename):
        """
        Try to fetch metadata for an mp3 file using YouTube and Google search as fallback.
        Returns a dict with 'artist', 'genre', 'title', 'album', 'date', 'tracknumber', 'composer', 'albumartist', 'discnumber', 'length', 'comment' if found, else None.
        """
        logging.info(f"Attempting to fetch metadata for {filename}")
        # Try YouTube search via yt-dlp (title only, no download)
        try:
            import yt_dlp
            ydl_opts = {
                'quiet': True,
                'skip_download': True,
                'extract_flat': True,
                'default_search': 'ytsearch1',
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(filename, download=False)
                if 'entries' in info and info['entries']:
                    entry = info['entries'][0]
                    artist = entry.get('uploader') or entry.get('artist')
                    genre = entry.get('genre')
                    title = entry.get('title')
                    album = entry.get('album')
                    date = entry.get('release_date') or entry.get('upload_date')
                    tracknumber = entry.get('track')
                    composer = entry.get('composer')
                    albumartist = entry.get('album_artist')
                    discnumber = entry.get('disc_number')
                    length = entry.get('duration')
                    comment = entry.get('description')
                    meta = {
                        'artist': artist or '',
                        'genre': genre or '',
                        'title': title or os.path.splitext(filename)[0],
                        'album': album or '',
                        'date': date or '',
                        'tracknumber': str(tracknumber) if tracknumber else '',
                        'composer': composer or '',
                        'albumartist': albumartist or '',
                        'discnumber': str(discnumber) if discnumber else '',
                        'length': str(length) if length else '',
                        'comment': comment or ''
                    }
                    logging.info(f"Fetched from YouTube: {meta}")
                    # Remove empty fields
                    meta = {k: v for k, v in meta.items() if v}
                    if meta:
                        return meta
        except Exception as e:
            logging.warning(f"YouTube metadata fetch failed for {filename}: {e}")
        # Fallback: Google Custom Search API
        try:
            api_key = os.getenv('GOOGLE_API_KEY')
            cse_id = os.getenv('GOOGLE_CSE_ID')
            if api_key and cse_id:
                search_url = (
                    f"https://www.googleapis.com/customsearch/v1?q={requests.utils.quote(filename)}+mp3+song&key={api_key}&cx={cse_id}"
                )
                resp = requests.get(search_url)
                if resp.status_code == 200:
                    data = resp.json()
                    if 'items' in data and data['items']:
                        snippet = data['items'][0].get('snippet', '')
                        # Try to extract artist/title from snippet (very basic)
                        artist, title = '', ''
                        match = re.search(r'by ([^\n\r]+)', snippet)
                        if match:
                            artist = match.group(1).split(' ')[0]
                        title_match = re.search(r'"([^"]+)"', snippet)
                        if title_match:
                            title = title_match.group(1)
                        meta = {
                            'artist': artist,
                            'title': title or os.path.splitext(filename)[0]
                        }
                        logging.info(f"Fetched from Google: {meta}")
                        meta = {k: v for k, v in meta.items() if v}
                        if meta:
                            return meta
                else:
                    logging.warning(f"Google API error {resp.status_code}: {resp.text}")
            else:
                logging.info("GOOGLE_API_KEY or GOOGLE_CSE_ID not set. Skipping Google fallback.")
        except Exception as e:
            logging.warning(f"Google metadata fetch failed for {filename}: {e}")
        logging.info(f"No metadata found for {filename} after all attempts.")
        return None

    def enrich_file(self, filepath):
        try:
            audio = MP3(filepath, ID3=EasyID3)
            # Common ID3 tags
            common_tags = ['artist', 'genre', 'title', 'album', 'date', 'tracknumber', 'composer', 'albumartist', 'discnumber', 'length', 'comment']
            missing = [k for k in common_tags if k not in audio]
            if not missing:
                return False  # Already has metadata
            meta = self.fetch_metadata(os.path.basename(filepath))
            if meta:
                for k, v in meta.items():
                    try:
                        audio[k] = v
                    except Exception as e:
                        logging.warning(f"Could not set tag {k} for {filepath}: {e}")
                audio.save()
                logging.info(f"Metadata added to {filepath}")
                return True
        except Exception as e:
            logging.error(f"Error processing {filepath}: {e}")
        return False

    def process(self):
        for root, _, files in os.walk(self.music_dir):
            for file in files:
                if not file.lower().endswith('.mp3'):
                    continue
                full_path = os.path.join(root, file)
                if full_path in self.processed:
                    continue
                cleaned = self.clean_filename(file)
                if cleaned != file:
                    new_path = os.path.join(root, cleaned)
                    if os.path.exists(new_path):
                        os.remove(new_path)  # Remove the existing file before renaming
                        logging.info(f"Removed existing file {new_path} to allow renaming.")
                    os.rename(full_path, new_path)
                    full_path = new_path
                if self.enrich_file(full_path):
                    self.processed.add(full_path)
                self.save_processed()

# Usage example:
# enricher = MP3MetaEnricher('/path/to/music')
# enricher.process()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Enrich MP3 metadata in a directory.")
    parser.add_argument("music_dir", help="Path to the directory containing mp3 files")
    args = parser.parse_args()
    enricher = MP3MetaEnricher(args.music_dir)
    enricher.process()
