import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')


app = Celery('backend')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Celery Beat Schedule
app.conf.beat_schedule = {
    'cleanup-old-conversations': {
        'task': 'chat.tasks.cleanup_old_conversations',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
        'args': (30,)  # Delete conversations older than 30 days
    },
    'generate-missing-summaries': {
        'task': 'chat.tasks.generate_missing_summaries',
        'schedule': crontab(hour=3, minute=0),  # Daily at 3 AM
    },
}

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')