import os
import json
import aiohttp
import asyncio
import subprocess
from typing import List, Dict, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Keep the download functions the same...
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

def create_slide_video(slides_dir: str, duration: float, output_path: str) -> str:
    """Create a video from slides using FFmpeg with precise timing."""
    # Create a temporary file listing all slide transitions
    concat_file = "slides_concat.txt"
    temp_output = "temp_slides.mp4"
    
    # Sort slides by timestamp
    slides = []
    for filename in sorted(os.listdir(slides_dir), key=lambda x: int(x.split('.')[0])):
        if filename.endswith('.png'):
            timestamp = int(filename.split('.')[0]) / 1000.0  # Convert ms to seconds
            slides.append((timestamp, os.path.join(slides_dir, filename)))
    
    # Add final timestamp
    slides.append((duration, slides[-1][1]))
    
    # Create concat file for FFmpeg
    with open(concat_file, 'w') as f:
        for i in range(len(slides) - 1):
            current_time = slides[i][0]
            next_time = slides[i+1][0]
            duration = next_time - current_time
            f.write(f"file '{slides[i][1]}'\n")
            f.write(f"duration {duration}\n")
        # Add last slide to avoid FFmpeg warnings
        f.write(f"file '{slides[-1][1]}'")
    
    # Create video from slides with exact durations
    cmd = [
        'ffmpeg', '-y',
        '-f', 'concat',
        '-safe', '0',
        '-i', concat_file,
        '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2',
        '-vsync', 'vfr',
        '-pix_fmt', 'yuv420p',
        temp_output
    ]
    subprocess.run(cmd, check=True)
    os.remove(concat_file)
    return temp_output

def create_presentation_video_ffmpeg(
    presentation_id: str,
    video_path: str,
    output_path: str = None,
    slide_scale: float = 0.75  # Scale of the main slide relative to video height
) -> None:
    """
    Create a video with slides inset using FFmpeg.
    The slides will be shown as the main content, with the video
    as a smaller overlay in the corner.
    """
    if output_path is None:
        output_path = f"presentation_{presentation_id}_ffmpeg.mp4"
    
    slides_dir = f"slides_{presentation_id}"
    if not os.path.exists(slides_dir):
        raise FileNotFoundError(f"Slides directory {slides_dir} not found")
    
    # Get video duration using FFprobe
    duration_cmd = [
        'ffprobe', 
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_path
    ]
    duration = float(subprocess.check_output(duration_cmd).decode().strip())
    
    # Create slide video
    slides_video = create_slide_video(slides_dir, duration, "temp_slides.mp4")
    
    # Calculate overlay size (maintaining aspect ratio)
    # Get video dimensions
    video_info_cmd = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height',
        '-of', 'json',
        video_path
    ]
    video_info = json.loads(subprocess.check_output(video_info_cmd).decode())
    video_width = int(video_info['streams'][0]['width'])
    video_height = int(video_info['streams'][0]['height'])
    
    # Calculate scaling
    scale_factor = slide_scale
    new_height = int(1080 * scale_factor)  # Assuming 1080p output
    new_width = int((new_height * video_width) / video_height)
    
    # Compose the final video with FFmpeg
    cmd = [
        'ffmpeg', '-y',
        '-i', slides_video,  # Slides as main content
        '-i', video_path,    # Original video for overlay
        '-filter_complex',
        f'[1:v]scale={new_width}:{new_height}[overlay];'
        f'[0:v][overlay]overlay=main_w-overlay_w-20:main_h-overlay_h-20:shortest=1[outv]',
        '-map', '[outv]',     # Video output
        '-map', '1:a',        # Audio from original video
        '-c:a', 'aac',        # Audio codec
        '-c:v', 'libx264',    # Video codec
        '-preset', 'ultrafast',
        '-crf', '23',         # Quality (lower = better, 23 is default)
        output_path
    ]
    
    subprocess.run(cmd, check=True)
    
    # Clean up temporary files
    os.remove(slides_video)
    logger.info(f"Created presentation video: {output_path}")

if __name__ == "__main__":
    # Example usage
    presentation_id = "39022942"
    video_path = "ICML  Scalable Oversight by Accounting for Unreliable Feedback.mp4"
    
    create_presentation_video_ffmpeg(
        presentation_id=presentation_id,
        video_path=video_path,
        slide_scale=0.75  # Slides take up 75% of the height
    )
    