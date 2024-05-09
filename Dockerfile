FROM python:3.8

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libffi-dev \
    libevent-dev \
    build-essential \
    libjpeg-dev \
    libpng-dev \
    ffmpeg \
    pkg-config \
    libhdf5-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt
RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
RUN pip install scikit-image
RUN pip install -qr https://huggingface.co/briaai/RMBG-1.4/resolve/main/requirements.txt

# Copy the rest of your application
COPY . .

# Set environment variables
ENV FLASK_ENV=production \
    PYTHONUNBUFFERED=1

CMD ["gunicorn", "--bind", "0.0.0.0:5002", "--workers", "4", "main:app"]
