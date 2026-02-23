import os
import sys
from utils import download_audio

# Test URL (a short video that is likely available)
test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ" # Rickroll is usually reliable
output_name = "test_download"

print(f"--- Testing download_audio with URL: {test_url} ---")
try:
    audio_path = download_audio(test_url, output_name)
except Exception as e:
    print(f"Unexpected Exception: {e}")
    import traceback
    traceback.print_exc()
    audio_path = None

if audio_path and os.path.exists(audio_path):
    print(f"\nSUCCESS: Audio downloaded to {audio_path}")
    # Cleanup
    # os.remove(audio_path)
else:
    print(f"\nFAILED: Audio download returned None")
    error_file = f"{output_name}.error"
    if os.path.exists(error_file):
        with open(error_file, "r") as f:
            print(f"Error captured in file: {f.read()}")
    else:
        print("No error file was created.")

print("\n--- Checking for JS Runtime (yt-dlp warning) ---")
import subprocess
result = subprocess.run(["./venv/bin/yt-dlp", "--version"], capture_output=True, text=True)
print(f"yt-dlp version: {result.stdout.strip()}")

# Test with a problematic URL if known, or just check the output for warnings
result = subprocess.run(["./venv/bin/yt-dlp", test_url, "--skip-download", "--quiet"], capture_output=True, text=True)
if "No supported JavaScript runtime could be found" in result.stderr:
    print("WARNING: Missing JavaScript runtime for yt-dlp.")
else:
    print("JavaScript runtime check passed (or no warning triggered).")
