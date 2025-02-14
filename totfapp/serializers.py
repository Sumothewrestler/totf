from rest_framework import serializers
from .models import *
from django.utils import timezone
import pytz
from datetime import datetime
from decimal import Decimal

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'color', 'created_at']

class ActivitySerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_color = serializers.CharField(source='category.color', read_only=True)
    
    class Meta:
        model = Activity
        fields = [
            'id', 
            'name', 
            'description', 
            'created_at', 
            'is_active', 
            'category',
            'category_name',
            'category_color'
        ]

class TimeEntrySerializer(serializers.ModelSerializer):
    activity_name = serializers.CharField(source='activity.name', read_only=True)
    category_name = serializers.CharField(source='activity.category.name', read_only=True)
    category_color = serializers.CharField(source='activity.category.color', read_only=True)
    duration_minutes = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = TimeEntry
        fields = [
            'id',
            'activity',
            'activity_name',
            'category_name',
            'category_color',
            'start_time',
            'end_time',
            'duration_minutes',
            'notes',
            'is_manually_entered',
            'created_at',
            'updated_at'
        ]

    def to_internal_value(self, data):
        """
        Convert incoming datetime strings to timezone-aware datetime objects.
        """
        ist = pytz.timezone('Asia/Kolkata')
        internal_data = super().to_internal_value(data)

        # Handle start_time
        if 'start_time' in internal_data:
            if timezone.is_naive(internal_data['start_time']):
                internal_data['start_time'] = ist.localize(internal_data['start_time'])

        # Handle end_time
        if 'end_time' in internal_data:
            if timezone.is_naive(internal_data['end_time']):
                internal_data['end_time'] = ist.localize(internal_data['end_time'])

        return internal_data

    def to_representation(self, instance):
        """
        Convert datetime fields to IST before sending to frontend.
        """
        ist = pytz.timezone('Asia/Kolkata')
        data = super().to_representation(instance)
        
        # Convert start_time to IST
        if data['start_time']:
            start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
            data['start_time'] = start_time.astimezone(ist).isoformat()
        
        # Convert end_time to IST
        if data['end_time']:
            end_time = datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
            data['end_time'] = end_time.astimezone(ist).isoformat()
        
        # Convert created_at and updated_at to IST
        if data['created_at']:
            created_at = datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
            data['created_at'] = created_at.astimezone(ist).isoformat()
        
        if data['updated_at']:
            updated_at = datetime.fromisoformat(data['updated_at'].replace('Z', '+00:00'))
            data['updated_at'] = updated_at.astimezone(ist).isoformat()
        
        return data

    def validate(self, data):
        """
        Validate time entry data with proper timezone handling.
        """
        ist = pytz.timezone('Asia/Kolkata')
        now = timezone.now().astimezone(ist)

        if 'start_time' in data and 'end_time' in data and data['end_time']:
            start_time = data['start_time'].astimezone(ist)
            end_time = data['end_time'].astimezone(ist)

            # Validate end time is after start time
            if end_time <= start_time:
                raise serializers.ValidationError({
                    "end_time": "End time must be after start time"
                })

            # Validate times are not in future
            if end_time > now:
                raise serializers.ValidationError({
                    "end_time": "End time cannot be in the future"
                })

            if start_time > now:
                raise serializers.ValidationError({
                    "start_time": "Start time cannot be in the future"
                })

            # Check for overlapping entries
            overlapping = TimeEntry.objects.filter(
                activity=data['activity'],
                start_time__lt=end_time,
                end_time__gt=start_time
            )
            
            if self.instance:
                overlapping = overlapping.exclude(pk=self.instance.pk)
            
            if overlapping.exists():
                raise serializers.ValidationError(
                    "This time entry overlaps with an existing entry"
                )

        return data

    def create(self, validated_data):
        """
        Create time entry with duration calculation.
        """
        instance = super().create(validated_data)
        
        # Calculate duration if both start and end times are present
        if instance.start_time and instance.end_time:
            duration = instance.end_time - instance.start_time
            instance.duration_minutes = int(duration.total_seconds() / 60)
            instance.save()
        
        return instance

    def update(self, instance, validated_data):
        """
        Update time entry with duration recalculation.
        """
        instance = super().update(instance, validated_data)
        
        # Recalculate duration if both start and end times are present
        if instance.start_time and instance.end_time:
            duration = instance.end_time - instance.start_time
            instance.duration_minutes = int(duration.total_seconds() / 60)
            instance.save()
        
        return instance
    
