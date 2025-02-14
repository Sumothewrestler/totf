# models.py
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Count, F, Q
from datetime import date, timedelta, time
from django.core.validators import MinValueValidator
from decimal import Decimal

class Category(models.Model):
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Categories"

class Activity(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Activities"

class TimeEntry(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='time_entries')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.IntegerField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    is_manually_entered = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    last_modified_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='modified_entries'
    )

    def clean(self):
        if self.end_time and self.start_time > self.end_time:
            raise ValidationError("End time must be after start time")
        
        if self.end_time:
            # Check for overlapping entries
            overlapping = TimeEntry.objects.filter(
                activity=self.activity,
                user=self.user,
                start_time__lte=self.end_time,
                end_time__gte=self.start_time
            ).exclude(pk=self.pk)
            
            if overlapping.exists():
                raise ValidationError("This time entry overlaps with an existing entry")

    def save(self, *args, **kwargs):
        if self.end_time:
            duration = self.end_time - self.start_time
            self.duration_minutes = duration.total_seconds() // 60
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.activity.name} - {self.start_time}"

class GoalStatus(models.TextChoices):
    FOCUS = 'FOCUS', 'Focus'
    UNFOCUSED = 'UNFOCUSED', 'Unfocused' 
    DONE = 'DONE', 'Done'
    ABANDONED = 'ABANDONED', 'Abandoned'

class ProcessStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    DONE = 'DONE', 'Done'

class Goal(models.Model):
    name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=10,
        choices=GoalStatus.choices,
        default=GoalStatus.UNFOCUSED
    )
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.status}"

    class Meta:
        ordering = ['sort_order', '-created_at']

class SubProcess(models.Model):
    name = models.CharField(max_length=255)
    goal = models.ForeignKey(
        Goal,
        on_delete=models.CASCADE,
        related_name='sub_processes'
    )
    estimated_days = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=Decimal('0.1'),
        validators=[MinValueValidator(Decimal('0.1'))],
        help_text="Estimated number of days needed to complete this process (minimum 0.1)"
    )
    status = models.CharField(
        max_length=10,
        choices=ProcessStatus.choices,
        default=ProcessStatus.PENDING
    )
    focus = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['sort_order', '-created_at'] 

class WorkHead(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)  # New field
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({'Active' if self.is_active else 'Inactive'})"

    class Meta:
        ordering = ['name']

class WorkUpdate(models.Model):
    date = models.DateField(default=timezone.now)
    head = models.ForeignKey(
        WorkHead, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='updates'
    )
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.date} - {self.head.name if self.head else 'No Head'}"

    class Meta:
        ordering = ['-date', '-created_at']

