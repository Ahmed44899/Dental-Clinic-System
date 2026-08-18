from django.db import models
from django.conf import settings
from decimal import Decimal
from patients.models import PatientProfile


class Appointment(models.Model):
    DEFAULT_DURATION_MINUTES = 30
    MIN_DURATION_MINUTES = 5
    MAX_DURATION_MINUTES = 480
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
    ]

    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name='appointments')
    dentist = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='appointments')
    date_time = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(
        default=DEFAULT_DURATION_MINUTES,
        help_text='Planned chair time in minutes.',
    )
    is_emergency_overbook = models.BooleanField(default=False)
    emergency_reason = models.TextField(blank=True)
    chief_complaint = models.CharField(max_length=255, blank=True)
    diagnosis = models.TextField(blank=True)
    procedures_done = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_appointments'  # different related_name — same model, two FKs
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_time']  # most recent first
        constraints = [
            models.CheckConstraint(
                check=models.Q(duration_minutes__gte=5, duration_minutes__lte=480),
                name='appointment_duration_between_5_and_480',
            ),
            models.UniqueConstraint(
                fields=['dentist', 'date_time'],
                condition=models.Q(
                    status='scheduled', is_emergency_overbook=False
                ),
                name='unique_scheduled_dentist_start',
            ),
        ]

    def __str__(self):
        return f'{self.patient} with Dr.{self.dentist.get_full_name()} on {self.date_time}'


class Invoice(models.Model):
    CURRENCY_CHOICES = [
        ('USD', 'US Dollar'),
        ('EGP', 'Egyptian Pound'),
    ]

    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='invoice')
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='USD')
    notes = models.TextField(blank=True)

    @property
    def total(self):
        return sum(
            (item.total for item in self.line_items.all()),
            Decimal('0.00'),
        )

    @property
    def payments_total(self):
        return sum(
            (
                transaction.amount
                for transaction in self.transactions.all()
                if transaction.transaction_type == PaymentTransaction.TYPE_PAYMENT
            ),
            Decimal('0.00'),
        )

    @property
    def refunds_total(self):
        return sum(
            (
                transaction.amount
                for transaction in self.transactions.all()
                if transaction.transaction_type == PaymentTransaction.TYPE_REFUND
            ),
            Decimal('0.00'),
        )

    @property
    def net_paid(self):
        return self.payments_total - self.refunds_total

    @property
    def balance(self):
        return self.total - self.net_paid

    @property
    def status(self):
        if self.total == 0 or self.net_paid <= 0:
            return 'unpaid'
        if self.net_paid < self.total:
            return 'partial'
        return 'paid'

    def __str__(self):
        return f'Invoice for {self.appointment} — Balance: {self.balance}'


class InvoiceLineItem(models.Model):
    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name='line_items'
    )
    description = models.CharField(max_length=255)
    procedure_code = models.CharField(max_length=50, blank=True)
    quantity = models.DecimalField(max_digits=8, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_invoice_items',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        constraints = [
            models.CheckConstraint(
                check=models.Q(quantity__gt=0),
                name='invoice_item_quantity_positive',
            ),
            models.CheckConstraint(
                check=models.Q(unit_price__gte=0),
                name='invoice_item_price_nonnegative',
            ),
        ]

    @property
    def total(self):
        return self.quantity * self.unit_price


class PaymentTransaction(models.Model):
    TYPE_PAYMENT = 'payment'
    TYPE_REFUND = 'refund'
    TYPE_CHOICES = [
        (TYPE_PAYMENT, 'Payment'),
        (TYPE_REFUND, 'Refund'),
    ]
    METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('insurance', 'Insurance'),
        ('bank_transfer', 'Bank transfer'),
        ('other', 'Other'),
    ]

    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name='transactions'
    )
    transaction_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    reference = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    occurred_at = models.DateTimeField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='recorded_payment_transactions',
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['occurred_at', 'id']
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name='payment_transaction_amount_positive',
            ),
        ]
