from django.urls import path
from . import views

urlpatterns = [
    path('conversations/', views.ConversationListCreateView.as_view(), name='messaging_conversations'),
    path('conversations/<uuid:pk>/', views.ConversationDetailView.as_view(), name='messaging_conversation_detail'),
    path('conversations/<uuid:pk>/messages/', views.ConversationMessagesView.as_view(), name='messaging_messages'),
    path('conversations/<uuid:pk>/mark-read/', views.ConversationMarkReadView.as_view(), name='messaging_mark_read'),
    path('unread-count/', views.UnreadCountView.as_view(), name='messaging_unread_count'),
    path('attachments/<uuid:pk>/', views.MessageAttachmentDownloadView.as_view(), name='messaging_attachment_download'),
]
