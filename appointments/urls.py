from django.urls import path
from .views import AppointmentListCreateView, AppointmentDetailView, InvoiceDetailView

urlpatterns = [
    path('', AppointmentListCreateView.as_view(), name='appointment-list-create'),
    path('<int:pk>/', AppointmentDetailView.as_view(), name='appointment-detail'),
    path('<int:pk>/invoice/', InvoiceDetailView.as_view(), name='invoice-detail'),
]