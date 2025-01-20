import os
import subprocess
import tempfile
import datetime
from loguru import logger
import json

# Get filename descriptor from the user
file_descriptor = input("Enter the filename descriptor in CamelCase: ")

TARGET_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
SAMPLE_DURATION = 120  # two minutes

# Set directory paths
script_dir = os.path.dirname(os.path.abspath(__file__))
source_dir = os.path.join(script_dir, "sourceVids")
uncompressed_video = os.path.join(script_dir, f"{datetime.datetime.now().strftime('%Y.%m.%d')}.{file_descriptor}.mov")

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
def join_videos(sourceFolder, new_name):
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
join_videos(source_dir, uncompressed_video)

# create sample vid for testing CRF values
sample_video = os.path.join(script_dir, f"sampleVid.mov")
sample_command = [
    'ffmpeg', '-y', '-i', uncompressed_video, '-t', str(SAMPLE_DURATION), sample_video
]
subprocess.run(sample_command, check=True)
sample_ratio = video_duration(uncompressed_video) / SAMPLE_DURATION # gives the multiplier of the sample to give the full video size

# use a binary search to find the lowest CRF value that will compress the video to the target size without going over
lowCRF, highCRF = 0, 35
estimated_sizes = {}

while lowCRF <= highCRF:
    mid_crf = (lowCRF + highCRF) // 2
    sample_uncompressed_video = video_compressor(sample_video, mid_crf)
    sample_size = os.path.getsize(sample_uncompressed_video)
    estimated_size = sample_size * sample_ratio
    logger.debug(f"Estimated size at CRF={mid_crf}: {estimated_size / (1024**3):.2f} GB")
    if estimated_size <= TARGET_SIZE:
        estimated_sizes[mid_crf] = estimated_size
        highCRF = mid_crf - 1
    else:
        logger.warning(f"Estimation of CRF={mid_crf} is {estimated_size / (1024**3):.2f} GB, which is over the target size {TARGET_SIZE / (1024**3):.2f} GB")
        lowCRF = mid_crf + 1
    logger.debug(f"Logging full estimated_sizes on each loop for debugging purposes:\n{json.dumps(estimated_sizes, indent=2)}")
    os.remove(sample_uncompressed_video) # clean up the sample file
# pretty-print the estimated sizes
logger.debug(f"ESTIMATED SIZES:\n{json.dumps(estimated_sizes, indent=2)}")

# best CRF is the lowest that made it into the estimated_sizes
if estimated_sizes:
    best_crf = min(estimated_sizes, key=estimated_sizes.get)
    logger.success(f"The recommended CRF value is {best_crf} with an estimated size of {estimated_sizes[best_crf] / (1024**3):.2f} GB")
else:
    logger.error("Failed to find an appropriate CRF value.")
    raise ValueError("Compression failed.")

# Run ffmpeg command to compress the concatenated video with the best CRF value
compressed_filename = os.path.join(script_dir, f"{os.path.splitext(os.path.basename(uncompressed_video))[0]}.compressed.mp4")
compress_command = [
    'ffmpeg', '-y', '-i', uncompressed_video, '-c:v', 'libx264', '-crf', str(best_crf), compressed_filename
]
subprocess.run(compress_command, check=True)
logger.success(f"Video compressed successfully into {compressed_filename}")