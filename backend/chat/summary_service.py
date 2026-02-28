import logging
import json
from typing import Optional
from datetime import timedelta
from django.utils.timezone import now
from django.core.cache import cache
from src.libs import openai

logger = logging.getLogger(__name__)

class ConversationSummaryService:
    """Service for generating and managing conversation summaries"""
    
    MAX_TOKENS = 200
    SUMMARY_CACHE_TIMEOUT = 3600  # 1 hour
    MIN_MESSAGES_FOR_SUMMARY = 3
    
    @staticmethod
    def generate_summary(conversation) -> Optional[str]:
        """
        Generate summary for a conversation using OpenAI
        
        Args:
            conversation: Conversation instance
            
        Returns:
            Generated summary string or None
        """
        try:
            # Check if conversation has enough messages
            message_count = conversation.messages.count()
            if message_count < ConversationSummaryService.MIN_MESSAGES_FOR_SUMMARY:
                logger.info(f"Conversation {conversation.id} has insufficient messages for summary")
                return None
            
            # Fetch all messages for context
            messages = conversation.messages.all().order_by('created_at')
            
            # Build context from messages
            context = "\n".join([
                f"{'User' if msg.role.name == 'user' else 'Assistant'}: {msg.content[:200]}"
                for msg in messages[:10]  # Limit to last 10 messages
            ])
            
            # Call OpenAI API
            response = openai.ChatCompletion.create(
                engine="gpt-35-turbo",  # Azure deployment name
                messages=[
                    {
                        "role": "system",
                        "content": "Provide a concise 2-3 sentence summary of the conversation."
                    },
                    {
                        "role": "user",
                        "content": f"Conversation to summarize:\n\n{context}"
                    }
                ],
                max_tokens=ConversationSummaryService.MAX_TOKENS,
                temperature=0.3
            )
            
            summary = response['choices'][0]['message']['content'].strip()
            logger.info(f"Successfully generated summary for conversation {conversation.id}")
            return summary
            
        except openai.error.OpenAIError as e:
            logger.error(f"OpenAI API error while generating summary: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in summary generation: {str(e)}")
            return None
    
    @staticmethod
    def update_conversation_summary(conversation) -> bool:
        """
        Update conversation with generated summary
        
        Args:
            conversation: Conversation instance
            
        Returns:
            True if successful, False otherwise
        """
        try:
            summary = ConversationSummaryService.generate_summary(conversation)
            
            if summary:
                conversation.summary = summary
                conversation.summary_generated_at = now()
                conversation.is_summary_stale = False
                conversation.save(update_fields=['summary', 'summary_generated_at', 'is_summary_stale'])
                
                # Cache the summary
                cache.set(
                    f"conversation_summary_{conversation.id}",
                    summary,
                    ConversationSummaryService.SUMMARY_CACHE_TIMEOUT
                )
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error updating conversation summary: {str(e)}")
            return False
    
    @staticmethod
    def get_cached_summary(conversation) -> Optional[str]:
        """Retrieve summary from cache or database"""
        cache_key = f"conversation_summary_{conversation.id}"
        cached = cache.get(cache_key)
        
        if cached:
            return cached
        
        if conversation.summary:
            cache.set(cache_key, conversation.summary, 
                     ConversationSummaryService.SUMMARY_CACHE_TIMEOUT)
            return conversation.summary
        
        return None
    
    @staticmethod
    def mark_summary_stale(conversation):
        """Mark summary as needing regeneration (e.g., when conversation is edited)"""
        conversation.is_summary_stale = True
        conversation.save(update_fields=['is_summary_stale'])
        cache.delete(f"conversation_summary_{conversation.id}")