from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from django.core.cache import cache
from chat.models import Conversation, Message
from chat.summary_service import ConversationSummaryService
import logging
    
logger = logging.getLogger(__name__)

@receiver(post_save, sender=Message)
def regenerate_summary_on_message_save(sender, instance, created, **kwargs):
    """Generate summary after new message is added"""
    if created and instance.conversation:
        conversation = instance.conversation
        
        # Only regenerate if we have enough messages
        if conversation.messages.count() >= ConversationSummaryService.MIN_MESSAGES_FOR_SUMMARY:
            ConversationSummaryService.update_conversation_summary(conversation)

@receiver(post_save, sender=Conversation)
def handle_conversation_save(sender, instance, created, **kwargs):
    """Handle conversation creation"""
    if created:
        logger.info(f"New conversation created: {instance.id}")
        # Initialize summary as stale so it's generated later
        instance.is_summary_stale = True
        Conversation.objects.filter(id=instance.id).update(is_summary_stale=True)

# Connect signals in apps.py
def ready():
    import chat.signals