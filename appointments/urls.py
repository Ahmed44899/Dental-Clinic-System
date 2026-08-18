from django.urls import path
from .views import (
    AppointmentDetailView,
    AppointmentListCreateView,
    InvoiceDetailView,
    InvoiceLineItemDetailView,
    InvoiceLineItemListCreateView,
    PaymentTransactionListCreateView,
)
from .financial_reports import FinancialReportView

urlpatterns = [
    path('', AppointmentListCreateView.as_view(), name='appointment-list-create'),
    path('<int:pk>/', AppointmentDetailView.as_view(), name='appointment-detail'),
    path('<int:pk>/invoice/', InvoiceDetailView.as_view(), name='invoice-detail'),
    path('<int:pk>/invoice/items/', InvoiceLineItemListCreateView.as_view(), name='invoice-item-list-create'),
    path('<int:pk>/invoice/items/<int:item_pk>/', InvoiceLineItemDetailView.as_view(), name='invoice-item-detail'),
    path('<int:pk>/invoice/transactions/', PaymentTransactionListCreateView.as_view(), name='payment-transaction-list-create'),
    path('financial-reports/', FinancialReportView.as_view(), name='financial-report'),
]
