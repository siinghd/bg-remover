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
import time
from threading import Thread
from datetime import datetime, timedelta
import glob

app = Flask(__name__)

# Get the environment variable for the mode (production or development)
MODE = os.environ.get('MODE', 'development')

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
    # finally:
    #     # Remove the input temporary file if not in CLI mode or in development mode
    #     if (not is_cli):
    #         os.remove(input_image_path)

@app.route('/remove_background', methods=['POST'])
def remove_background_endpoint():
    # Check if the image file is provided in the request
    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400

    # Generate unique names for temporary files
    unique_id = str(uuid.uuid4())
    input_image_path = f'temp_input_{unique_id}.png'
    output_image_path = f'temp_output_{unique_id}.png'

    # Get the image file from the request
    image_file = request.files['image']
    # Save the image file to a temporary location
    image_file.save(input_image_path)

    # Create a new thread for background removal
    thread = threading.Thread(target=remove_background, args=(input_image_path, output_image_path))
    thread.start()

    # Return the unique ID as a response
    return jsonify({'id': unique_id})

@app.route('/get_result/<string:unique_id>', methods=['GET'])
def get_result(unique_id):
    output_image_path = f'temp_output_{unique_id}.png'
    if os.path.exists(output_image_path):
        with open(output_image_path, 'rb') as f:
            output_image_bytes = f.read()
        # Send the output image as a response
        output_image_file = io.BytesIO(output_image_bytes)
    
        os.remove(output_image_path)
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