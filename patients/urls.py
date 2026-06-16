from django.urls import path
from .views import PatientListCreateView, PatientDetailView, PatientSearchView

urlpatterns = [
    path('', PatientListCreateView.as_view(), name='patient-list-create'),
    path('search/', PatientSearchView.as_view(), name='patient-search'),
    path('<int:pk>/', PatientDetailView.as_view(), name='patient-detail'),
]