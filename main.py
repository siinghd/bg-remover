from flask import Flask, request, jsonify, send_file
from rembg import remove
import cv2
import numpy as np
import argparse
import os
import threading
import uuid
import io
import sys
import re
import time
from threading import Thread
from datetime import datetime, timedelta
import glob
import requests
from PIL import Image
import tempfile
import cloudinary
import cloudinary.uploader
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

# Configure Cloudinary with your credentials

cloudinary.config( 
  cloud_name = "", 
  api_key = "", 
  api_secret = "" 
)
# Get the environment variable for the mode (production or development)
MODE = os.environ.get('MODE', 'development')
def remove_background_and_upload_wrapper(args):
    """
    Wrapper function to unpack arguments.
    This is necessary because ThreadPoolExecutor.map or submit
    functions can only pass a single iterable to the worker function.
    """
    return remove_background_and_upload(*args)

def process_and_upload_mints_concurrently():
    mint_data = fetch_mint_data()  # Assuming this function fetches your mints data
    if mint_data is None:
        print("No data fetched, terminating process.")
        return

    mints = mint_data.get("mints", [])
    # Prepare a list of tuples, each containing the arguments to be passed to the function
    tasks = [(mint.get("image"), mint.get("mint"), mint.get("rank")) for mint in mints if mint.get("image") and mint.get("mint") and  mint.get("rank")]

    # Number of workers (threads); adjust based on your environment and task nature
    workers = 2

    with ThreadPoolExecutor(max_workers=workers) as executor:
        # Schedule the callable to be executed for each set of arguments and return futures
        future_to_mint = {executor.submit(remove_background_and_upload_wrapper, task): task for task in tasks}
        
        for future in as_completed(future_to_mint):
            task = future_to_mint[future]
            try:
                # Wait for the result (if necessary) and handle results/errors here
                result = future.result()
            except Exception as exc:
                print(f'{task[1]} generated an exception: {exc}')
            else:
                print(f'{task[1]} image processed successfully.')
                
def fetch_mint_data():
    url = "https://moonrank.app/mints/teddies"
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raises an HTTPError if the response was an error
        data = response.json()
        return data
    except requests.RequestException as e:
        print(f"Failed to fetch mint data: {e}")
        return None

def process_and_upload_mints():
    mint_data = fetch_mint_data()
    if mint_data is None:
        print("No data fetched, terminating process.")
        return
    
    mints = mint_data.get("mints", [])
    
    for mint in mints:
        image_url = mint.get("image")
        mint_address = mint.get("mint")
        if image_url and mint_address:
            # Assuming `remove_background_and_upload` is the function you've set up to process each mint
            remove_background_and_upload(image_url, mint_address)
        else:
            print(f"Missing image URL or mint address for mint: {mint}")
            
def download_image(url):
    response = requests.get(url)
    if response.status_code == 200:
        return Image.open(io.BytesIO(response.content))
    else:
        raise Exception("Failed to download image")

from collections import Counter

def extract_background_color(image):
    # Ensure image is in RGB
    image_rgb = image.convert("RGB")
    
    # Convert the image to a sequence of pixels
    pixels = list(image_rgb.getdata())
    
    # Find the most common color
    most_common_color = Counter(pixels).most_common(1)[0][0]
    
    return most_common_color

def remove_background_and_upload(image_url, mint_address, rank):
    input_tmp_path = None
    output_tmp_path = None
    try:
        image = download_image(image_url)
        background_color = extract_background_color(image)
        background_color_hex = ''.join([f'{c:02x}' for c in background_color])

        # Extract the filename (numeric part) from the URL
        original_image_name_match = re.search(r'/(\d+)\.png$', image_url)
        original_image_name_numeric = original_image_name_match.group(1) if original_image_name_match else 'unknown'

        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as input_tmp:
            image.save(input_tmp, format='PNG')
            input_tmp_path = input_tmp.name

        output_tmp_path = f"{input_tmp_path}_no_bg.png"

        # Use your existing function to remove the background
        remove_background(input_tmp_path, output_tmp_path)

        # Ensure public_id does not end with double .png
        public_id = f"teddies/{mint_address}-teddies-{background_color_hex}-{rank}-{original_image_name_numeric}"

        with open(output_tmp_path, 'rb') as f:
            upload_result = cloudinary.uploader.upload(
                f, 
                public_id=public_id,
                resource_type='image'
            )
        print("Uploaded to Cloudinary:", upload_result['url'])
        
    except Exception as e:
        print(f"Failed to process {image_url}: {e}")
    finally:
        # Cleanup: Check if paths are not None before attempting to remove
        if input_tmp_path and os.path.exists(input_tmp_path):
            os.remove(input_tmp_path)
        if output_tmp_path and os.path.exists(output_tmp_path):
            os.remove(output_tmp_path)

        