class SubProcessSerializer(serializers.ModelSerializer):
    goal_name = serializers.CharField(source='goal.name', read_only=True)
    estimated_days = serializers.DecimalField(
        max_digits=4,
        decimal_places=1,
        min_value=Decimal('0.1')
    )
    
    class Meta:
        model = SubProcess
        fields = [
            'id', 
            'name', 
            'goal',
            'goal_name', 
            'estimated_days',
            'status',
            'sort_order',
            'focus',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

class GoalSerializer(serializers.ModelSerializer):
    sub_processes = SubProcessSerializer(many=True, read_only=True)
    
    class Meta:
        model = Goal
        fields = ['id', 'name', 'status', 'sub_processes', 'sort_order', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

# First define SubProcessInGoalSerializer
class SubProcessInGoalSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubProcess
        fields = ['id', 'name', 'estimated_days', 'status', 'focus']

class GoalDetailSerializer(serializers.ModelSerializer):
    sub_processes = SubProcessInGoalSerializer(many=True, read_only=True)
    total_estimated_days = serializers.SerializerMethodField()
    completed_estimated_days = serializers.SerializerMethodField()
    remaining_estimated_days = serializers.SerializerMethodField()
    completion_percentage = serializers.SerializerMethodField()
    subprocess_completion_percentage = serializers.SerializerMethodField()
    total_subprocesses = serializers.SerializerMethodField()
    completed_subprocesses = serializers.SerializerMethodField()

    class Meta:
        model = Goal
        fields = [
            'id', 
            'name', 
            'status',
            'sub_processes',
            'total_estimated_days',
            'completed_estimated_days',
            'remaining_estimated_days',
            'completion_percentage',
            'subprocess_completion_percentage',
            'total_subprocesses',
            'completed_subprocesses',
            'created_at',
            'updated_at'
        ]

    # Existing methods remain the same
    def get_total_estimated_days(self, obj):
        return sum(
            [sp.estimated_days for sp in obj.sub_processes.all()],
            Decimal('0')
        )

    def get_completed_estimated_days(self, obj):
        return sum(
            [sp.estimated_days for sp in obj.sub_processes.filter(status='DONE')],
            Decimal('0')
        )

    def get_remaining_estimated_days(self, obj):
        return sum(
            [sp.estimated_days for sp in obj.sub_processes.filter(status='PENDING')],
            Decimal('0')
        )

    def get_completion_percentage(self, obj):
        total = self.get_total_estimated_days(obj)
        if total == 0:
            return 0
        completed = self.get_completed_estimated_days(obj)
        return round((completed / total) * 100, 1)

    # New methods for subprocess completion
    def get_total_subprocesses(self, obj):
        return obj.sub_processes.count()

    def get_completed_subprocesses(self, obj):
        return obj.sub_processes.filter(status='DONE').count()

    def get_subprocess_completion_percentage(self, obj):
        total = self.get_total_subprocesses(obj)
        if total == 0:
            return 0
        completed = self.get_completed_subprocesses(obj)
        return round((completed / total) * 100, 1)

class SubProcessDetailSerializer(serializers.ModelSerializer):
    goal_name = serializers.CharField(source='goal.name', read_only=True)
    
    class Meta:
        model = SubProcess
        fields = [
            'id', 
            'name', 
            'goal', 
            'goal_name', 
            'estimated_days',  # Changed from est_due_date
            'status', 
            'focus', 
            'created_at',
            'completed_at',
            'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate_estimated_days(self, value):
        if value <= 0:
            raise serializers.ValidationError("Estimated days must be greater than zero")
        return value

class WorkHeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkHead
        fields = ['id', 'name', 'description', 'is_active', 'created_at']

class WorkUpdateSerializer(serializers.ModelSerializer):
    head_name = serializers.CharField(source='head.name', read_only=True)
    head_active = serializers.BooleanField(source='head.is_active', read_only=True)

    class Meta:
        model = WorkUpdate
        fields = ['id', 'date', 'head', 'head_name', 'head_active', 'description', 'created_at', 'updated_at']

class WorkUpdateReportSerializer(serializers.ModelSerializer):
    head_name = serializers.CharField(source='head.name', read_only=True)
    
    class Meta:
        model = WorkUpdate
        fields = ['date', 'head_name', 'description']

class WorkHeadReportSerializer(serializers.ModelSerializer):
    update_count = serializers.IntegerField()
    last_update = serializers.DateField()
    
    class Meta:
        model = WorkHead
        fields = ['name', 'is_active', 'update_count', 'last_update']


class FocusedSubProcessSerializer(serializers.ModelSerializer):
    goal_name = serializers.CharField(source='goal.name', read_only=True)
    
    class Meta:
        model = SubProcess
        fields = [
            'id', 'name', 'goal', 'goal_name', 
            'estimated_days', 'status', 'focus',
            'created_at', 'updated_at'
        ]

class TaskSerializer(serializers.ModelSerializer):
    is_overdue = serializers.BooleanField(read_only=True)
    estimated_duration_text = serializers.SerializerMethodField()
    
    class Meta:
        model = Task
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'completed_at')

    def get_estimated_duration_text(self, obj):
        if obj.estimated_time and obj.estimate_unit:
            unit = obj.estimate_unit.lower()
            return f"{obj.estimated_time}{unit[0]}"  # Returns format like "30m", "2h", "1d"
        return None

class TaskSummarySerializer(serializers.Serializer):
    status = serializers.CharField()
    count = serializers.IntegerField()

class TaskCompletionStatsSerializer(serializers.Serializer):
    month = serializers.DateField()
    completed_count = serializers.IntegerField()
    total_count = serializers.IntegerField()
    completion_rate = serializers.FloatField()

class CompletedTaskSerializer(serializers.ModelSerializer):
    completed_time = serializers.SerializerMethodField()
    completion_duration = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            'id', 'title', 'description', 'priority',
            'task_date', 'task_time', 'completed_at',
            'completed_time', 'completion_duration'
        ]

    def get_completed_time(self, obj):
        if obj.completed_at:
            return obj.completed_at.strftime('%I:%M %p')
        return None

    def get_completion_duration(self, obj):
        """Calculate duration between task creation and completion"""
        if obj.completed_at and obj.created_at:
            duration = obj.completed_at - obj.created_at
            hours = duration.total_seconds() / 3600
            return round(hours, 2)
        return None

class CompletedTasksSummarySerializer(serializers.Serializer):
    date = serializers.DateField()
    total_completed = serializers.IntegerField()
    by_priority = serializers.DictField()
    average_completion_time = serializers.FloatField()


class HabitSerializer(serializers.ModelSerializer):
    completion_rate = serializers.SerializerMethodField()
    current_streak = serializers.SerializerMethodField()
    is_completed_today = serializers.SerializerMethodField()

    class Meta:
        model = Habit
        fields = [
            'id', 'name', 'description', 'frequency', 'created_at',
            'reminder_time', 'is_reminder_active',
            'completion_rate', 'current_streak', 'is_completed_today'
        ]

    def get_completion_rate(self, obj):
        days = self.context.get('days', 30)
        return obj.get_completion_rate(days)

    def get_current_streak(self, obj):
        return obj.get_current_streak()

    def get_is_completed_today(self, obj):
        return obj.is_completed_for_date(timezone.now().date())

class HabitLogSerializer(serializers.ModelSerializer):
    habit_name = serializers.CharField(source='habit.name', read_only=True)

    class Meta:
        model = HabitLog
        fields = ['id', 'habit', 'habit_name', 'log_date', 'completed_at', 'notes']
        read_only_fields = ['completed_at']

class HabitStatsSerializer(serializers.Serializer):
    total_habits = serializers.IntegerField()
    active_habits = serializers.IntegerField()
    completion_rate = serializers.FloatField()
    longest_streak = serializers.IntegerField()
    most_consistent_habit = serializers.CharField()

class HabitRegisterSerializer(serializers.Serializer):
    date_range = serializers.ListField(
        child=serializers.DateField(),
        read_only=True
    )
    habits = serializers.SerializerMethodField()

    def get_habits(self, obj):
        habits = Habit.objects.all()
        return [{
            'id': habit.id,
            'name': habit.name,
            'completions': [
                habit.is_completed_for_date(date)
                for date in obj['date_range']
            ]
        } for habit in habits]

class IncomeGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncomeGroup
        fields = '__all__'

class ExpenseGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseGroup
        fields = '__all__'

class IncomeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Income
        fields = '__all__'

class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = '__all__'

class PartyLedgerSerializer(serializers.ModelSerializer):
    current_balance = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,
        source='get_current_balance'
    )

    class Meta:
        model = PartyLedger
        fields = '__all__'

