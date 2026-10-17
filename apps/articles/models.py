import uuid
from django.db import models
from django.conf import settings
from django.utils.text import slugify


class ArticleCategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = 'article_categories'
        verbose_name_plural = 'article categories'

    def __str__(self):
        return self.name


class Article(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'
        ARCHIVED = 'archived', 'Archived'

    class Language(models.TextChoices):
        ENGLISH = 'en', 'English'
        CEBUANO = 'ceb', 'Cebuano'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=255)
    content = models.TextField()
    excerpt = models.TextField(blank=True)
    category = models.ForeignKey(
        ArticleCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='articles'
    )
    language = models.CharField(max_length=5, choices=Language.choices, default=Language.ENGLISH)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='articles'
    )
    cover_image = models.URLField(blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'articles'
        ordering = ['-published_at', '-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
