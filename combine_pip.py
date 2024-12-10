from moviepy.editor import VideoFileClip, CompositeVideoClip, ColorClip
import os
import logging

logger = logging.getLogger(__name__)

def create_pip_video(main_video_path, secondary_video_path, output_path=None):
    """
    Creates picture-in-picture video.
    Returns the path to the created video.
    """
    logger.info(f"Creating PiP video from {main_video_path} and {secondary_video_path}")
    
    if output_path is None:
        # Generate output filename in same directory as main video
        main_dir = os.path.dirname(main_video_path)
        main_name = os.path.splitext(os.path.basename(main_video_path))[0]
        secondary_name = os.path.splitext(os.path.basename(secondary_video_path))[0]
        output_path = os.path.join(main_dir, f"{main_name}_pip_{secondary_name}.mp4")
    
    # Load the videos
    main_video = VideoFileClip(main_video_path)
    secondary_video = VideoFileClip(secondary_video_path)
    
    # Get dimensions of main video
    width, height = main_video.size
    
    # Resize secondary video to 1/4 of main video width
    new_width = width // 4
    secondary_video_resized = secondary_video.resize(width=new_width)
    
    # Calculate margins (20 pixels from edges)
    margin = 20
    
    # Create a slightly larger background clip for border (3px border)
    border_width = 3
    border_color = (255, 255, 255)  # White border
    
    # Create border by making a color clip slightly larger than the video
    border = ColorClip(
        size=(secondary_video_resized.w + 2*border_width, 
              secondary_video_resized.h + 2*border_width),
        color=border_color
    ).set_duration(main_video.duration)
    
    # Position the border
    border = border.set_position((
        width - secondary_video_resized.w - margin - border_width,
        height - secondary_video_resized.h - margin - border_width
    ))
    
    # Position the secondary video
    secondary_video_resized = secondary_video_resized.set_position((
        width - secondary_video_resized.w - margin,
        height - secondary_video_resized.h - margin
    ))
    
    # Combine all clips
    final_video = CompositeVideoClip([
        main_video,
        border,
        secondary_video_resized
    ])
    
    # Write the output file
    final_video.write_videofile(
        output_path,
        codec='libx264',
        audio_codec='aac'
    )
    
    # Close the video files
    main_video.close()
    secondary_video.close()
    
    logger.info(f"Successfully created PiP video: {output_path}")
    return output_path

if __name__ == "__main__":
    main_video = "39021974.mp4"
    secondary_video = "ICML 2024 Position On the Societal Impact of Open Foundation Models Oral.mp4"
    
    output_file = create_pip_video(main_video, secondary_video)
    print(f"Created combined video: {output_file}") 