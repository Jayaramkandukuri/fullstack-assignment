from django.core.management.base import BaseCommand
from django.utils.timezone import now
from django.db.models import Count
from datetime import timedelta
from chat.models import Conversation
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Clean up old conversations based on age'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Delete conversations older than specified days (default: 30)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )
        parser.add_argument(
            '--user',
            type=str,
            help='Only delete conversations for specific user'
        )
    
    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        user_filter = options.get('user')
        
        cutoff_date = now() - timedelta(days=days)
        queryset = Conversation.objects.filter(created_at__lt=cutoff_date)
        
        if user_filter:
            queryset = queryset.filter(user__username=user_filter)
        
        count = queryset.count()
        
        if count == 0:
            self.stdout.write(
                self.style.WARNING('No conversations found matching criteria')
            )
            return
        
        self.stdout.write(f"Conversations to delete: {count}\n")
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No deletions made\n'))
            for conv in queryset[:5]:
                self.stdout.write(
                    f"  - {conv.title} ({conv.messages.count()} messages)"
                )
            return
        
        confirm = input(f"Delete {count} conversations? (yes/no): ")
        
        if confirm.lower() == 'yes':
            deleted_count = queryset.delete()[0]
            self.stdout.write(
                self.style.SUCCESS(f'✓ Deleted {deleted_count} conversations')
            )
        else:
            self.stdout.write(self.style.WARNING('Deletion cancelled'))