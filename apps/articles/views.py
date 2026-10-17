from rest_framework import generics, permissions
from rest_framework import serializers
from .models import Article, ArticleCategory


class ArticleCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ArticleCategory
        fields = ('id', 'name', 'slug', 'description')


class ArticleListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = Article
        fields = (
            'id', 'title', 'slug', 'excerpt', 'category_name',
            'language', 'cover_image', 'published_at',
        )


class ArticleDetailSerializer(serializers.ModelSerializer):
    category = ArticleCategorySerializer(read_only=True)
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = Article
        fields = (
            'id', 'title', 'slug', 'content', 'excerpt',
            'category', 'language', 'cover_image',
            'author_name', 'published_at',
        )

    def get_author_name(self, obj):
        return obj.author.full_name if obj.author else 'AmponCebu Team'


class ArticleListView(generics.ListAPIView):
    serializer_class = ArticleListSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Article.objects.filter(status='published').select_related(
            'category'
        ).order_by('-published_at')


class ArticleDetailView(generics.RetrieveAPIView):
    serializer_class = ArticleDetailSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'slug'

    def get_queryset(self):
        return Article.objects.filter(status='published').select_related('category', 'author')
