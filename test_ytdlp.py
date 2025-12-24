# test_ytdlp.py
import subprocess

cmd = [
    "yt-dlp",
    "--no-playlist",
    "-x",
    "--audio-format",
    "wav",
    "https://www.youtube.com/watch?v=EXF1Aq2xDr4",
]

print("CMD:", " ".join(cmd))

subprocess.run(cmd)