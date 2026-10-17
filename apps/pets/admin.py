from django.contrib import admin
from .models import Pet, PetImage, Favorite


class PetImageInline(admin.TabularInline):
    model = PetImage
    extra = 1


@admin.register(Pet)
class PetAdmin(admin.ModelAdmin):
    list_display = ('name', 'species', 'shelter', 'adoption_status', 'is_published', 'created_at')
    list_filter = ('species', 'adoption_status', 'is_published', 'sex', 'size')
    search_fields = ('name', 'shelter__name')
    inlines = [PetImageInline]


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ('user', 'pet', 'created_at')
