# ML Conference Talk Downloader & Processor

A Python-based tool for downloading and processing machine learning conference talks, including slide extraction and organization.

## Overview

This tool helps download and process conference talks, extracting slides and organizing them into a structured format. It handles video processing and slide extraction, making it easier to review and reference conference materials.

## Project Structure

## Main Files

- `main.py`: Core script that handles downloading and processing conference talks
  - Downloads videos from conference URLs
  - Extracts slides and audio
  - Creates picture-in-picture videos with synchronized slides
  - Manages parallel processing of multiple talks

- `slide_saving.py`: Handles slide extraction and processing
  - Downloads individual slides from presentations
  - Creates video sequences from extracted slides
  - Synchronizes slides with video timing

- `combine_pip.py`: Creates picture-in-picture video outputs
  - Combines slide video with speaker video
  - Handles video overlay positioning and scaling
  - Produces final processed video output

## Input Files

- `downloadlist.txt`: List of conference talk URLs to process
- `requirements.txt`: Python package dependencies

## Output Structure

The tool creates a structured output in the `talks` directory:


