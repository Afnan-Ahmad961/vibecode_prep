import json

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import generics, permissions, viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action

from .serializers import (
    RegisterSerializer,
    UserSerializer,
    ChatSerializer,
    MessageSerializer,
    ChatCreateSerializer,
    FollowUpMessageSerializer,
)
from .models import Chat, Message, DailyUsage
from .services.gemini import generate_project_plan, send_followup_message


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (permissions.AllowAny,)
    serializer_class = RegisterSerializer


class ProfileView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class ChatViewSet(viewsets.ModelViewSet):
    serializer_class = ChatSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Chat.objects.filter(user=self.request.user).order_by('-created_at')

    def create(self, request, *args, **kwargs):
        """
        POST /api/chats/
        Accepts project form data, calls Gemini to generate a structured plan,
        and persists the chat + both messages (user form + AI response).
        """
        # 1. Validate incoming form data
        form_serializer = ChatCreateSerializer(data=request.data)
        if not form_serializer.is_valid():
            return Response(form_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        form_data = form_serializer.validated_data

        # 2. Call Gemini to generate the project plan
        result = generate_project_plan(form_data)
        if not result["success"]:
            return Response(
                {"error": result["error"]},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        gemini_data = result["data"]

        # 3. Auto-generate the chat title from Gemini's project_explanation
        title = (
            gemini_data.get("project_explanation", {}).get("title")
            or form_data.get("description", "Untitled Project")[:100]
        )

        # 4. Create the Chat record
        chat = Chat.objects.create(user=request.user, title=title)

        # 5. Save the user's form data as the first message
        Message.objects.create(
            chat=chat,
            role="user",
            content=json.dumps(form_data),
        )

        # 6. Save Gemini's structured response as the assistant message
        Message.objects.create(
            chat=chat,
            role="assistant",
            content=json.dumps(gemini_data),
        )

        # 7. Return the full chat (with both messages) to the frontend
        serializer = ChatSerializer(chat)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def message(self, request, pk=None):
        """
        POST /api/chats/:id/message/
        Sends a follow-up message with full conversation history to Gemini.
        Rate-limited to 20 messages per user per day.
        """
        chat = self.get_object()
        user = request.user
        today = timezone.now().date()

        # Rate limiting check
        usage, _ = DailyUsage.objects.get_or_create(user=user, date=today)
        if usage.count >= 20:
            return Response(
                {"error": "Daily message limit reached (20 messages)."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Validate incoming message
        follow_up_serializer = FollowUpMessageSerializer(data=request.data)
        if not follow_up_serializer.is_valid():
            return Response(follow_up_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user_content = follow_up_serializer.validated_data["content"]

        # Fetch existing conversation history (excluding the new message)
        existing_messages = list(chat.messages.order_by("created_at"))

        # Call Gemini with full history + new user message
        result = send_followup_message(existing_messages, user_content)
        if not result["success"]:
            return Response(
                {"error": result["error"]},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Save the user message
        user_message = Message.objects.create(
            chat=chat,
            role="user",
            content=user_content,
        )

        # Save Gemini's assistant response
        assistant_message = Message.objects.create(
            chat=chat,
            role="assistant",
            content=result["data"],
        )

        # Increment daily usage
        usage.count += 1
        usage.save()

        # Return both new messages
        return Response(
            {
                "user_message": MessageSerializer(user_message).data,
                "assistant_message": MessageSerializer(assistant_message).data,
            },
            status=status.HTTP_201_CREATED,
        )