class Task(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]

    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('URGENT', 'Urgent'),
    ]

    ESTIMATE_UNIT_CHOICES = [
        ('MINUTES', 'Minutes'),
        ('HOURS', 'Hours'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING'
    )
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default='MEDIUM'
    )
    task_date = models.DateField(default=date.today)
    task_time = models.TimeField(null=True, blank=True)
    estimated_time = models.PositiveIntegerField(null=True, blank=True)
    estimate_unit = models.CharField(
        max_length=10,
        choices=ESTIMATE_UNIT_CHOICES,
        default='MINUTES',
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-task_date', 'task_time', '-priority']
        indexes = [
            models.Index(fields=['status', 'task_date']),
            models.Index(fields=['task_date', 'task_time']),
        ]

    def __str__(self):
        return self.title

    @classmethod
    def get_tasks_by_status(cls, status):
        return cls.objects.filter(status=status)

    @classmethod
    def get_overdue_tasks(cls):
        today = date.today()
        now = timezone.localtime().time()
        return cls.objects.filter(
            models.Q(task_date__lt=today) |
            models.Q(task_date=today, task_time__lt=now),
            status__in=['PENDING', 'IN_PROGRESS']
        )

    @classmethod
    def get_today_tasks(cls):
        return cls.objects.filter(task_date=date.today())

    @classmethod
    def get_upcoming_tasks(cls, days=7):
        end_date = date.today() + timedelta(days=days)
        return cls.objects.filter(
            task_date__gte=date.today(),
            task_date__lte=end_date
        )
    
    @classmethod
    def get_completed_tasks_by_date(cls, date_filter=None):
        """Get completed tasks for a specific date"""
        queryset = cls.objects.filter(status='COMPLETED')
        
        if date_filter:
            queryset = queryset.filter(
                completed_at__date=date_filter
            )
        
        return queryset.order_by('-completed_at')

    @classmethod
    def get_today_completed_tasks(cls):
        """Get tasks completed today"""
        return cls.get_completed_tasks_by_date(date.today())

class Habit(models.Model):
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    frequency = models.CharField(
        max_length=10,
        choices=FREQUENCY_CHOICES,
        default='daily'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reminder_time = models.TimeField(null=True, blank=True)
    is_reminder_active = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def is_completed_for_date(self, date):
        return self.habitlog_set.filter(log_date=date).exists()

    def get_completion_rate(self, days=30):
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        
        total_days = (end_date - start_date).days
        completed_days = self.habitlog_set.filter(
            log_date__range=[start_date, end_date]
        ).count()
        
        expected_completions = 0
        if self.frequency == 'daily':
            expected_completions = total_days
        elif self.frequency == 'weekly':
            expected_completions = total_days // 7
        elif self.frequency == 'monthly':
            expected_completions = total_days // 30

        if expected_completions == 0:
            return 0
            
        return min((completed_days / expected_completions) * 100, 100)

    def get_current_streak(self):
        logs = self.habitlog_set.order_by('-log_date')
        if not logs.exists():
            return 0

        streak = 0
        last_date = None

        for log in logs:
            current_date = log.log_date
            if last_date is None:
                streak = 1
            elif (last_date - current_date).days == 1:
                streak += 1
            else:
                break
            last_date = current_date

        return streak

class HabitLog(models.Model):
    habit = models.ForeignKey(Habit, on_delete=models.CASCADE)
    log_date = models.DateField(default=timezone.now)
    completed_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-log_date']
        unique_together = ['habit', 'log_date']  # Ensures one log per habit per day

    def __str__(self):
        return f"{self.habit.name} - {self.log_date}"

class IncomeGroup(models.Model):
    group_name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.group_name

class ExpenseGroup(models.Model):
    group_name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.group_name

class Income(models.Model):
    date = models.DateField()
    income_name = models.CharField(max_length=255)
    income_group = models.ForeignKey(IncomeGroup, on_delete=models.PROTECT)
    amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

class Expense(models.Model):
    date = models.DateField()
    expense_name = models.CharField(max_length=255)
    expense_group = models.ForeignKey(ExpenseGroup, on_delete=models.PROTECT)
    amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

class PartyLedger(models.Model):
    BALANCE_NATURE_CHOICES = [
        ('Receivable', 'Receivable'),
        ('Payable', 'Payable'),
    ]
    
    party_name = models.CharField(max_length=255)
    opening_balance = models.DecimalField(max_digits=10, decimal_places=2)
    balance_nature = models.CharField(
        max_length=10,
        choices=BALANCE_NATURE_CHOICES
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def get_current_balance(self):
        transactions = self.partytransaction_set.all()
        balance = self.opening_balance
        
        if self.balance_nature == 'Payable':
            balance = -balance
            
        for transaction in transactions:
            if transaction.transaction_type == 'Money In':
                balance += transaction.amount
            else:
                balance -= transaction.amount
                
        return balance

class PartyTransaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ('Money In', 'Money In'),
        ('Money Out', 'Money Out'),
    ]
    
    date = models.DateField()
    party = models.ForeignKey(PartyLedger, on_delete=models.PROTECT)
    transaction_type = models.CharField(
        max_length=10,
        choices=TRANSACTION_TYPE_CHOICES
    )
    amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Debt(models.Model):
    DEBT_TYPE_CHOICES = [
        ('One-Time', 'One-Time'),
        ('Multiple-Tenure', 'Multiple-Tenure'),
    ]
    
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Paid', 'Paid'),
        ('Partially Paid', 'Partially Paid'),
    ]
    
    debt_name = models.CharField(max_length=255)
    debt_type = models.CharField(
        max_length=15,
        choices=DEBT_TYPE_CHOICES
    )
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='Pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)

class DebtPaymentSchedule(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Paid', 'Paid'),
        ('Partially Paid', 'Partially Paid'),
        ('Skipped', 'Skipped'),
    ]
    
    debt = models.ForeignKey(Debt, on_delete=models.PROTECT)
    s_no = models.IntegerField()
    expected_payment_date = models.DateField()
    expected_amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_date = models.DateField(null=True, blank=True)
    paid_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        null=True,
        blank=True
    )
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='Pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['debt', 's_no']

class DebtPayment(models.Model):
    debt = models.ForeignKey(
        Debt, 
        on_delete=models.CASCADE,
        related_name='payments'
    )
    schedule = models.ForeignKey(
        DebtPaymentSchedule,
        on_delete=models.CASCADE,
        related_name='payments'
    )
    payment_date = models.DateField()
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    notes = models.TextField(
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-payment_date', '-created_at']

    def save(self, *args, **kwargs):
        # Update the schedule's paid amount and status
        schedule = self.schedule
        total_paid = (schedule.paid_amount or 0) + self.amount

        if total_paid >= schedule.expected_amount:
            schedule.status = 'Paid'
        elif total_paid > 0:
            schedule.status = 'Partially Paid'
        
        schedule.paid_amount = total_paid
        schedule.save()

        # Update the debt's status
        debt = self.debt
        all_schedules = debt.debtpaymentschedule_set.all()
        all_paid = all(s.status == 'Paid' for s in all_schedules)
        any_paid = any(s.status in ['Paid', 'Partially Paid'] for s in all_schedules)

        if all_paid:
            debt.status = 'Paid'
        elif any_paid:
            debt.status = 'Partially Paid'
        
        debt.save()

        super().save(*args, **kwargs)