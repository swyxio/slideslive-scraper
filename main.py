import sys
import os
import asyncio
import logging
from typing import List
import aiofiles
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import requests
from bs4 import BeautifulSoup
import re
import subprocess
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Import functions from other modules
from slide_saving import download_slides, create_presentation_video
from combine_pip import create_pip_video

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def download_video(url: str) -> str:
    """
    Downloads video from a URL containing an m3u8 stream.
    Returns the title of the downloaded video.
    """
    # Get page HTML
    response = requests.get(url)
    html = response.text
    
    # Parse title
    soup = BeautifulSoup(html, 'html.parser')
    title = soup.title.string if soup.title else 'video'
    # Clean title for filename
    title = re.sub(r'[^\w\s-]', '', title).strip()

    # Initialize headless browser
    options = webdriver.FirefoxOptions()
    options.add_argument('--headless')
    driver = webdriver.Firefox(options=options)
    
    try:
        # First try to find m3u8 URL in initial page HTML
        m3u8_match = re.search(r'(https?://[^\s<>"\']+?master\.m3u8[^\s<>"\']*)', html)
        if m3u8_match:
            m3u8_url = m3u8_match.group(1)
        else:
            # If not found, load the page and wait for iframe to render
            driver.get(url)
            iframe = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[id^='presentation-embed'] iframe"))
            )
            iframe_url = iframe.get_attribute('src')
            
            # Switch to iframe and get rendered content
            driver.switch_to.frame(iframe)
            iframe_html = driver.page_source
            
            # Try to find m3u8 URL in rendered iframe content
            m3u8_match = re.search(r'(https?://[^\s<>"\']+?master\.m3u8[^\s<>"\']*)', iframe_html)
            if not m3u8_match:
                raise Exception("Could not find master.m3u8 URL in page or rendered iframe")
            
            m3u8_url = m3u8_match.group(1)

        logger.info(f"Found M3U8 URL: {m3u8_url}")
        
        # Download with youtube-dl
        with open(f'{title}_download.log', 'w') as log_file:
            result = subprocess.run([
                'youtube-dl',
                '-o', f'{title}.%(ext)s',
                m3u8_url
            ], stdout=log_file, stderr=subprocess.PIPE, text=True)
            
            if result.returncode != 0:
                raise Exception(f"youtube-dl failed: {result.stderr}")

        # Get video file info if download succeeded
        video_file = f"{title}.mp4"
        if os.path.exists(video_file):
            size_bytes = os.path.getsize(video_file)
            size_mb = size_bytes / (1024 * 1024)
            logger.info(f"Downloaded video size: {size_mb:.1f} MB")
            
            # Get detailed video info using ffprobe
            try:
                video_info = subprocess.check_output([
                    'ffprobe',
                    '-v', 'error', 
                    '-select_streams', 'v:0',
                    '-show_entries', 'stream=width,height,codec_name,bit_rate,avg_frame_rate',
                    '-of', 'json',
                    video_file
                ]).decode()
                video_data = json.loads(video_info)
                stream = video_data['streams'][0]
                
                logger.info(f"Video details:")
                logger.info(f"Resolution: {stream.get('width')}x{stream.get('height')}")
                logger.info(f"Codec: {stream.get('codec_name')}")
                logger.info(f"Bitrate: {int(stream.get('bit_rate', 0))/1000:.0f} kbps")
                logger.info(f"Frame rate: {stream.get('avg_frame_rate')}")

                # Extract audio from video using ffmpeg
                audio_file = video_file.replace('.mp4', '.mp3')
                logger.info(f"Extracting audio to {audio_file}...")
                
                audio_result = subprocess.run([
                    'ffmpeg',
                    '-i', video_file,
                    '-vn',  # Disable video
                    '-acodec', 'libmp3lame',  # Use MP3 codec
                    '-q:a', '2',  # High quality audio
                    audio_file
                ], stderr=subprocess.PIPE, text=True)
                
                if audio_result.returncode != 0:
                    logger.warning(f"Could not extract audio: {audio_result.stderr}")
                else:
                    logger.info("Audio extraction complete")

            except Exception as e:
                logger.warning(f"Could not get detailed video info: {str(e)}")

        return title

    except Exception as e:
        logger.error(f"Error downloading video: {str(e)}")
        raise

    finally:
        driver.quit()

