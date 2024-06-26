from flask import Flask, request, jsonify, send_file
import numpy as np
import argparse
import os
import threading
import uuid
import io
import sys
import re
import time
from datetime import datetime, timedelta
import glob
import requests
from PIL import Image
import tempfile
import boto3
from transformers import pipeline

app = Flask(__name__)

# # Configure R2 with your credentials
# endpoint_url = ''
# access_key_id = ''
# secret_access_key = ''
# region_name = 'auto'  # Choose as per your location setup in R2
# bucket_name = ''

# # Create an S3 client
# s3 = boto3.client(
#     service_name='s3',
#     endpoint_url=endpoint_url,
#     aws_access_key_id=access_key_id,
#     aws_secret_access_key=secret_access_key,
#     region_name=region_name
# )

# Get the environment variable for the mode (production or development)
MODE = os.environ.get('MODE', 'development')

def process_and_upload_mints():
    mint_data = fetch_mint_data()  # Assuming this function fetches your mints data
    if mint_data is None:
        print("No data fetched, terminating process.")
        return

    mints = mint_data.get("mints", [])

    for mint in mints:
        image_url = mint.get("image")
        mint_address = mint.get("mint")
        rank = mint.get("rank")
        rank_explain = mint.get("rank_explain")
        if image_url and mint_address and rank:
            remove_background_and_upload(image_url, mint_address, rank,rank_explain)
        else:
            print(f"Missing image URL, mint address, or rank for mint: {mint}")
        
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

def download_image(url):
    response = requests.get(url)
    if response.status_code == 200:
        return Image.open(io.BytesIO(response.content))
    else:
        raise Exception("Failed to download image")

def extract_background_color(image, crop_size=(10, 10)):
    try:
        # Ensure the image is in RGB format
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Crop the image to the top-left corner based on crop_size
        crop = image.crop((0, 0, crop_size[0], crop_size[1]))  # (left, upper, right, lower)

        # Convert the cropped image to a numpy array
        np_crop = np.array(crop)

        # Calculate the mean color of the cropped area
        mean_color = np.mean(np_crop, axis=(0, 1)).astype(int)
        
        # Convert numpy array to tuple of RGB values
        background_color = tuple(mean_color)

        return background_color
    except Exception as e:
        print(f"Failed to extract background color from crop due to error: {str(e)}")
        return None
# def remove_background_task(image_url, unique_id, webhook_url=None, input_image_data=None):
#     try:
#         redis_client.set(f"{unique_id}_status", "processing", ex=3600)
#         if input_image_data is None and image_url is not None:
#             response = requests.get(image_url)
#             if response.status_code == 200:
#                 input_image_data = response.content
#             else:
#                 raise Exception(f"Failed to download image from URL: {image_url}")
#         elif input_image_data is None:
#             raise Exception("No image data or URL provided")
#         # Convert input image data to PIL Image
#         input_image = Image.open(io.BytesIO(input_image_data))

#         # Initialize the pipeline
#         pipe = pipeline("image-segmentation", model="briaai/RMBG-1.4", trust_remote_code=True)
#         # Use the pipeline to remove the background
#         # This will return a PIL Image with the background removed
#         try:
#             # Use the pipeline to remove the background
#             output_image = pipe(input_image)
#         except Exception as e:
#             print(f"Error removing background: {str(e)}")
#             raise
#         # Convert output image to bytes
#         output_image_bytes = io.BytesIO()
#         output_image.save(output_image_bytes, format='PNG')
#         output_image_bytes.seek(0)

#         # Upload the processed image to Cloudflare R2
#         s3.upload_fileobj(output_image_bytes, bucket_name, f"processed_images/{unique_id}.png")

#         # Generate a presigned URL for the processed image
#         presigned_url = s3.generate_presigned_url(
#             'get_object',
#             Params={'Bucket': bucket_name, 'Key': f"processed_images/{unique_id}.png"},
#             ExpiresIn=3600  # URL expires in 1 hour
#         )

#         # Set the presigned URL and status in Redis with an expiration of 1 hour
#         redis_client.set(f"{unique_id}_url", presigned_url, ex=3600)
#         redis_client.set(f"{unique_id}_status", "completed", ex=3600)

#         # Send a webhook notification if webhook_url is provided
#         if webhook_url:
#             payload = {
#                 'id': unique_id,
#                 'status': 'completed',
#                 'image_url': presigned_url
#             }
#             requests.post(webhook_url, json=payload)

#         print(f"Background removed for image: {unique_id}")
#     except Exception as e:
#         print(f"Error: {e}")
#         redis_client.set(f"{unique_id}_status", "failed", ex=3600)

#         # Send a webhook notification if webhook_url is provided
#         if webhook_url:
#             payload = {
#                 'id': unique_id,
#                 'status': 'failed'
#             }
#             requests.post(webhook_url, json=payload)
def remove_background_and_upload(image_url, mint_address, rank,rank_explain):
    input_tmp_path = None
    output_tmp_path = None
    try:
        image = download_image(image_url)
        background_color = extract_background_color(image)
        background_color_hex = ''.join([f'{c:02x}' for c in background_color])
        print(f"Background color: {background_color_hex}")

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
        public_id = f"teddies/{mint_address}-teddies-{background_color_hex}-{rank}-{original_image_name_numeric}.png"

        with open(output_tmp_path, 'rb') as f:
            s3.upload_fileobj(
                io.BytesIO(f.read()),
                bucket_name,
                public_id
            )
        print(f"Uploaded to Cloudflare R2: {public_id}")
        
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
        # Initialize the pipeline
        pipe = pipeline("image-segmentation", model="briaai/RMBG-1.4", trust_remote_code=True)
        
        # Use the pipeline to remove the background
        # This will return a PIL Image with the background removed
        pillow_image = pipe(input_image_path)
        
        # Ensure the output file extension is .png
        output_image_path = os.path.splitext(output_image_path)[0] + ".png"
        
        # Save the output image as PNG using PIL
        pillow_image.save(output_image_path, "PNG")
        
        print(f"Background removed and saved to '{output_image_path}'")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Remove the input temporary file if not in CLI mode or in development mode
        if not is_cli:
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
        return send_file(output_image_file, mimetype='image/png')
    else:
        return jsonify({'error': 'Background removal not completed yet'}), 202

def run_cli(input_image_path, output_image_path):
    remove_background(input_image_path, output_image_path, is_cli=True)
    print("Background removal is complete.")

def run_server(port, debug):
    app.run(host='127.0.0.1', port=port, debug=debug)
    
if __name__ == "__main__":
    try:
        # process_and_upload_mints()
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
    except Exception as e:
        print(f"An error occurred during execution: {e}")
        # Log the exception traceback for debugging purposes
        import traceback
        traceback.print_exc()