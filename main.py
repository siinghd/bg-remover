from flask import Flask, request, jsonify
import os
import uuid
import requests
import boto3
from transformers import pipeline ,is_torch_available
from celery import Celery
import redis
from dotenv import load_dotenv
import torch
import io
from PIL import Image

load_dotenv()  # Load environment variables from .env file

app = Flask(__name__)

# Configure Celery
app.config['broker_url'] = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
app.config['result_backend'] = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

# Initialize Celery
celery = Celery(app.name, broker=app.config['broker_url'])
celery.conf.update(app.config)

# Configure priority queues
celery.conf.task_routes = {
    'main.remove_background_task_paid': {'queue': 'paid'},
    'main.remove_background_task_free': {'queue': 'free'},
}

# Set queue priorities
celery.conf.worker_prefetch_multiplier = 1
celery.conf.task_acks_late = True
celery.conf.worker_consumer_strategy = 'custom'


# Initialize Redis
redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
redis_client = redis.from_url(redis_url)

# Configure R2 with your credentials
endpoint_url = os.environ.get('R2_ENDPOINT_URL')
access_key_id = os.environ.get('R2_ACCESS_KEY_ID')
secret_access_key = os.environ.get('R2_SECRET_ACCESS_KEY')
region_name = os.environ.get('R2_REGION_NAME', 'auto')
bucket_name = os.environ.get('R2_BUCKET_NAME')

# Create an S3 client
s3 = boto3.client(
    service_name='s3',
    endpoint_url=endpoint_url,
    aws_access_key_id=access_key_id,
    aws_secret_access_key=secret_access_key,
    region_name=region_name
)

@celery.task(name='main.remove_background_task_paid')
def remove_background_task_paid(image_url, unique_id, webhook_url=None, input_image_data=None):
    return remove_background_task(image_url, unique_id, webhook_url, input_image_data)

@celery.task(name='main.remove_background_task_free')
def remove_background_task_free(image_url, unique_id, webhook_url=None, input_image_data=None):
    return remove_background_task(image_url, unique_id, webhook_url, input_image_data)

def remove_background_task(image_url, unique_id, webhook_url=None, input_image_data=None):
    try:
        redis_client.set(f"{unique_id}_status", "processing", ex=3600)
        if input_image_data is None and image_url is not None:
            response = requests.get(image_url)
            if response.status_code == 200:
                input_image_data = response.content
            else:
                raise Exception(f"Failed to download image from URL: {image_url}")
        elif input_image_data is None:
            raise Exception("No image data or URL provided")
        # Convert input image data to PIL Image
        input_image = Image.open(io.BytesIO(input_image_data))

        # Initialize the pipeline
        pipe = pipeline("image-segmentation", model="briaai/RMBG-1.4", trust_remote_code=True, force_download=True)
        # Use the pipeline to remove the background
        # This will return a PIL Image with the background removed
        try:
            # Use the pipeline to remove the background
            output_image = pipe(input_image)
        except Exception as e:
            print(f"Error removing background: {str(e)}")
            raise
        # Convert output image to bytes
        output_image_bytes = io.BytesIO()
        output_image.save(output_image_bytes, format='PNG')
        output_image_bytes.seek(0)

        # Upload the processed image to Cloudflare R2
        s3.upload_fileobj(output_image_bytes, bucket_name, f"processed_images/{unique_id}.png")

        # Generate a presigned URL for the processed image
        presigned_url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': f"processed_images/{unique_id}.png"},
            ExpiresIn=3600  # URL expires in 1 hour
        )

        # Set the presigned URL and status in Redis with an expiration of 1 hour
        redis_client.set(f"{unique_id}_url", presigned_url, ex=3600)
        redis_client.set(f"{unique_id}_status", "completed", ex=3600)

        # Send a webhook notification if webhook_url is provided
        if webhook_url:
            payload = {
                'id': unique_id,
                'status': 'completed',
                'image_url': presigned_url
            }
            requests.post(webhook_url, json=payload)

    except Exception as e:
        print(f"Error: {e}")
        redis_client.set(f"{unique_id}_status", "failed", ex=3600)

        # Send a webhook notification if webhook_url is provided
        if webhook_url:
            payload = {
                'id': unique_id,
                'status': 'failed'
            }
            requests.post(webhook_url, json=payload)

@app.route('/remove_background', methods=['POST'])
def remove_background_endpoint():
    unique_id = str(uuid.uuid4())
    webhook_url = request.form.get('webhook_url')
    is_paid_user = request.form.get('is_paid_user', 'false').lower() == 'true'

    if 'image' in request.files:
        image_file = request.files['image']
        input_image_data = image_file.read()
        if is_paid_user:
            remove_background_task_paid.delay(None, unique_id, webhook_url, input_image_data)
        else:
            remove_background_task_free.delay(None, unique_id, webhook_url, input_image_data)
    elif 'image_url' in request.form:
        image_url = request.form['image_url']
        if is_paid_user:
            remove_background_task_paid.delay(image_url, unique_id, webhook_url)
        else:
            remove_background_task_free.delay(image_url, unique_id, webhook_url)
    else:
        return jsonify({'error': 'No image file or URL provided'}), 400

    return jsonify({'id': unique_id})

@app.route('/get_result', methods=['GET'])
def get_result():
    unique_ids = request.args.getlist('id')
    if not unique_ids:
        return jsonify({'error': 'No IDs provided'}), 400

    results = []
    for unique_id in unique_ids:
        status = redis_client.get(f"{unique_id}_status")
        image_url = redis_client.get(f"{unique_id}_url")
        if status is None:
            result = {'id': unique_id, 'error': 'Invalid ID'}
        elif status.decode() == "completed":
            result = {
                'id': unique_id,
                'status': 'completed',
                'image_url': image_url.decode()
            }
        elif status.decode() == "failed":
            result = {'id': unique_id, 'error': 'Background removal failed'}
        else:
            result = {'id': unique_id, 'status': 'processing'}

        results.append(result)

    return jsonify(results)
    


def start_celery_worker():
    command = [
        'celery', '-A', 'main.celery', 'worker',
        '--loglevel=info', '--concurrency=4','--pool=gevent' ,'-Q', 'paid,free'
    ]
    subprocess.Popen(command)

if __name__ == "__main__":
    port = int(os.getenv('PORT', 5000))
    # start_celery_worker()

    # Start the Flask app
    app.run(host='127.0.0.1', port=port, debug=True)