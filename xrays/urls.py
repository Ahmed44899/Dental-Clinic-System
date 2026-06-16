from django.urls import path
from .views import XRayListCreateView, XRayDetailView

urlpatterns = [
    path('', XRayListCreateView.as_view(), name='xray-list-create'),
    path('<int:pk>/', XRayDetailView.as_view(), name='xray-detail'),
]