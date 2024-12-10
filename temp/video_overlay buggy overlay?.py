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
    clips_array,
    vfx,
    concatenate_videoclips
)
from PIL import Image
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Keeping the download functions the same as they're working well
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

async def download_presentation_slides(presentation_id: str, max_concurrent: int = 5) -> None:
    """Download all slides for a presentation in parallel."""
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
    """Synchronous wrapper for the async download function."""
    asyncio.run(download_presentation_slides(presentation_id))

def create_presentation_video_fast(
    presentation_id: str,
    video_path: str,
    output_path: str = None,
    mode: str = "side_by_side",  # or "inset"
    slide_ratio: float = 0.5,  # for side_by_side: ratio of frame width for slides
    inset_scale: float = 0.25,  # for inset: scale of the inset video
    margin: int = 20
) -> None:
    """
    Create a video combining slides with the original video, optimized for speed.
    Uses the original video as the base and overlays slides with minimal re-encoding.
    
    Args:
        presentation_id: The presentation ID used to find slides
        video_path: Path to the video file
        output_path: Where to save the final video
        mode: "side_by_side" or "inset" - determines layout
        slide_ratio: For side_by_side mode, what portion of width should slides take
        inset_scale: For inset mode, how large should the inset be relative to frame
        margin: Margin around elements in pixels
    """
    if output_path is None:
        output_path = f"presentation_{presentation_id}_fast_{mode}.mp4"
    
    slides_dir = f"slides_{presentation_id}"
    if not os.path.exists(slides_dir):
        raise FileNotFoundError(f"Slides directory {slides_dir} not found")
    
    # Load the video with minimal decoding
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
    
    # Prepare the video using the original video as base
    if mode == "side_by_side":
        # Create a composite video for the entire duration
        final_w = video.w
        final_h = video.h
        video_width = int(final_w * (1 - slide_ratio))
        
        def make_frame(t):
            # Get current slide based on timestamp
            current_slide_idx = 0
            for i, (slide_time, _) in enumerate(slides[:-1]):
                if t >= slide_time:
                    current_slide_idx = i
            
            # Get the current slide image
            _, slide_path = slides[current_slide_idx]
            slide_img = ImageClip(slide_path).resize(width=int(final_w * slide_ratio) - margin).get_frame(0)
            
            # Get the video frame
            video_frame = video.resize(width=video_width).get_frame(t)
            
            # Create the combined frame
            combined_frame = np.zeros((final_h, final_w, 3), dtype='uint8')
            
            # Copy video frame
            h = min(video_frame.shape[0], final_h)
            combined_frame[:h, :video_width] = video_frame[:h]
            
            # Copy slide frame
            slide_h = min(slide_img.shape[0], final_h)
            slide_w = slide_img.shape[1]
            combined_frame[:slide_h, video_width:video_width+slide_w] = slide_img[:slide_h]
            
            return combined_frame
        
        # Create the final clip
        final_video = VideoFileClip(video_path).fl(make_frame, apply_to=['mask'])
        
    else:  # inset mode
        # Create a composite video clip using the slides as base
        def make_frame(t):
            # Get current slide based on timestamp
            current_slide_idx = 0
            for i, (slide_time, _) in enumerate(slides[:-1]):
                if t >= slide_time:
                    current_slide_idx = i
            
            # Get the current slide image
            _, slide_path = slides[current_slide_idx]
            slide_img = ImageClip(slide_path).resize(width=video.w).get_frame(0)
            
            # Get the video frame
            video_frame = video.resize(width=int(video.w * inset_scale)).get_frame(t)
            
            # Create the combined frame
            combined_frame = slide_img.copy()
            
            # Calculate position for video inset
            video_h, video_w = video_frame.shape[:2]
            x = combined_frame.shape[1] - video_w - margin
            y = combined_frame.shape[0] - video_h - margin
            
            # Overlay video frame
            combined_frame[y:y+video_h, x:x+video_w] = video_frame
            
            return combined_frame
        
        # Create the final clip
        final_video = VideoFileClip(video_path).fl(make_frame, apply_to=['mask'])
    
    # Write the final video with fast encoding settings
    final_video.write_videofile(
        output_path,
        codec='libx264',
        audio_codec='aac',
        fps=24,
        preset='ultrafast',  # Fastest encoding
        threads=4,  # Use multiple threads
        bitrate='2000k'  # Lower bitrate for faster encoding
    )
    
    # Clean up
    video.close()
    final_video.close()
    logger.info(f"Created presentation video: {output_path}")

if __name__ == "__main__":
    # Example usage
    presentation_id = "39022942"
    video_path = "ICML  Scalable Oversight by Accounting for Unreliable Feedback.mp4"
    
    # Create side-by-side version (fastest)
    create_presentation_video_fast(
        presentation_id=presentation_id,
        video_path=video_path,
        mode="side_by_side",
        slide_ratio=0.5  # Slides take up 50% of the width
    )