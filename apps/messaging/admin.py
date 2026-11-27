from django.contrib import admin
from .models import Conversation, Message, MessageAttachment, MessageReadState

admin.site.register(Conversation)
admin.site.register(Message)
admin.site.register(MessageAttachment)
admin.site.register(MessageReadState)
