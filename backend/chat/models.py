import uuid
import hashlib
from django.db import models

from authentication.models import CustomUser


class Role(models.Model):
    name = models.CharField(max_length=20, blank=False, null=False, default="user")

    def __str__(self):
        return self.name


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=100, blank=False, null=False, default="Mock title")
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    active_version = models.ForeignKey(
        "Version", null=True, blank=True, on_delete=models.CASCADE, related_name="current_version_conversations"
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    # TASK 1: Summary fields
    summary = models.TextField(
        null=True, 
        blank=True,
        help_text="Auto-generated summary of the conversation"
    )
    summary_generated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when summary was generated"
    )
    is_summary_stale = models.BooleanField(
        default=False,
        help_text="Indicates if summary needs to be regenerated"
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['is_summary_stale']),
        ]
    def __str__(self):
        return self.title

    def version_count(self):
        return self.versions.count()

    version_count.short_description = "Number of versions"


class Version(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey("Conversation", related_name="versions", on_delete=models.CASCADE)
    parent_version = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    root_message = models.ForeignKey(
        "Message", null=True, blank=True, on_delete=models.SET_NULL, related_name="root_message_versions"
    )

    def __str__(self):
        if self.root_message:
            return f"Version of `{self.conversation.title}` created at `{self.root_message.created_at}`"
        else:
            return f"Version of `{self.conversation.title}` with no root message yet"


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content = models.TextField(blank=False, null=False)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    version = models.ForeignKey("Version", related_name="messages", on_delete=models.CASCADE)

    class Meta:
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        self.version.conversation.save()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.role}: {self.content[:20]}..."


# TASK 3: File Upload Model
class UploadedFile(models.Model):
    """
    Model for storing uploaded files with metadata.
    TASK 3: File upload with duplicate detection
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='uploaded_files'
    )
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='files'
    )

    file = models.FileField(upload_to='uploads/%Y/%m/%d/')
    filename = models.CharField(max_length=255)
    file_size = models.BigIntegerField()  # in bytes
    file_type = models.CharField(max_length=50)  # e.g., 'pdf', 'docx'
    file_hash = models.CharField(max_length=64, unique=True)  # SHA256

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    # Metadata
    mime_type = models.CharField(max_length=100, null=True, blank=True)
    page_count = models.IntegerField(null=True, blank=True)  # For PDFs
    is_indexed = models.BooleanField(default=False)  # For RAG indexing

    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['user', '-uploaded_at']),
            models.Index(fields=['file_hash']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.filename} ({self.user.username})"

    @staticmethod
    def calculate_file_hash(file_obj):
        """Calculate SHA256 hash of file"""
        hash_sha256 = hashlib.sha256()
        for chunk in file_obj.chunks():
            hash_sha256.update(chunk)
        file_obj.seek(0)  # Reset file pointer
        return hash_sha256.hexdigest()

    def save(self, *args, **kwargs):
        if self.file and not self.file_hash:
            self.file_hash = self.calculate_file_hash(self.file)
        super().save(*args, **kwargs)


# TASK 4: Activity Logging Model
class ActivityLog(models.Model):
    """
    Model for logging all user activities.
    TASK 4: Activity logging and auditing
    """
    ACTION_CHOICES = [
        ('file_upload', 'File Upload'),
        ('file_delete', 'File Delete'),
        ('file_access', 'File Access'),
        ('conversation_create', 'Conversation Create'),
        ('conversation_delete', 'Conversation Delete'),
        ('conversation_edit', 'Conversation Edit'),
        ('message_send', 'Message Send'),
        ('summary_generate', 'Summary Generate'),
        ('summary_regenerate', 'Summary Regenerate'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='activity_logs'
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    resource_type = models.CharField(max_length=50)  # 'file', 'conversation', etc.
    resource_id = models.CharField(max_length=100, null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)  # Extra context
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        default='success',
        choices=[('success', 'Success'), ('failed', 'Failed')]
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
            models.Index(fields=['resource_type', 'resource_id']),
        ]

    def __str__(self):
        return f"{self.user} - {self.action} at {self.timestamp}"


# TASK 4: User Role Model for RBAC
class UserRole(models.Model):
    """
    Model for user roles - used for role-based access control.
    TASK 4: Role-based access control
    """
    ROLE_CHOICES = [
        ('user', 'Regular User'),
        ('moderator', 'Moderator'),
        ('admin', 'Administrator'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='role_profile'
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='user'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"


# TASK 4: File Permission Model for Granular Control
class FilePermission(models.Model):
    """
    Model for granular file permissions.
    TASK 4: Role-based access control
    """
    PERMISSION_CHOICES = [
        ('view', 'View'),
        ('upload', 'Upload'),
        ('delete', 'Delete'),
        ('share', 'Share'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='file_permissions'
    )
    file = models.ForeignKey(
        UploadedFile,
        on_delete=models.CASCADE,
        related_name='permissions'
    )
    permission = models.CharField(max_length=20, choices=PERMISSION_CHOICES)
    granted_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='granted_permissions'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'file', 'permission')

    def __str__(self):
        return f"{self.user.username} - {self.permission} on {self.file.filename}"
