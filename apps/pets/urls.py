from django.urls import path
from . import views

urlpatterns = [
    path('', views.PetListView.as_view(), name='pet_list'),
    path('favorites/', views.FavoriteListView.as_view(), name='favorite_list'),
    path('favorites/<uuid:pet_id>/', views.FavoriteToggleView.as_view(), name='favorite_toggle_direct'),
    path('favorites/<uuid:pet_id>/toggle/', views.FavoriteToggleView.as_view(), name='favorite_toggle'),
    path('shelter/<slug:shelter_slug>/', views.ShelterPetListView.as_view(), name='shelter_pet_list'),
    path('shelter/<slug:shelter_slug>/create/', views.ShelterPetCreateView.as_view(), name='shelter_pet_create'),
    path('<uuid:pk>/', views.PetDetailView.as_view(), name='pet_detail'),
    path('<uuid:pk>/update/', views.PetUpdateView.as_view(), name='pet_update'),
]
