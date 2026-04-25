from django.contrib.auth.models import User
from rest_framework import serializers
from .models import Chat, Message


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('username', 'password', 'email', 'first_name', 'last_name')

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password'],
            email=validated_data.get('email', ''),
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', '')
        )
        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name')


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ('id', 'role', 'content', 'created_at')


class ChatSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Chat
        fields = ('id', 'title', 'created_at', 'messages')


class ChatCreateSerializer(serializers.Serializer):
    """Validates the project form data POSTed to /api/chats/."""
    description = serializers.CharField()
    framework = serializers.CharField(required=False, allow_blank=True, default='')
    platform = serializers.CharField()
    requirements = serializers.CharField(required=False, allow_blank=True, default='')


class FollowUpMessageSerializer(serializers.Serializer):
    """Validates a follow-up message POSTed to /api/chats/:id/message/."""
    content = serializers.CharField()
