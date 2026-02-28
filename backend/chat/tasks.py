from celery import shared_task
from django.utils.timezone import now
from datetime import timedelta
from chat.models import Conversation
from chat.summary_service import ConversationSummaryService
import logging

logger = logging.getLogger(__name__)

@shared_task(name='chat.tasks.cleanup_old_conversations')
def cleanup_old_conversations(days=30):
    """Clean up conversations older than specified days"""
    cutoff_date = now() - timedelta(days=days)
    deleted_count, _ = Conversation.objects.filter(
        created_at__lt=cutoff_date
    ).delete()
    
    logger.info(f"Cleanup task: Deleted {deleted_count} conversations")
    return {'deleted': deleted_count}

@shared_task(name='chat.tasks.generate_missing_summaries')
def generate_missing_summaries():
    """Generate summaries for conversations that don't have one"""
    conversations = Conversation.objects.filter(
        summary__isnull=True,
        messages__isnull=False
    ).distinct()[:50]  # Limit to prevent overload
    
    count = 0
    for conversation in conversations:
        if ConversationSummaryService.update_conversation_summary(conversation):
            count += 1
    
    logger.info(f"Generated summaries for {count} conversations")
    return {'generated': count}

@shared_task(name='chat.tasks.generate_conversation_summary_task')
def generate_conversation_summary_task(conversation_id):
    """Generate summary for a specific conversation"""
    try:
        conversation = Conversation.objects.get(id=conversation_id)
        return ConversationSummaryService.update_conversation_summary(conversation)
    except Conversation.DoesNotExist:
        logger.error(f"Conversation {conversation_id} not found")
        return False