from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import generics, permissions, viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action
from .serializers import RegisterSerializer, UserSerializer, ChatSerializer, MessageSerializer
from .models import Chat, Message, DailyUsage

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

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def message(self, request, pk=None):
        chat = self.get_object()
        user = request.user
        today = timezone.now().date()

        # Basic rate limiting logic
        usage, created = DailyUsage.objects.get_or_create(user=user, date=today)
        if usage.count >= 20:  # Example daily limit
            return Response(
                {"error": "Daily message limit reached (20 messages)."}, 
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        serializer = MessageSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(chat=chat)
            
            # Increment usage count
            usage.count += 1
            usage.save()
            
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
