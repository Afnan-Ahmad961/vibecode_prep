from django.contrib import admin
from .models import Chat, Message, DailyUsage

@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'created_at')
    search_fields = ('title', 'user__username')

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('chat', 'role', 'created_at')
    list_filter = ('role',)

@admin.register(DailyUsage)
class DailyUsageAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'count')
    list_filter = ('date',)
