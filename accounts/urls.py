from django.urls import path
from .views import (
    CurrentUserView,
    MembershipListView,
    DentistListView,
    LoginView,
    LogoutView,
    PasswordChangeView,
    RefreshTokenView,
    RegisterUserView,
    StaffListView,
    StaffStatusView,
)

urlpatterns = [
    path('memberships/', MembershipListView.as_view(), name='membership-list'),
    path('register/', RegisterUserView.as_view(), name='register'),
    path('staff/', StaffListView.as_view(), name='staff-list'),
    path('staff/<int:pk>/status/', StaffStatusView.as_view(), name='staff-status'),
    path('dentists/', DentistListView.as_view(), name='dentist-list'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('password/change/', PasswordChangeView.as_view(), name='password-change'),
    path('token/refresh/', RefreshTokenView.as_view(), name='token-refresh'),
    path('me/', CurrentUserView.as_view(), name='current-user'),
]
