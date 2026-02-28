from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import serializers

from chat.models import Conversation, Message, Role, Version

# file upload related serializer
from chat.models import UploadedFile


def should_serialize(validated_data, field_name) -> bool:
    if validated_data.get(field_name) is not None:
        return True


class TitleSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=100, required=True)


class VersionTimeIdSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    created_at = serializers.DateTimeField()


class MessageSerializer(serializers.ModelSerializer):
    role = serializers.SlugRelatedField(slug_field="name", queryset=Role.objects.all())

    class Meta:
        model = Message
        fields = [
            "id",  # DB
            "content",
            "role",  # required
            "created_at",  # DB, read-only
        ]
        read_only_fields = ["id", "created_at", "version"]

    def create(self, validated_data):
        message = Message.objects.create(**validated_data)
        return message

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["versions"] = []  # add versions field
        return representation


class VersionSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True)
    active = serializers.SerializerMethodField()
    conversation_id = serializers.UUIDField(source="conversation.id")
    created_at = serializers.SerializerMethodField()

    class Meta:
        model = Version
        fields = [
            "id",
            "conversation_id",  # DB
            "root_message",
            "messages",
            "active",
            "created_at",  # DB, read-only
            "parent_version",  # optional
        ]
        read_only_fields = ["id", "conversation"]

    @staticmethod
    def get_active(obj):
        return obj == obj.conversation.active_version

    @staticmethod
    def get_created_at(obj):
        if obj.root_message is None:
            return timezone.localtime(obj.conversation.created_at)
        return timezone.localtime(obj.root_message.created_at)

    def create(self, validated_data):
        messages_data = validated_data.pop("messages")
        version = Version.objects.create(**validated_data)
        for message_data in messages_data:
            Message.objects.create(version=version, **message_data)

        return version

    def update(self, instance, validated_data):
        instance.conversation = validated_data.get("conversation", instance.conversation)
        instance.parent_version = validated_data.get("parent_version", instance.parent_version)
        instance.root_message = validated_data.get("root_message", instance.root_message)
        if not any(
            [
                should_serialize(validated_data, "conversation"),
                should_serialize(validated_data, "parent_version"),
                should_serialize(validated_data, "root_message"),
            ]
        ):
            raise ValidationError(
                "At least one of the following fields must be provided: conversation, parent_version, root_message"
            )
        instance.save()

        messages_data = validated_data.pop("messages", [])
        for message_data in messages_data:
            if "id" in message_data:
                message = Message.objects.get(id=message_data["id"], version=instance)
                message.content = message_data.get("content", message.content)
                message.role = message_data.get("role", message.role)
                message.save()
            else:
                Message.objects.create(version=instance, **message_data)

        return instance


class ConversationSerializer(serializers.ModelSerializer):
    versions = VersionSerializer(many=True)

    class Meta:
        model = Conversation
        fields = [
            "id",  # DB
            "title",  # required
            "active_version",
            "versions",  # optional
            "modified_at",  # DB, read-only
        ]

    def create(self, validated_data):
        versions_data = validated_data.pop("versions", [])
        conversation = Conversation.objects.create(**validated_data)
        for version_data in versions_data:
            version_serializer = VersionSerializer(data=version_data)
            if version_serializer.is_valid():
                version_serializer.save(conversation=conversation)

        return conversation

    def update(self, instance, validated_data):
        instance.title = validated_data.get("title", instance.title)
        active_version_id = validated_data.get("active_version", instance.active_version)
        if active_version_id is not None:
            active_version = Version.objects.get(id=active_version_id)
            instance.active_version = active_version
        instance.save()

        versions_data = validated_data.pop("versions", [])
        for version_data in versions_data:
            if "id" in version_data:
                version = Version.objects.get(id=version_data["id"], conversation=instance)
                version_serializer = VersionSerializer(version, data=version_data)
            else:
                version_serializer = VersionSerializer(data=version_data)
            if version_serializer.is_valid():
                version_serializer.save(conversation=instance)

        return instance


class ConversationSummarySerializer(serializers.ModelSerializer):
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            'id',
            'title',
            'summary',
            'summary_generated_at',
            'is_summary_stale',
            'message_count',
            'created_at',
        ]

    def get_message_count(self, obj):
        from chat.models import Message
        return Message.objects.filter(
            version__conversation=obj
        ).count()


class UploadedFileSerializer(serializers.ModelSerializer):
    """Serializer for UploadedFile model.

    When a file is provided we calculate its hash and check for duplicates so
    the same file cannot be uploaded more than once.  Some metadata is also
    populated automatically (filename, size, type, owner).
    """

    class Meta:
        model = UploadedFile
        # expose all relevant metadata fields so the frontend can render them
        fields = [
            "id",
            "user",
            "conversation",
            "file",
            "filename",
            "file_size",
            "file_type",
            "file_hash",
            "status",
            "uploaded_at",
            "processed_at",
            "error_message",
            "mime_type",
            "page_count",
            "is_indexed",
        ]
        read_only_fields = [
            "id",
            "user",
            "file_hash",
            "status",
            "uploaded_at",
            "processed_at",
            "error_message",
            "mime_type",
            "page_count",
            "is_indexed",
        ]

    def validate_file(self, value):
        """Compute SHA256 of the incoming file and reject duplicates."""
        # calculate and then rewind pointer so the same file object can still be
        # saved by Django's storage backend
        file_hash = UploadedFile.calculate_file_hash(value)
        value.seek(0)
        if UploadedFile.objects.filter(file_hash=file_hash).exists():
            raise serializers.ValidationError("A file with the same content has already been uploaded.")
        return value

    def create(self, validated_data):
        # automatically populate some meta fields that the client doesn't need
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            validated_data["user"] = request.user

        file_obj = validated_data.get("file")
        if file_obj:
            validated_data["filename"] = file_obj.name
            validated_data["file_size"] = file_obj.size
            # simple type extraction based on extension
            if "." in file_obj.name:
                validated_data["file_type"] = file_obj.name.rsplit('.', 1)[1]
            else:
                validated_data["file_type"] = ""

        return super().create(validated_data)