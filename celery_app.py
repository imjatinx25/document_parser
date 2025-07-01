from celery import Celery
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Celery with Valkey Glide
celery_app = Celery(
    'bank_statement_analyzer',
    broker=f"redis://{os.getenv('VALKEY_HOST', 'localhost')}:{os.getenv('VALKEY_PORT', '6379')}/0?ssl_cert_reqs=none",
    backend=f"redis://{os.getenv('VALKEY_HOST', 'localhost')}:{os.getenv('VALKEY_PORT', '6379')}/0?ssl_cert_reqs=none",
    include=['celery_tasks']
)

# Optional configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    worker_prefetch_multiplier=1,
    result_expires=900,  # Set TTL to 15 minutes (900 seconds) for task results
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10
) 