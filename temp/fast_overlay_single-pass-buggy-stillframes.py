import os
import json
import aiohttp
import asyncio
import subprocess
from typing import List, Dict, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Download functions remain the same...
async def download_slide(session: aiohttp.ClientSession, 
                        presentation_id: str,
                        image_name: str, 
                        timestamp: int,
                        output_dir: str) -> None:
    url = f"https://rs.slideslive.com/{presentation_id}/slides/{image_name}.png?h=432&f=webp&s=lambda&accelerate_s3=1"
    output_path = os.path.join(output_dir, f"{timestamp}.png")
    try:
        async with session.get(url) as response:
            if response.status == 200:
                with open(output_path, 'wb') as f:
                    f.write(await response.read())
                logger.info(f"Downloaded slide {image_name} for timestamp {timestamp}")
            else:
                logger.error(f"Failed to download slide {image_name}, status: {response.status}")
    except Exception as e:
        logger.error(f"Error downloading slide {image_name}: {str(e)}")

async def download_presentation_slides(presentation_id: str, max_concurrent: int = 5) -> None:
    output_dir = f"slides_{presentation_id}"
    os.makedirs(output_dir, exist_ok=True)
    json_url = f"https://s.slideslive.com/{presentation_id}/v3/slides.json"
    async with aiohttp.ClientSession() as session:
        async with session.get(json_url) as response:
            if response.status != 200:
                logger.error(f"Failed to fetch slides JSON, status: {response.status}")
                return
            data = await response.json()
            slides = data.get("slides", [])
            if not slides:
                logger.error("No slides found in JSON response")
                return
            tasks = []
            semaphore = asyncio.Semaphore(max_concurrent)
            async def bounded_download(img_name: str, ts: int):
                async with semaphore:
                    await download_slide(session, presentation_id, img_name, ts, output_dir)
            for slide in slides:
                if slide["type"] == "image":
                    tasks.append(asyncio.create_task(
                        bounded_download(slide["image"]["name"], slide["time"])
                    ))
            await asyncio.gather(*tasks)
            logger.info(f"Downloaded all slides to {output_dir}")

def download_slides(presentation_id: str):
    asyncio.run(download_presentation_slides(presentation_id))

def create_presentation_video_ffmpeg_single_pass(
    presentation_id: str,
    video_path: str,
    output_path: str = None,
    slide_scale: float = 0.75
) -> None:
    """
    Create a video with slides inset using FFmpeg in a single pass.
    """
    if output_path is None:
        output_path = f"presentation_{presentation_id}_ffmpeg.mp4"
    
    slides_dir = f"slides_{presentation_id}"
    if not os.path.exists(slides_dir):
        raise FileNotFoundError(f"Slides directory {slides_dir} not found")
    
    # Get video duration and dimensions using FFprobe
    info_cmd = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,r_frame_rate',
        '-show_entries', 'format=duration',
        '-of', 'json',
        video_path
    ]
    info = json.loads(subprocess.check_output(info_cmd).decode())
    duration = float(info['format']['duration'])
    video_width = int(info['streams'][0]['width'])
    video_height = int(info['streams'][0]['height'])
    
    # Calculate overlay size
    scale_factor = slide_scale
    new_height = int(1080 * scale_factor)
    new_width = int((new_height * video_width) / video_height)
    
    # Create concat file for slides with precise timing
    slides = []
    concat_file = "slides_concat.txt"
    for filename in sorted(os.listdir(slides_dir), key=lambda x: int(x.split('.')[0])):
        if filename.endswith('.png'):
            timestamp = int(filename.split('.')[0]) / 1000.0
            slides.append((timestamp, os.path.join(slides_dir, filename)))
    slides.append((duration, slides[-1][1]))
    
    with open(concat_file, 'w') as f:
        for i in range(len(slides) - 1):
            current_time = slides[i][0]
            next_time = slides[i+1][0]
            duration = next_time - current_time
            f.write(f"file '{slides[i][1]}'\n")
            f.write(f"duration {duration}\n")
        f.write(f"file '{slides[-1][1]}'")
    
    # Single FFmpeg command that handles both slides and video overlay
    cmd = [
        'ffmpeg', '-y',
        '-f', 'concat', '-safe', '0', '-i', concat_file,  # Slides input
        '-i', video_path,  # Video input
        '-filter_complex',
        f'[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2[slides];' +
        f'[1:v]scale={new_width}:{new_height}[overlay];' +
        f'[slides][overlay]overlay=main_w-overlay_w-20:main_h-overlay_h-20:shortest=1[outv]',
        '-map', '[outv]',  # Video output
        '-map', '1:a',     # Audio from original video
        '-c:v', 'h264_videotoolbox',  # Hardware encoding on Mac
        '-c:a', 'aac',     # Audio codec
        '-preset', 'ultrafast',
        '-b:v', '2M',      # Target bitrate
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True)
        logger.info(f"Created presentation video: {output_path}")
    except subprocess.CalledProcessError:
        # If hardware encoding fails, fall back to software encoding
        cmd[cmd.index('h264_videotoolbox')] = 'libx264'
        subprocess.run(cmd, check=True)
        logger.info(f"Created presentation video (software encoding): {output_path}")
    finally:
        os.remove(concat_file)

if __name__ == "__main__":
    presentation_id = "39022942"
    video_path = "ICML  Scalable Oversight by Accounting for Unreliable Feedback.mp4"
    
    create_presentation_video_ffmpeg_single_pass(
        presentation_id=presentation_id,
        video_path=video_path,
        slide_scale=0.75
    )