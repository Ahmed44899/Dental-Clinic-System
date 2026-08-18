from django.urls import path
from .views import XRayDetailView, XRayImageView, XRayListCreateView

urlpatterns = [
    path('', XRayListCreateView.as_view(), name='xray-list-create'),
    path('<int:pk>/image/', XRayImageView.as_view(), name='xray-image'),
    path('<int:pk>/', XRayDetailView.as_view(), name='xray-detail'),
]
