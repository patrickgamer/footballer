import os
import subprocess
import tempfile
import datetime
from loguru import logger
import json
import math

# Get filename descriptor from the user
file_descriptor = input("Enter the filename descriptor in CamelCase: ")

TARGET_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB

# Set directory paths
script_dir = os.path.dirname(os.path.abspath(__file__))
source_dir = os.path.join(script_dir, "sourceVids")
source_files = [os.path.join(source_dir, f) for f in os.listdir(source_dir) if f.lower().endswith(".mov")]
source_files.sort(key=os.path.getctime)  # sort by creation time instead of mod time
first_file_date = datetime.datetime.fromtimestamp(os.path.getctime(source_files[0])).strftime('%Y.%m.%d')
uncompressed_video = os.path.join(script_dir, f"{first_file_date}.{file_descriptor}.mov")

# function to compress video using given CRF value
def video_compressor(orig_file, crf):
    global SAMPLE_DURATION
    sample_file = orig_file.replace(".mov", f".CRF{crf}.mp4")
    sample_command = [
        'ffmpeg', '-y', '-i', orig_file, '-t', str(SAMPLE_DURATION),
        '-c:v', 'libx264', '-crf', str(crf), sample_file
    ]
    subprocess.run(sample_command, check=True)
    return sample_file # returns the sample file path

# function to get video duration
def video_duration(video_path):
    # Use ffprobe to get the video duration
    command = [
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
        video_path
    ]
    duration = subprocess.run(command, capture_output=True, text=True)
    return float(duration.stdout.strip())

# function to join videos in a folder into one video
def join_and_mute(sourceFolder, new_name):
    # Find all MOV files in the source directory
    source_files = [os.path.join(sourceFolder, f) for f in os.listdir(sourceFolder) if f.lower().endswith(".mov")]
    logger.trace(f"Number of .mov files found: {len(source_files)}")
    source_files.sort(key=os.path.getctime)  # sort by creation time instead of mod time
    first_file_date = datetime.datetime.fromtimestamp(os.path.getctime(source_files[0])).strftime('%Y.%m.%d')

    # Create a temporary concat file for ffmpeg
    temp_concat_file = tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.txt')
    uncompressed_video = os.path.join(sourceFolder, f"{first_file_date}.{file_descriptor}.mov")
    try:
        for sourcefile in source_files:
            temp_concat_file.write(f"file '{sourcefile}'\n")
        temp_concat_file.close()
        concat_command = [
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', temp_concat_file.name,
            '-c', 'copy', '-an', new_name  # remember '-an' to remove audio
        ]
        subprocess.run(concat_command, check=True)
        logger.success(f"Files merged successfully into {new_name}")
    finally:
        os.remove(temp_concat_file.name)

# make the silent concatenated video
join_and_mute(source_dir, uncompressed_video)

def two_pass_encode(input_file, output_file):
    '''
    Perform a two-pass encode to fit the final video near the target_size_gb (in GB).
    '''
    global TARGET_SIZE

    # get the total duration in seconds
    probe_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_file]
    duration_str = subprocess.check_output(probe_cmd).decode().strip()
    duration_sec = float(duration_str)
    
    # Compute the necessary bitrate (bits per second).
    # Multiply bytes * 8 to convert to bits; divide by video duration.
    target_bytes = int(TARGET_SIZE * .98)# target size in bytes
    video_bitrate = (target_bytes * 8) / duration_sec
    
    # Optional: set maxrate to something slightly higher to accommodate variations.
    maxrate = math.ceil(video_bitrate * 1.25)
    
    # Pass 1 (analysis only, writes to a temporary log file).
    pass1_cmd = [
        "ffmpeg", "-y", "-i", input_file, "-an", 
        "-c:v", "libx264",
        "-b:v", str(int(video_bitrate)),
        "-maxrate", str(maxrate),
        "-pass", "1",
        "-f", "mp4", 
        "/dev/null"
    ]
    subprocess.run(pass1_cmd, check=True)
    
    # Pass 2 (actual output).
    pass2_cmd = [
        "ffmpeg", "-y", "-i", input_file, "-an",
        "-c:v", "libx264",
        "-b:v", str(int(video_bitrate)),
        "-maxrate", str(maxrate),
        "-pass", "2",
        output_file
    ]
    subprocess.run(pass2_cmd, check=True)

# Run ffmpeg command to compress the concatenated video with the best CRF value
compressed_filename = os.path.join(script_dir, f"{os.path.splitext(os.path.basename(uncompressed_video))[0]}.compressed.mp4")
#compress_command = ['ffmpeg', '-y', '-i', uncompressed_video, '-c:v', 'libx264', '-crf', str(best_crf), compressed_filename]
#subprocess.run(compress_command, check=True)
two_pass_encode(uncompressed_video, compressed_filename)
logger.success(f"Video compressed successfully into {compressed_filename}")