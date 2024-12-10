import os
import json
import aiohttp
import asyncio
from typing import List, Dict, Tuple
import logging
from moviepy.editor import (
    VideoFileClip, 
    ImageClip, 
    CompositeVideoClip, 
    concatenate_videoclips
)
from PIL import Image
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def download_slide(session: aiohttp.ClientSession, 
                        presentation_id: str,
                        image_name: str, 
                        timestamp: int,
                        output_dir: str) -> None:
    """Download a single slide and save it with timestamp as filename."""
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

async def download_presentation_slides(presentation_id: str, output_dir: str, max_concurrent: int = 5) -> None:
    """
    Download all slides for a presentation in parallel.
    
    Args:
        presentation_id: The SlidesLive presentation ID
        output_dir: Directory to save slides in
        max_concurrent: Maximum number of concurrent downloads
    """
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Get slides data
    json_url = f"https://s.slideslive.com/{presentation_id}/v3/slides.json?1724563602"
    
    async with aiohttp.ClientSession() as session:
        # Fetch slides JSON
        async with session.get(json_url) as response:
            if response.status != 200:
                logger.error(f"Failed to fetch slides JSON, status: {response.status}")
                return
            
            data = await response.json()
            slides = data.get("slides", [])
            
            if not slides:
                logger.error("No slides found in JSON response")
                return
            
            # Create download tasks
            tasks = []
            semaphore = asyncio.Semaphore(max_concurrent)
            
            async def bounded_download(img_name: str, ts: int):
                async with semaphore:
                    await download_slide(
                        session, 
                        presentation_id,
                        img_name, 
                        ts,
                        output_dir
                    )
            
            for slide in slides:
                if slide["type"] == "image":
                    image_name = slide["image"]["name"]
                    timestamp = slide["time"]
                    tasks.append(asyncio.create_task(
                        bounded_download(image_name, timestamp)
                    ))
            
            # Wait for all downloads to complete
            await asyncio.gather(*tasks)
            logger.info(f"Downloaded all slides to {output_dir}")

async def download_slides(presentation_id: str, output_dir: str):
    """Asynchronous function to download slides."""
    await download_presentation_slides(presentation_id, output_dir)

def create_presentation_video(
    presentation_id: str,
    video_path: str,
    slides_dir: str,
    output_path: str = None,
    overlay_scale: float = 0.25,
    margin: int = 20
) -> str:
    """
    Create a video combining slides with video overlay.
    
    Args:
        presentation_id: The presentation ID used to find slides
        video_path: Path to the video file to use as overlay
        slides_dir: Directory containing the slides
        output_path: Where to save the final video
        overlay_scale: Size of the overlay relative to frame
        margin: Margin around the overlay in pixels
    """
    if output_path is None:
        output_path = f"presentation_{presentation_id}_with_overlay.mp4"
    
    if not os.path.exists(slides_dir):
        raise FileNotFoundError(f"Slides directory {slides_dir} not found")
    
    # Load the video
    video = VideoFileClip(video_path)
    video_duration = video.duration
    
    # Get all slides and their timestamps
    slides = []
    for filename in sorted(os.listdir(slides_dir), key=lambda x: int(x.split('.')[0])):
        if filename.endswith('.png'):
            timestamp = int(filename.split('.')[0]) / 1000.0  # Convert ms to seconds
            slide_path = os.path.join(slides_dir, filename)
            slides.append((timestamp, slide_path))
    
    if not slides:
        raise ValueError("No slides found in slides directory")
    
    # Add an end timestamp
    slides.append((video_duration, slides[-1][1]))
    
    # Create slide clips
    clips = []
    for i in range(len(slides) - 1):
        start_time, slide_path = slides[i]
        end_time = slides[i + 1][0]
        
        # Create slide clip
        slide_clip = ImageClip(slide_path).set_duration(end_time - start_time)
        slide_clip = slide_clip.resize(height=1080)  # Standardize height
        
        # Scale and position the video overlay
        overlay = video.subclip(start_time, end_time)
        overlay_resized = overlay.resize(width=overlay.w * overlay_scale)
        
        # Position overlay in bottom right with margin
        overlay_x = slide_clip.w - overlay_resized.w - margin
        overlay_y = slide_clip.h - overlay_resized.h - margin
        
        # Compose the clips
        comp = CompositeVideoClip([
            slide_clip,
            overlay_resized.set_position((overlay_x, overlay_y))
        ])
        
        clips.append(comp)
    
    # Concatenate all clips
    final_video = concatenate_videoclips(clips)
    
    # Write the final video
    final_video.write_videofile(
        output_path,
        codec='libx264',
        audio_codec='aac',
        fps=24
    )
    
    # Clean up
    video.close()
    final_video.close()
    logger.info(f"Created presentation video: {output_path}")
    
    return output_path

if __name__ == "__main__":
    # Example usage
    presentation_id = "39022942"
    
    # # First download the slides
    # download_slides(presentation_id)
    
    # Then create the video (assuming you have video.mp4 in the current directory)
    create_presentation_video(
        presentation_id=presentation_id,
        # video_path=presentation_id + ".mp4",
        video_path="ICML  Scalable Oversight by Accounting for Unreliable Feedback.mp4",
        overlay_scale=0.25,  # Makes overlay 1/4 of the frame width
        margin=20
    ) 