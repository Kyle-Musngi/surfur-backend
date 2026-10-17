from django.contrib import admin
from .models import Article, ArticleCategory


@admin.register(ArticleCategory)
class ArticleCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'language', 'status', 'published_at', 'author')
    list_filter = ('status', 'language', 'category')
    search_fields = ('title', 'content')
    prepopulated_fields = {'slug': ('title',)}
