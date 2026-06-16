from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import RegisterUserView, StaffListView, DentistListView

urlpatterns = [
    path('register/', RegisterUserView.as_view(), name='register'),
    path('staff/', StaffListView.as_view(), name='staff-list'),
    path('dentists/', DentistListView.as_view(), name='dentist-list'),
    path('login/', TokenObtainPairView.as_view(), name='login'),       # returns access + refresh token
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
]