async def process_single_talk(url: str, log_dir: str) -> None:
    """Process a single talk URL - download video, slides, and combine them."""
    
    # Get talk ID and clean title for folder name
    talk_id = url.split('/')[-1]
    
    # Get page title for folder name
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    talk_name = soup.title.string if soup.title else 'untitled'
    talk_name = re.sub(r'[^\w\s-]', '', talk_name).strip()
    
    # Create unique directory for this talk
    talk_dir = os.path.join("talks", f"talk_{talk_id}_{talk_name}")
    os.makedirs(talk_dir, exist_ok=True)
    
    # Create log file in talk directory
    log_file = os.path.join(talk_dir, "processing.log")
    
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    
    try:
        logger.info(f"Starting processing for talk: {url}")
        
        # Step 1: Download video
        logger.info("Downloading video...")
        title = await download_video_async(url)
        video_path = os.path.join(talk_dir, "initialdownload.mp4")
        # Move the downloaded video to the talk directory with generic name
        original_video = f"{title}.mp4"
        if os.path.exists(original_video):
            os.rename(original_video, video_path)
            
            # Also move the download log if it exists
            original_log = f"{title}_download.log"
            if os.path.exists(original_log):
                os.rename(original_log, os.path.join(talk_dir, "download.log"))
            
            # Move the mp3 file if it exists
            original_mp3 = f"{title}.mp3"
            if os.path.exists(original_mp3):
                os.rename(original_mp3, os.path.join(talk_dir, "audio.mp3"))
        
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
            
        # Step 2: Download slides
        logger.info("Downloading slides...")
        presentation_id = talk_id
        slides_dir = os.path.join(talk_dir, "slides")  # Simplified slides directory name
        await download_slides(presentation_id, slides_dir)
        
        # Step 3: Create presentation video with slides
        logger.info("Creating presentation video...")
        slides_video_path = os.path.join(talk_dir, "createdslides.mp4")
        create_presentation_video(
            presentation_id=presentation_id,
            video_path=video_path,
            slides_dir=slides_dir,
            output_path=slides_video_path,
            overlay_scale=0.25,
            margin=20
        )
        
        # Step 4: Create PiP video as final output
        logger.info("Creating final PiP video...")
        final_output = os.path.join(talk_dir, "finalvideo.mp4")
        create_pip_video(slides_video_path, video_path, final_output)
        
        logger.info(f"Successfully processed talk {talk_id}. Final output: {final_output}")
        
    except Exception as e:
        logger.error(f"Error processing talk {url}: {str(e)}", exc_info=True)
        raise
    
    finally:
        logger.removeHandler(file_handler)
        file_handler.close()

async def process_talk_list(url_file: str, max_concurrent: int = 3) -> None:
    """Process multiple talks from a file with URLs in parallel."""
    
    # Create logs directory
    log_dir = "processing_logs"
    os.makedirs(log_dir, exist_ok=True)
    
    # Read URLs from file
    async with aiofiles.open(url_file, 'r') as f:
        urls = [line.strip() for line in (await f.readlines()) if line.strip()]
    
    # Process URLs with semaphore for concurrency control
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def bounded_process(url: str):
        async with semaphore:
            await process_single_talk(url, log_dir)
    
    # Create tasks for all URLs
    tasks = [asyncio.create_task(bounded_process(url)) for url in urls]
    
    # Wait for all tasks to complete
    await asyncio.gather(*tasks, return_exceptions=True)

async def download_video_async(url: str) -> str:
    """Asynchronous wrapper for the synchronous download_video function."""
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        title = await loop.run_in_executor(pool, download_video, url)
        return title

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python main.py <url_or_file>")
        sys.exit(1)
        
    input_path = sys.argv[1]
    
    try:
        if os.path.isfile(input_path):
            # Process multiple URLs from file
            asyncio.run(process_talk_list(input_path))
        else:
            # Process single URL
            asyncio.run(process_single_talk(input_path, "processing_logs"))
            
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)