class PartyTransactionSerializer(serializers.ModelSerializer):
    party_name = serializers.CharField(source='party.party_name', read_only=True)
    
    class Meta:
        model = PartyTransaction
        fields = ['id', 'date', 'transaction_type', 'amount', 'notes', 
                 'created_at', 'party', 'party_name']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['amount'] = float(representation['amount'])
        return representation

class DebtSerializer(serializers.ModelSerializer):
    total_expected = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    total_paid = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    net_balance = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = Debt
        fields = '__all__'

class DebtPaymentScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DebtPaymentSchedule
        fields = '__all__'

class DebtMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Debt
        fields = ['id', 'debt_name']

class ScheduleMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = DebtPaymentSchedule
        fields = ['id', 's_no', 'expected_amount', 'expected_payment_date']

class DebtPaymentSerializer(serializers.ModelSerializer):
    debt_details = DebtMinimalSerializer(source='debt', read_only=True)
    schedule_details = ScheduleMinimalSerializer(source='schedule', read_only=True)

    class Meta:
        model = DebtPayment
        fields = [
            'id',
            'debt',
            'debt_details',
            'schedule',
            'schedule_details',
            'payment_date',
            'amount',
            'notes',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, data):
        schedule = data['schedule']
        amount = data['amount']

        # Ensure the schedule belongs to the debt
        if schedule.debt != data['debt']:
            raise serializers.ValidationError(
                "The selected schedule does not belong to the selected debt"
            )

        # Check if payment amount is valid
        remaining_amount = schedule.expected_amount - (schedule.paid_amount or 0)
        if amount > remaining_amount:
            raise serializers.ValidationError(
                f"Payment amount cannot exceed the remaining amount of {remaining_amount}"
            )

        return data

class DailyHabitSerializer(serializers.ModelSerializer):
    is_completed = serializers.SerializerMethodField()
    item_type = serializers.SerializerMethodField()
    time = serializers.TimeField(source='reminder_time')

    class Meta:
        model = Habit
        fields = ['id', 'name', 'time', 'is_completed', 'item_type']

    def get_is_completed(self, obj):
        today = timezone.now().date()
        return obj.is_completed_for_date(today)

    def get_item_type(self, obj):
        return 'habit'

class DailyTaskSerializer(serializers.ModelSerializer):
    item_type = serializers.SerializerMethodField()
    time = serializers.TimeField(source='task_time')
    name = serializers.CharField(source='title')  # Map title to name for consistent frontend

    class Meta:
        model = Task
        fields = ['id', 'name', 'time', 'status', 'item_type', 'priority']

    def get_item_type(self, obj):
        return 'task'
    
class DailySubProcessSerializer(serializers.ModelSerializer):
    item_type = serializers.SerializerMethodField()

    class Meta:
        model = SubProcess
        fields = ['id', 'name', 'status', 'item_type']

    def get_item_type(self, obj):
        return 'subprocess'