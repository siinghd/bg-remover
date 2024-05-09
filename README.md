
# Background Removal Microservice

This is a Flask-based microservice that provides an API for removing the background from images using the RMBG model from Hugging Face. The service uses Celery for asynchronous task processing and Redis for storing task status and results. The processed images are stored in a Cloudflare R2 bucket.

## Prerequisites

Before running this application, make sure you have the following prerequisites installed:

- Docker
- Docker Compose

## Environment Variables

The following environment variables need to be set:

- `PORT`: The port on which the Flask app will run (default: `5000`)
- `REDIS_URL`: The URL of the Redis instance
- `R2_ENDPOINT_URL`: The endpoint URL for Cloudflare R2
- `R2_ACCESS_KEY_ID`: The access key ID for Cloudflare R2
- `R2_SECRET_ACCESS_KEY`: The secret access key for Cloudflare R2
- `R2_REGION_NAME`: The region name for Cloudflare R2 (default: `auto`)
- `R2_BUCKET_NAME`: The name of the Cloudflare R2 bucket

## Running the Application

1. Build the Docker images:

```
docker-compose build
```

2. Run the application using Docker Compose:

```
docker-compose up
```

This will start the Flask app and the Celery worker.

## API Endpoints

### `/remove_background` (POST)

This endpoint accepts an image file or a URL to an image, and returns a unique ID for the background removal task.

**Request Parameters**:
- `image` (file): The image file to be processed
- `image_url` (string): The URL of the image to be processed
- `webhook_url` (string, optional): The URL to receive a webhook notification when the task is completed or failed
- `is_paid_user` (boolean, default: `false`): Indicates whether the user is a paid user or not. Paid users have higher priority in the task queue.

**Response**:
- `id` (string): The unique ID of the background removal task

### `/get_result` (GET)

This endpoint retrieves the status and result of one or more background removal tasks.

**Request Parameters**:
- `id` (string, multiple): The unique ID(s) of the background removal task(s), passed as query parameters (e.g., `/get_result?id=uuid1&id=uuid2&id=uuid3`)

**Responses**:
- `200 OK`: A list of results, each containing the following fields:
  - `id` (string): The unique ID of the task
  - `status` (string): The status of the task (`processing`, `completed`, or `failed`)
  - `image_url` (string, if `status` is `completed`): The URL of the processed image
  - `error` (string, if `status` is `failed`): The error message
- `400 Bad Request`: No IDs were provided in the request

## Deployment

The application is designed to be deployed using Docker and Docker Compose. The provided `docker-compose.yml` file includes configurations for both the Flask app and the Celery worker.

To deploy the application, follow these steps:

1. Set the required environment variables.
2. Build the Docker images using `docker-compose build`.
3. Start the containers using `docker-compose up`.

## License

This project is licensed under the [MIT License](LICENSE).