# Function to clean up old files
def cleanup_old_files():
    while True:
        now = datetime.now()
        for filepath in glob.glob('temp_input_*') + glob.glob('temp_output_*.png'):
            file_creation_time = datetime.fromtimestamp(os.path.getmtime(filepath))
            if now - file_creation_time > timedelta(hours=1):
                try:
                    os.remove(filepath)
                    print(f"Deleted {filepath}")
                except Exception as e:
                    print(f"Error deleting file {filepath}: {e}")
        time.sleep(3600)  # Sleep for 1 hour

def remove_background(input_image_path, output_image_path, is_cli=False):
    try:
        # Read the image data
        input_image = cv2.imread(input_image_path, cv2.IMREAD_UNCHANGED)
        # Convert the image data to bytes
        input_image_bytes = cv2.imencode('.png', input_image)[1].tobytes()
        # Remove the background
        output_image_bytes = remove(input_image_bytes)
        # Convert the output bytes back to an image
        output_image = cv2.imdecode(np.frombuffer(output_image_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
        # Save the output image
        cv2.imwrite(output_image_path, output_image)
        print(f"Background removed and saved to '{output_image_path}'")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Remove the input temporary file if not in CLI mode or in development mode
        if (not is_cli):
            os.remove(input_image_path)

@app.route('/remove_background', methods=['POST'])
def remove_background_endpoint():
    unique_id = str(uuid.uuid4())
    input_image_path = f'temp_input_{unique_id}.png'
    output_image_path = f'temp_output_{unique_id}.png'

    if 'image' in request.files:
        image_file = request.files['image']
        image_file.save(input_image_path)
    elif 'image_url' in request.form:
        image_url = request.form['image_url']
        response = requests.get(image_url)
        if response.status_code == 200:
            with open(input_image_path, 'wb') as f:
                f.write(response.content)
        else:
            return jsonify({'error': 'Failed to download image from URL'}), 400
    else:
        return jsonify({'error': 'No image file or URL provided'}), 400

    thread = threading.Thread(target=remove_background, args=(input_image_path, output_image_path))
    thread.start()

    return jsonify({'id': unique_id})

@app.route('/get_result/<string:unique_id>', methods=['GET'])
def get_result(unique_id):
    output_image_path = f'temp_output_{unique_id}.png'
    if os.path.exists(output_image_path):
        with open(output_image_path, 'rb') as f:
            output_image_bytes = f.read()
        # Send the output image as a response
        output_image_file = io.BytesIO(output_image_bytes)
    
        # os.remove(output_image_path)
        return send_file(output_image_file, mimetype='image/png')
    else:
        return jsonify({'error': 'Background removal not completed yet'}), 202

def run_cli(input_image_path, output_image_path):
    remove_background(input_image_path, output_image_path, is_cli=True)
    print("Background removal is complete.")

def run_server(port, debug):
    app.run(host='127.0.0.1', port=port, debug=debug)
    
# Start the cleanup thread
cleanup_thread = Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()
if __name__ == "__main__":
    # process_and_upload_mints_concurrently()

    # Check if the first argument is "serve"; if so, run as a web server
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        parser = argparse.ArgumentParser(description="Run the Flask web server.")
        parser.add_argument("--port", type=int, default=5000, help="The port number the server should listen on.")
        parser.add_argument("--debug", action='store_true', help="Run the server in debug mode if specified, else run in production.")
        args, unknown = parser.parse_known_args()  # Ignore unknown args
        debug_mode = MODE == 'development' or args.debug
        run_server(args.port, debug_mode)
    else:
        # If not serving, assume CLI mode for background removal
        parser = argparse.ArgumentParser(description="Remove background from an image.")
        parser.add_argument("input_image_path", type=str, help="Path to the input image")
        parser.add_argument("output_image_path", type=str, help="Path to the output image")
        args = parser.parse_args()
        run_cli(args.input_image_path, args.output_image_path)