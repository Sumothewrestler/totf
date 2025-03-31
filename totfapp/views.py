from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import ListModelMixin
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.views import APIView
from .models import *
from .serializers import *
from datetime import datetime
from django.db.models import Sum, Case, When, DecimalField
from django.db.models import F
from django_filters import rest_framework as django_filters
import pytz
from datetime import datetime, timedelta
from django.db.models import Count, Avg, Max
from django.db.models import Q
from django.db.models import Count
import csv
from django.db.models.functions import TruncDate
from rest_framework.decorators import api_view
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters, status
from django.db.models.functions import TruncDate, TruncMonth
from rest_framework import generics
from django.shortcuts import get_object_or_404
import uuid

class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    
    def get_queryset(self):
        return Category.objects.all().order_by('name')

class ActivityViewSet(viewsets.ModelViewSet):
    serializer_class = ActivitySerializer
    
    def get_queryset(self):
        queryset = Activity.objects.all()
        category = self.request.query_params.get('category', None)
        is_active = self.request.query_params.get('is_active', None)
        
        if category:
            queryset = queryset.filter(category_id=category)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
            
        return queryset.order_by('name')

class TimeEntryViewSet(viewsets.ModelViewSet):
    serializer_class = TimeEntrySerializer
    
    def get_queryset(self):
        queryset = TimeEntry.objects.select_related('activity', 'activity__category')
        
        # Get query parameters
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        sort_by = self.request.query_params.get('sort_by', 'start_time')
        order = self.request.query_params.get('order', 'asc')
        activity = self.request.query_params.get('activity')
        
        try:
            # Convert dates to timezone-aware datetime
            ist = pytz.timezone('Asia/Kolkata')
            if start_date:
                start_datetime = ist.localize(datetime.strptime(start_date, '%Y-%m-%d')).replace(
                    hour=0, minute=0, second=0
                )
                queryset = queryset.filter(start_time__gte=start_datetime)
            
            if end_date:
                end_datetime = ist.localize(datetime.strptime(end_date, '%Y-%m-%d')).replace(
                    hour=23, minute=59, second=59
                )
                queryset = queryset.filter(start_time__lte=end_datetime)
            
            # Filter by activity if provided
            if activity:
                queryset = queryset.filter(activity_id=activity)
            
            # Apply sorting
            sort_field = f'-{sort_by}' if order == 'desc' else sort_by
            if sort_by != 'start_time':
                return queryset.order_by(sort_field, 'start_time')
            return queryset.order_by(sort_field)
            
        except Exception as e:
            print(f"Error in get_queryset: {str(e)}")
            return TimeEntry.objects.none()

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        
        # Calculate total duration
        total_duration = sum(
            entry.duration_minutes for entry in queryset if entry.duration_minutes
        )
        
        # Get date range for response
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        ist = pytz.timezone('Asia/Kolkata')
        
        start_datetime = None
        end_datetime = None
        
        if start_date:
            start_datetime = ist.localize(datetime.strptime(start_date, '%Y-%m-%d')).replace(
                hour=0, minute=0, second=0
            )
        if end_date:
            end_datetime = ist.localize(datetime.strptime(end_date, '%Y-%m-%d')).replace(
                hour=23, minute=59, second=59
            )
        
        return Response({
            'entries': serializer.data,
            'total_entries': queryset.count(),
            'total_duration_minutes': total_duration,
            'date_range': {
                'start': start_datetime.isoformat() if start_datetime else None,
                'end': end_datetime.isoformat() if end_datetime else None,
            }
        })

    @action(detail=False, methods=['GET'])
    def active(self, request):
        """Return the currently active time entry (if any)"""
        active_entry = self.get_queryset().filter(end_time=None).order_by('-start_time').first()
        
        if active_entry:
            serializer = self.get_serializer(active_entry)
            return Response(serializer.data)
        return Response({}, status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=False, methods=['POST'])
    def start(self, request):
        """Start a new time entry, ensuring any active entries are stopped first"""
        # First stop any active entries
        active_entries = self.get_queryset().filter(end_time=None)
        
        for entry in active_entries:
            entry.end_time = timezone.now()
            entry.save()
        
        # Create the new entry with a sync token
        data = request.data.copy()
        data['sync_token'] = str(uuid.uuid4())
        
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['POST'])
    def stop(self, request, pk=None):
        """Stop an active time entry and calculate duration"""
        try:
            entry = self.get_queryset().get(pk=pk)
            
            if entry.end_time:
                return Response(
                    {"detail": "This time entry is already stopped"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            entry.end_time = timezone.now()
            duration = entry.end_time - entry.start_time
            entry.duration_minutes = int(duration.total_seconds() / 60)
            entry.save()
            
            serializer = self.get_serializer(entry)
            return Response(serializer.data)
            
        except TimeEntry.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['GET'])
    def sync_state(self, request):
        """
        Return the current state of time entries for synchronization
        Includes active entry and recently completed entries
        """
        # Get active entry if any
        active_entry = self.get_queryset().filter(end_time=None).order_by('-start_time').first()
        
        # Get recently completed entries in the last 24 hours
        yesterday = timezone.now() - timezone.timedelta(days=1)
        recent_entries = self.get_queryset().filter(
            end_time__gte=yesterday
        ).order_by('-end_time')[:5]
        
        response_data = {
            'active_entry': self.get_serializer(active_entry).data if active_entry else None,
            'recent_entries': self.get_serializer(recent_entries, many=True).data
        }
        
        return Response(response_data)

    @action(detail=False, methods=['post'])
    def manual(self, request):
        """Create a manual time entry"""
        serializer = self.get_serializer(data={**request.data, 'is_manually_entered': True})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
@api_view(['GET'])
def category_report(request):
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    
    # Convert dates to datetime
    start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
    end_datetime = datetime.strptime(end_date, '%Y-%m-%d')
    
    # Query all categories with their time entries
    categories = Category.objects.all()
    report_data = []
    
    for category in categories:
        time_entries = TimeEntry.objects.filter(
            activity__category=category,
            start_time__date__gte=start_datetime,
            start_time__date__lte=end_datetime,
            end_time__isnull=False
        ).select_related('activity')
        
        if not time_entries.exists():
            continue
            
        total_duration = time_entries.aggregate(
            total=Sum('duration_minutes')
        )['total'] or 0
        
        entry_data = []
        for entry in time_entries:
            entry_data.append({
                'activity_name': entry.activity.name,
                'duration_minutes': entry.duration_minutes,
                'start_time': entry.start_time,
                'end_time': entry.end_time,
            })
            
        report_data.append({
            'category_id': category.id,
            'category_name': category.name,
            'category_color': category.color,
            'total_duration': total_duration,
            'activity_count': time_entries.count(),
            'time_entries': entry_data
        })
    
    return Response(report_data)

@api_view(['GET'])
def category_summary_report(request):
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    
    # Convert dates to datetime
    start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
    end_datetime = datetime.strptime(end_date, '%Y-%m-%d')
    
    categories = Category.objects.all()
    summary_data = []
    
    for category in categories:
        total_duration = TimeEntry.objects.filter(
            activity__category=category,
            start_time__date__gte=start_datetime,
            start_time__date__lte=end_datetime,
            end_time__isnull=False
        ).aggregate(
            total=Sum('duration_minutes')
        )['total'] or 0
        
        if total_duration > 0:
            summary_data.append({
                'category_id': category.id,
                'category_name': category.name,
                'category_color': category.color,
                'total_duration': total_duration,
                'percentage': 0  # Will be calculated below
            })
    
    # Calculate percentages
    total_time = sum(item['total_duration'] for item in summary_data)
    if total_time > 0:
        for item in summary_data:
            item['percentage'] = round((item['total_duration'] / total_time) * 100, 1)
    
    return Response(summary_data)

@api_view(['GET'])
def activity_report(request):
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    
    # Convert dates to datetime
    start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
    end_datetime = datetime.strptime(end_date, '%Y-%m-%d')
    
    activities = Activity.objects.all().select_related('category')
    report_data = []
    
    for activity in activities:
        time_entries = TimeEntry.objects.filter(
            activity=activity,
            start_time__date__gte=start_datetime,
            start_time__date__lte=end_datetime,
            end_time__isnull=False
        )
        
        if not time_entries.exists():
            continue
            
        total_duration = time_entries.aggregate(
            total=Sum('duration_minutes')
        )['total'] or 0
        
        entry_data = []
        for entry in time_entries:
            entry_data.append({
                'id': entry.id,
                'start_time': entry.start_time,
                'end_time': entry.end_time,
                'duration_minutes': entry.duration_minutes,
                'date': entry.start_time.date().isoformat()
            })
            
        report_data.append({
            'activity_id': activity.id,
            'activity_name': activity.name,
            'activity_description': activity.description,
            'category': {
                'id': activity.category.id,
                'name': activity.category.name,
                'color': activity.category.color
            } if activity.category else None,
            'total_duration': total_duration,
            'entry_count': time_entries.count(),
            'time_entries': entry_data
        })
    
    return Response(report_data)

@api_view(['GET'])
def activity_summary_report(request):
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    
    # Convert dates to datetime
    start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
    end_datetime = datetime.strptime(end_date, '%Y-%m-%d')
    
    activities = Activity.objects.all().select_related('category')
    summary_data = []
    total_duration = 0
    
    for activity in activities:
        duration = TimeEntry.objects.filter(
            activity=activity,
            start_time__date__gte=start_datetime,
            start_time__date__lte=end_datetime,
            end_time__isnull=False
        ).aggregate(
            total=Sum('duration_minutes')
        )['total'] or 0
        
        if duration > 0:
            summary_data.append({
                'activity_id': activity.id,
                'activity_name': activity.name,
                'category': {
                    'id': activity.category.id,
                    'name': activity.category.name,
                    'color': activity.category.color
                } if activity.category else None,
                'total_duration': duration,
                'percentage': 0  # Will be calculated below
            })
            total_duration += duration
    
    # Calculate percentages
    if total_duration > 0:
        for item in summary_data:
            item['percentage'] = round((item['total_duration'] / total_duration) * 100, 1)
    
    # Sort by duration (descending)
    summary_data.sort(key=lambda x: x['total_duration'], reverse=True)
    
    return Response({
        'activities': summary_data,
        'total_duration': total_duration
    })

@api_view(['GET'])
def time_entry_gaps(request):
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    
    # Convert dates to timezone-aware datetime
    ist = pytz.timezone('Asia/Kolkata')
    start_datetime = ist.localize(datetime.strptime(start_date, '%Y-%m-%d')).replace(
        hour=0, minute=0, second=0
    )
    end_datetime = ist.localize(datetime.strptime(end_date, '%Y-%m-%d')).replace(
        hour=23, minute=59, second=59
    )
    
    # Get all time entries for the date range, ordered by start time
    entries = TimeEntry.objects.filter(
        start_time__gte=start_datetime,
        start_time__lte=end_datetime,
        end_time__isnull=False
    ).order_by('start_time')
    
    gaps = []
    previous_end = start_datetime
    
    for entry in entries:
        # If there's a gap between previous end and current start
        if entry.start_time - previous_end > timedelta(minutes=1):
            gaps.append({
                'gap_start': previous_end.astimezone(ist).isoformat(),
                'gap_end': entry.start_time.astimezone(ist).isoformat(),
                'duration_minutes': int((entry.start_time - previous_end).total_seconds() / 60),
                'previous_activity': None if previous_end == start_datetime else TimeEntry.objects.filter(
                    end_time=previous_end
                ).first().activity.name,
                'next_activity': entry.activity.name
            })
        previous_end = entry.end_time
    
    # Check for gap after the last entry until end of day
    if entries.exists() and entries.last().end_time < end_datetime:
        gaps.append({
            'gap_start': entries.last().end_time.astimezone(ist).isoformat(),
            'gap_end': end_datetime.astimezone(ist).isoformat(),
            'duration_minutes': int(
                (end_datetime - entries.last().end_time).total_seconds() / 60
            ),
            'previous_activity': entries.last().activity.name,
            'next_activity': None
        })
    
    # If no entries for the day, return the entire day as a gap
    if not entries.exists():
        gaps.append({
            'gap_start': start_datetime.astimezone(ist).isoformat(),
            'gap_end': end_datetime.astimezone(ist).isoformat(),
            'duration_minutes': 1440,  # 24 hours in minutes
            'previous_activity': None,
            'next_activity': None
        })
    
    return Response({
        'date_range': {
            'start': start_datetime.astimezone(ist).isoformat(),
            'end': end_datetime.astimezone(ist).isoformat(),
        },
        'gaps': gaps,
        'total_gap_minutes': sum(gap['duration_minutes'] for gap in gaps)
    })

class SubProcessViewSet(viewsets.ModelViewSet):
    queryset = SubProcess.objects.all()
    serializer_class = SubProcessSerializer

    @action(detail=True, methods=['post'])  # Add new action
    def update_sort_order(self, request, pk=None):
        subprocess = self.get_object()
        new_order = request.data.get('sort_order')
        
        if new_order is not None:
            # Update current subprocess order
            subprocess.sort_order = new_order
            subprocess.save()
            
            # Reorder other subprocesses in the same goal
            SubProcess.objects.filter(
                goal=subprocess.goal,
                sort_order__gte=new_order
            ).exclude(
                id=subprocess.id
            ).update(sort_order=F('sort_order') + 1)
            
            return Response({'status': 'sort order updated'})
        return Response(
            {'error': 'sort_order required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )

    @action(detail=True, methods=['post'])
    def toggle_focus(self, request, pk=None):
        subprocess = self.get_object()
        subprocess.focus = not subprocess.focus
        subprocess.save()
        serializer = self.get_serializer(subprocess)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def toggle_status(self, request, pk=None):
        subprocess = self.get_object()
        if subprocess.status == ProcessStatus.PENDING:
            subprocess.status = ProcessStatus.DONE
            subprocess.completed_at = timezone.now()  # Set completion date
        else:
            subprocess.status = ProcessStatus.PENDING
            subprocess.completed_at = None  # Clear completion date
        subprocess.save()
        return Response({
            'status': 'success',
            'new_status': subprocess.status
        })

    def get_queryset(self):
        queryset = SubProcess.objects.all().order_by('sort_order', '-created_at')
        
        # Filter by goal
        goal_id = self.request.query_params.get('goal', None)
        if goal_id:
            queryset = queryset.filter(goal_id=goal_id)
            
        # Filter by status
        process_status = self.request.query_params.get('status', None)
        if process_status:
            queryset = queryset.filter(status=process_status)
            
        # Filter by focus
        focus = self.request.query_params.get('focus', None)
        if focus is not None:
            queryset = queryset.filter(focus=focus.lower() == 'true')
            
        return queryset

class FocusedSubProcessView(generics.ListAPIView):
    serializer_class = FocusedSubProcessSerializer
    
    def get_queryset(self):
        return SubProcess.objects.filter(
            focus=True
        ).select_related('goal').order_by('created_at')

class GoalViewSet(viewsets.ModelViewSet):
    queryset = Goal.objects.all()
    serializer_class = GoalDetailSerializer

    @action(detail=True, methods=['post'])
    def update_sort_order(self, request, pk=None):
        goal = self.get_object()
        new_order = request.data.get('sort_order')
        
        if new_order is not None:
            # Update current goal order
            goal.sort_order = new_order
            goal.save()
            
            # Reorder other goals
            Goal.objects.filter(
                sort_order__gte=new_order
            ).exclude(
                id=goal.id
            ).update(sort_order=F('sort_order') + 1)
            
            return Response({'status': 'sort order updated'})
        return Response(
            {'error': 'sort_order required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )

    def get_queryset(self):
        return Goal.objects.prefetch_related('sub_processes').order_by('sort_order', '-created_at')

    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        goal = self.get_object()
        sub_processes = goal.sub_processes.all()
        completed_sub_processes = sub_processes.filter(status='DONE')

        # Calculate statistics
        total_sub_processes = sub_processes.count()
        completed_count = completed_sub_processes.count()
        
        stats = {
            'total_sub_processes': total_sub_processes,
            'completed_sub_processes': completed_count,
            'focused_sub_processes': sub_processes.filter(focus=True).count(),
            'estimated_days': {
                'total': float(sum([sp.estimated_days for sp in sub_processes], Decimal('0'))),
                'completed': float(sum(
                    [sp.estimated_days for sp in completed_sub_processes],
                    Decimal('0')
                )),
                'remaining': float(sum(
                    [sp.estimated_days for sp in sub_processes.filter(status='PENDING')],
                    Decimal('0')
                ))
            },
            'progress': {
                'time_based': {
                    'percentage': 0,
                    'completed_days': 0,
                    'total_days': 0
                },
                'subprocess_based': {
                    'percentage': 0,
                    'completed_count': completed_count,
                    'total_count': total_sub_processes
                }
            }
        }

        # Calculate time-based completion percentage
        if stats['estimated_days']['total'] > 0:
            stats['progress']['time_based'] = {
                'percentage': round(
                    (stats['estimated_days']['completed'] / stats['estimated_days']['total']) * 100,
                    1
                ),
                'completed_days': stats['estimated_days']['completed'],
                'total_days': stats['estimated_days']['total']
            }

        # Calculate subprocess-based completion percentage
        if total_sub_processes > 0:
            stats['progress']['subprocess_based'] = {
                'percentage': round(
                    (completed_count / total_sub_processes) * 100,
                    1
                ),
                'completed_count': completed_count,
                'total_count': total_sub_processes
            }

        return Response(stats)

    @action(detail=True, methods=['get'])
    def sub_processes(self, request, pk=None):
        goal = self.get_object()
        sub_processes = goal.sub_processes.all().order_by('created_at')
        serializer = SubProcessSerializer(sub_processes, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def mark_completed(self, request, pk=None):
        goal = self.get_object()
        
        # Mark all sub-processes as done
        goal.sub_processes.all().update(status='DONE')
        
        # Update goal status
        goal.status = 'DONE'
        goal.save()
        
        return Response({
            'status': 'Goal and all sub-processes marked as completed',
            'progress': {
                'time_based': {
                    'percentage': 100,
                    'completed_days': float(sum(
                        [sp.estimated_days for sp in goal.sub_processes.all()],
                        Decimal('0')
                    ))
                },
                'subprocess_based': {
                    'percentage': 100,
                    'completed_count': goal.sub_processes.count(),
                    'total_count': goal.sub_processes.count()
                }
            }
        })

class VisionViewSet(ListModelMixin, GenericViewSet):
    serializer_class = GoalSerializer
    
    def get_queryset(self):
        return Goal.objects.prefetch_related('sub_processes').order_by('sort_order', '-created_at')

    @action(detail=False, methods=['post'])
    def bulk_update_order(self, request):
        """Update sort order for multiple goals at once"""
        orders = request.data.get('orders', [])
        
        for order in orders:
            goal_id = order.get('id')
            new_order = order.get('sort_order')
            
            if goal_id and new_order is not None:
                Goal.objects.filter(id=goal_id).update(sort_order=new_order)
        
        return Response({'status': 'orders updated'})

class WorkHeadViewSet(viewsets.ModelViewSet):
    queryset = WorkHead.objects.all()
    serializer_class = WorkHeadSerializer

    def get_queryset(self):
        # For creating new work updates, only show active heads
        if self.action == 'list' and self.request.query_params.get('for_update') == 'true':
            return WorkHead.objects.filter(is_active=True)
        # For all other cases, show all heads
        return WorkHead.objects.all()

class WorkUpdateViewSet(viewsets.ModelViewSet):
    queryset = WorkUpdate.objects.all()
    serializer_class = WorkUpdateSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['date', 'head']
    ordering_fields = ['date', 'created_at']
    ordering = ['-date', '-created_at']

    def get_queryset(self):
        queryset = WorkUpdate.objects.select_related('head').all()
        
        # Date range filtering
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
            
        return queryset

@api_view(['GET'])
def recent_updates_report(request):
    """Get updates from the last 7 days"""
    try:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=7)
        
        updates = WorkUpdate.objects.filter(
            date__range=[start_date, end_date]
        ).select_related('head').order_by('-date')
        
        serializer = WorkUpdateReportSerializer(updates, many=True)
        
        return Response({
            'start_date': start_date,
            'end_date': end_date,
            'updates': serializer.data
        })
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
def work_head_summary(request):
    """Get summary statistics for each work head"""
    try:
        # Show all work heads in summary, including inactive
        work_heads = WorkHead.objects.annotate(
            update_count=Count('updates'),
            last_update=Max('updates__date')
        ).order_by('-update_count')
        
        serializer = WorkHeadReportSerializer(work_heads, many=True)
        
        return Response(serializer.data)
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
def monthly_update_counts(request):
    """Get update counts by month"""
    try:
        year = request.query_params.get('year', datetime.now().year)
        
        # Include all updates in monthly counts
        monthly_counts = WorkUpdate.objects.filter(
            date__year=year
        ).annotate(
            month=TruncMonth('date')
        ).values('month').annotate(
            count=Count('id')
        ).order_by('month')
        
        return Response({
            'year': year,
            'monthly_counts': [
                {
                    'month': item['month'].strftime('%B %Y'),
                    'count': item['count']
                }
                for item in monthly_counts
            ]
        })
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
def work_update_search(request):
    """Search work updates by description or work head"""
    try:
        query = request.query_params.get('q', '')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        # Show all updates in search results
        updates = WorkUpdate.objects.select_related('head')
        
        if query:
            updates = updates.filter(
                Q(description__icontains=query) |
                Q(head__name__icontains=query)
            )
        
        if start_date:
            updates = updates.filter(date__gte=start_date)
        if end_date:
            updates = updates.filter(date__lte=end_date)
            
        updates = updates.order_by('-date')[:100]  # Limit to 100 results
        
        serializer = WorkUpdateReportSerializer(updates, many=True)
        
        return Response({
            'query': query,
            'start_date': start_date,
            'end_date': end_date,
            'results': serializer.data
        })
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    filterset_fields = ['status', 'priority', 'task_date']
    search_fields = ['title', 'description']
    ordering_fields = ['task_date', 'priority', 'created_at']

    @action(detail=False)
    def by_status(self, request):
        status = request.query_params.get('status', 'PENDING')
        tasks = Task.get_tasks_by_status(status)
        serializer = self.get_serializer(tasks, many=True)
        return Response(serializer.data)

    @action(detail=False)
    def by_priority(self, request):
        priority = request.query_params.get('priority', 'HIGH')
        tasks = self.queryset.filter(priority=priority)
        serializer = self.get_serializer(tasks, many=True)
        return Response(serializer.data)

    @action(detail=False)
    def overdue(self, request):
        tasks = Task.get_overdue_tasks()
        serializer = self.get_serializer(tasks, many=True)
        return Response(serializer.data)

    @action(detail=False)
    def today(self, request):
        tasks = Task.get_today_tasks()
        serializer = self.get_serializer(tasks, many=True)
        return Response(serializer.data)

    @action(detail=False)
    def completed_today(self, request):
        """Get tasks completed today"""
        tasks = Task.get_today_completed_tasks()
        serializer = CompletedTaskSerializer(tasks, many=True)
        return Response(serializer.data)

    @action(detail=False)
    def completion_report(self, request):
        """Get completion report for a date range"""
        days = int(request.query_params.get('days', 7))
        end_date = date.today()
        start_date = end_date - timedelta(days=days-1)
        
        daily_completions = []
        current_date = start_date
        
        while current_date <= end_date:
            tasks = Task.get_completed_tasks_by_date(current_date)
            daily_data = {
                'date': current_date,
                'total_completed': tasks.count(),
                'by_priority': dict(tasks.values('priority').annotate(
                    count=Count('id')).values_list('priority', 'count')),
                'average_completion_time': tasks.exclude(
                    completed_at__isnull=True
                ).aggregate(
                    avg_time=Avg(
                        models.F('completed_at') - models.F('created_at')
                    )
                )['avg_time'].total_seconds() / 3600 if tasks.exists() else 0
            }
            daily_completions.append(daily_data)
            current_date += timedelta(days=1)
        
        return Response(daily_completions)
    
class TaskSummaryView(generics.ListAPIView):
    serializer_class = TaskSummarySerializer

    def get_queryset(self):
        return (Task.objects
                .values('status')
                .annotate(count=Count('id'))
                .order_by('status'))

class UpcomingTasksView(generics.ListAPIView):
    serializer_class = TaskSerializer

    def get_queryset(self):
        days = int(self.request.query_params.get('days', 7))
        return Task.get_upcoming_tasks(days)

class TaskCompletionStatsView(generics.ListAPIView):
    serializer_class = TaskCompletionStatsSerializer

    def get_queryset(self):
        end_date = date.today()
        start_date = end_date - timedelta(days=365)
        
        monthly_stats = (
            Task.objects
            .filter(task_date__range=[start_date, end_date])
            .annotate(month=TruncMonth('task_date'))
            .values('month')
            .annotate(
                completed_count=Count('id', filter=models.Q(status='COMPLETED')),
                total_count=Count('id'),
                completion_rate=F('completed_count') * 100.0 / F('total_count')
            )
            .order_by('month')
        )
        return monthly_stats

class CompletedTasksView(generics.ListAPIView):
    serializer_class = CompletedTaskSerializer

    def get_queryset(self):
        # Get date from query params or default to today
        date_str = self.request.query_params.get('date')
        if date_str:
            try:
                filter_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                filter_date = date.today()
        else:
            filter_date = date.today()

        return Task.get_completed_tasks_by_date(filter_date)

    def get(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        # Get summary statistics
        date_filter = queryset.first().completed_at.date() if queryset.exists() else date.today()
        
        summary_data = {
            'date': date_filter,
            'total_completed': queryset.count(),
            'by_priority': dict(queryset.values('priority').annotate(
                count=Count('id')).values_list('priority', 'count')),
            'average_completion_time': queryset.exclude(
                completed_at__isnull=True
            ).aggregate(
                avg_time=Avg(
                    models.F('completed_at') - models.F('created_at')
                )
            )['avg_time'].total_seconds() / 3600 if queryset.exists() else 0
        }

        # Return both summary and detailed data
        return Response({
            'summary': CompletedTasksSummarySerializer(summary_data).data,
            'tasks': self.serializer_class(queryset, many=True).data
        })

class HabitViewSet(viewsets.ModelViewSet):
    queryset = Habit.objects.all()
    serializer_class = HabitSerializer

    @action(detail=True, methods=['post'])
    def log_completion(self, request, pk=None):
        habit = self.get_object()
        log_date = request.data.get('date', timezone.now().date())
        
        # Convert string date to date object if necessary
        if isinstance(log_date, str):
            log_date = datetime.strptime(log_date, '%Y-%m-%d').date()

        # Check if already logged for this date
        if habit.is_completed_for_date(log_date):
            return Response(
                {'error': 'Habit already logged for this date'},
                status=status.HTTP_400_BAD_REQUEST
            )

        HabitLog.objects.create(
            habit=habit,
            log_date=log_date,
            notes=request.data.get('notes', '')
        )
        return Response({'status': 'logged'})

    @action(detail=True)
    def completion_history(self, request, pk=None):
        habit = self.get_object()
        days = int(request.query_params.get('days', 30))
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        
        logs = habit.habitlog_set.filter(
            log_date__range=[start_date, end_date]
        ).order_by('log_date')
        
        return Response(HabitLogSerializer(logs, many=True).data)

class HabitRegisterView(APIView):
    def get(self, request):
        # Get date range from query params
        range_type = request.query_params.get('range', '7days')
        end_date = timezone.now().date()
        
        if range_type == '7days':
            start_date = end_date - timedelta(days=6)
        elif range_type == '30days':
            start_date = end_date - timedelta(days=29)
        elif range_type == 'custom':
            try:
                start_date = datetime.strptime(
                    request.query_params.get('start_date'),
                    '%Y-%m-%d'
                ).date()
                end_date = datetime.strptime(
                    request.query_params.get('end_date'),
                    '%Y-%m-%d'
                ).date()
            except (ValueError, TypeError):
                return Response(
                    {'error': 'Invalid date format. Use YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            return Response(
                {'error': 'Invalid range type'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Generate date range
        date_range = [
            start_date + timedelta(days=x)
            for x in range((end_date - start_date).days + 1)
        ]

        serializer = HabitRegisterSerializer({
            'date_range': date_range
        })
        return Response(serializer.data)

class HabitLogViewSet(viewsets.ModelViewSet):
    queryset = HabitLog.objects.all()
    serializer_class = HabitLogSerializer

class HabitStatsView(generics.RetrieveAPIView):
    serializer_class = HabitStatsSerializer

    def get_object(self):
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        habits = Habit.objects.all()
        total_habits = habits.count()
        
        # Changed habitlog_set to habitlog
        active_habits = habits.filter(
            habitlog__completed_at__gte=start_date
        ).distinct().count()
        
        completion_logs = HabitLog.objects.filter(
            completed_at__range=[start_date, end_date]
        )
        
        total_possible = total_habits * 30
        completion_rate = (completion_logs.count() / total_possible * 100) if total_possible > 0 else 0
        
        # Get longest streak
        longest_streak = max([habit.get_current_streak() for habit in habits]) if habits.exists() else 0
        
        # Changed habitlog_set to habitlog in annotation
        most_consistent = habits.annotate(
            log_count=Count('habitlog')
        ).order_by('-log_count').first()
        
        return {
            'total_habits': total_habits,
            'active_habits': active_habits,
            'completion_rate': round(completion_rate, 1),
            'longest_streak': longest_streak,
            'most_consistent_habit': most_consistent.name if most_consistent else None
        }

class HabitTrendsView(generics.ListAPIView):
    serializer_class = HabitSerializer

    def get_queryset(self):
        days = int(self.request.query_params.get('days', 30))
        return Habit.objects.all().annotate(
            completion_count=Count('habitlog')
        ).order_by('-completion_count')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        days = int(request.query_params.get('days', 30))
        
        data = {
            'trends': self.get_serializer(queryset, many=True, context={'days': days}).data,
            'total_completions': HabitLog.objects.count(),
            'daily_average': HabitLog.objects.values('completed_at__date').annotate(
                count=Count('id')
            ).aggregate(Avg('count'))['count__avg']
        }
        
        return Response(data)

class IncomeGroupViewSet(viewsets.ModelViewSet):
    queryset = IncomeGroup.objects.all()
    serializer_class = IncomeGroupSerializer

class ExpenseGroupViewSet(viewsets.ModelViewSet):
    queryset = ExpenseGroup.objects.all()
    serializer_class = ExpenseGroupSerializer

class PartyTransactionFilter(django_filters.FilterSet):
    date_range = django_filters.CharFilter(method='filter_date_range')
    search = django_filters.CharFilter(method='filter_search')

    class Meta:
        model = PartyTransaction
        fields = ['date_range', 'search']

    def filter_date_range(self, queryset, name, value):
        today = timezone.now().date()
        
        if value == 'today':
            return queryset.filter(date=today)
        elif value == 'yesterday':
            return queryset.filter(date=today - timedelta(days=1))
        elif value == 'this_month':
            return queryset.filter(
                date__year=today.year,
                date__month=today.month
            )
        elif value and '_to_' in value:  # Custom date range
            start_date, end_date = value.split('_to_')
            try:
                start = datetime.strptime(start_date, '%Y-%m-%d').date()
                end = datetime.strptime(end_date, '%Y-%m-%d').date()
                return queryset.filter(date__range=[start, end])
            except ValueError:
                return queryset
        return queryset

    def filter_search(self, queryset, name, value):
        if value:
            return queryset.filter(
                Q(party__party_name__icontains=value) |
                Q(transaction_type__icontains=value) |
                Q(notes__icontains=value) |
                Q(amount__icontains=value)
            )
        return queryset

class PartyTransactionViewSet(viewsets.ModelViewSet):
    queryset = PartyTransaction.objects.all().select_related('party').order_by('-date', '-created_at')
    serializer_class = PartyTransactionSerializer
    filter_backends = [django_filters.DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = PartyTransactionFilter
    ordering_fields = ['date', 'amount', 'created_at']

    def get_queryset(self):
        return super().get_queryset().select_related('party')

class DebtPaymentScheduleViewSet(viewsets.ModelViewSet):
    queryset = DebtPaymentSchedule.objects.all()
    serializer_class = DebtPaymentScheduleSerializer

class IncomeViewSet(viewsets.ModelViewSet):
    queryset = Income.objects.all()
    serializer_class = IncomeSerializer

    def get_queryset(self):
        queryset = Income.objects.all().select_related('income_group')
        
        # Handle date filtering
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        report_type = self.request.query_params.get('type')
        search = self.request.query_params.get('search')

        if report_type == 'today':
            date_from = date_to = timezone.now().date()
        elif report_type == 'yesterday':
            date_from = date_to = timezone.now().date() - timedelta(days=1)
        elif report_type == 'this_month':
            today = timezone.now().date()
            date_from = today.replace(day=1)
            date_to = today

        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)

        # Handle search
        if search:
            queryset = queryset.filter(
                Q(income_name__icontains=search) |
                Q(notes__icontains=search) |
                Q(income_group__group_name__icontains=search)
            )

        return queryset.order_by('-date', '-created_at')

class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer

    def get_queryset(self):
        queryset = Expense.objects.all().select_related('expense_group')
        
        # Handle date filtering
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        report_type = self.request.query_params.get('type')
        search = self.request.query_params.get('search')

        if report_type == 'today':
            date_from = date_to = timezone.now().date()
        elif report_type == 'yesterday':
            date_from = date_to = timezone.now().date() - timedelta(days=1)
        elif report_type == 'this_month':
            today = timezone.now().date()
            date_from = today.replace(day=1)
            date_to = today

        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)

        # Handle search
        if search:
            queryset = queryset.filter(
                Q(expense_name__icontains=search) |
                Q(notes__icontains=search) |
                Q(expense_group__group_name__icontains=search)
            )

        return queryset.order_by('-date', '-created_at')

    @action(detail=False, methods=['get'])
    def report(self, request):
        queryset = self.get_queryset()
        total = queryset.aggregate(total=Sum('amount'))['total'] or 0
        
        # Get group-wise totals
        group_totals = queryset.values(
            'expense_group__group_name'
        ).annotate(
            total=Sum('amount')
        ).order_by('-total')

        serializer = self.get_serializer(queryset, many=True)
        
        return Response({
            'total': total,
            'group_totals': group_totals,
            'transactions': serializer.data
        })

class PartyLedgerViewSet(viewsets.ModelViewSet):
    queryset = PartyLedger.objects.all()
    serializer_class = PartyLedgerSerializer

    @action(detail=False, methods=['get'])
    def total_outstanding(self, request):
        parties = self.get_queryset()
        data = []
        
        for party in parties:
            current_balance = party.get_current_balance()
            data.append({
                'party_name': party.party_name,
                'current_balance': current_balance,
                'balance_nature': 'Receivable' if current_balance > 0 else 'Payable'
            })
            
        return Response(data)

    @action(detail=True, methods=['get'])
    def statement(self, request, pk=None):
        party = self.get_object()
        transactions = PartyTransaction.objects.filter(party=party).order_by('date')
        
        running_balance = party.opening_balance
        if party.balance_nature == 'Payable':
            running_balance = -running_balance

        statement = []
        statement.append({
            'date': party.created_at.date(),
            'description': 'Opening Balance',
            'amount': abs(party.opening_balance),
            'type': party.balance_nature,
            'running_balance': running_balance
        })

        for transaction in transactions:
            if transaction.transaction_type == 'Money In':
                running_balance += transaction.amount
            else:
                running_balance -= transaction.amount

            statement.append({
                'date': transaction.date,
                'description': transaction.notes or transaction.transaction_type,
                'amount': transaction.amount,
                'type': transaction.transaction_type,
                'running_balance': running_balance
            })

        return Response({
            'party_name': party.party_name,
            'statement': statement,
            'net_balance': running_balance
        })

class DebtPaymentViewSet(viewsets.ModelViewSet):
    queryset = DebtPayment.objects.all()
    serializer_class = DebtPaymentSerializer

    def create(self, request, *args, **kwargs):
        debt_id = request.data.get('debt')
        schedule_id = request.data.get('schedule')
        
        # Validate debt exists
        debt = get_object_or_404(Debt, id=debt_id)
        
        # Create payment
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class DebtViewSet(viewsets.ModelViewSet):
    queryset = Debt.objects.all()
    serializer_class = DebtSerializer

    @action(detail=False, methods=['get'])
    def total_outstanding(self, request):
        debts = self.get_queryset()
        data = []
        
        for debt in debts:
            schedules = debt.debtpaymentschedule_set.all()
            total_expected = schedules.aggregate(
                total=Sum('expected_amount'))['total'] or 0
            total_paid = schedules.aggregate(
                total=Sum('paid_amount'))['total'] or 0
            net_balance = total_expected - total_paid
            
            data.append({
                'id': debt.id,  # Added this line
                'debt_name': debt.debt_name,
                'debt_type': debt.debt_type,  # Added this line
                'total_expected': total_expected,
                'total_paid': total_paid,
                'net_balance': net_balance,
                'status': debt.status,
                'created_at': debt.created_at  # Added this line
            })
            
        return Response(data)

    @action(detail=True, methods=['get'])
    def statement(self, request, pk=None):
        debt = self.get_object()
        schedules = debt.debtpaymentschedule_set.all().order_by('s_no')
        
        total_expected = schedules.aggregate(
            total=Sum('expected_amount'))['total'] or 0
        total_paid = schedules.aggregate(
            total=Sum('paid_amount'))['total'] or 0
        
        return Response({
            'debt_name': debt.debt_name,
            'debt_type': debt.debt_type,
            'status': debt.status,
            'total_expected': total_expected,
            'total_paid': total_paid,
            'net_balance': total_expected - total_paid,
            'schedules': DebtPaymentScheduleSerializer(schedules, many=True).data
        })

@api_view(['GET'])
def dashreport_work_updates(request):
    """Get work updates for dashreport based on date range"""
    try:
        # Get date range parameters
        date_range = request.query_params.get('range', 'today').lower()
        
        # Calculate date range based on parameter
        if date_range == 'yesterday':
            start_date = end_date = datetime.now().date() - timedelta(days=1)
        elif date_range == 'today':
            start_date = end_date = datetime.now().date()
        elif date_range == 'custom':
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            
            if not start_date or not end_date:
                return Response(
                    {'error': 'Both start_date and end_date are required for custom range'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'error': 'Invalid date format. Use YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            return Response(
                {'error': 'Invalid range parameter. Use yesterday, today, or custom'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Query work updates
        updates = WorkUpdate.objects.filter(
            date__range=[start_date, end_date]
        ).select_related('head').order_by('-date')

        serializer = WorkUpdateReportSerializer(updates, many=True)
        
        return Response({
            'range': date_range,
            'start_date': start_date,
            'end_date': end_date,
            'updates': serializer.data
        })
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
def dashtimeview(request):
    """Get category summary report for a date range"""
    try:
        # Get date range parameters
        date_range = request.query_params.get('range', 'today').lower()
        
        # Calculate date range based on parameter
        if date_range == 'yesterday':
            start_date = end_date = timezone.now().date() - timedelta(days=1)
        elif date_range == 'today':
            start_date = end_date = timezone.now().date()
        elif date_range == 'custom':
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            
            if not start_date or not end_date:
                return Response(
                    {'error': 'Both start_date and end_date are required for custom range'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'error': 'Invalid date format. Use YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            return Response(
                {'error': 'Invalid range parameter. Use yesterday, today, or custom'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Query categories and time entries
        categories = Category.objects.all()
        summary_data = []
        
        for category in categories:
            total_duration = TimeEntry.objects.filter(
                activity__category=category,
                start_time__date__gte=start_date,
                start_time__date__lte=end_date,
                end_time__isnull=False
            ).aggregate(
                total=Sum('duration_minutes')
            )['total'] or 0
            
            if total_duration > 0:
                summary_data.append({
                    'category_id': category.id,
                    'category_name': category.name,
                    'category_color': category.color,
                    'total_duration': total_duration,
                    'percentage': 0  # Will be calculated below
                })
        
        # Calculate percentages
        total_time = sum(item['total_duration'] for item in summary_data)
        if total_time > 0:
            for item in summary_data:
                item['percentage'] = round((item['total_duration'] / total_time) * 100, 1)
        
        return Response({
            'range': date_range,
            'start_date': start_date,
            'end_date': end_date,
            'summary': summary_data
        })
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
def dashtaskview(request):
    """Get task summary and completed tasks for a date range"""
    try:
        # Get date range parameters
        date_range = request.query_params.get('range', 'today').lower()
        
        # Calculate date range based on parameter
        if date_range == 'yesterday':
            start_date = end_date = datetime.now().date() - timedelta(days=1)
        elif date_range == 'today':
            start_date = end_date = datetime.now().date()
        elif date_range == 'custom':
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            
            if not start_date or not end_date:
                return Response(
                    {'error': 'Both start_date and end_date are required for custom range'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'error': 'Invalid date format. Use YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            return Response(
                {'error': 'Invalid range parameter. Use yesterday, today, or custom'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Query tasks
        tasks = Task.objects.filter(
            task_date__range=[start_date, end_date]
        )

        # Calculate summary
        total_tasks = tasks.count()
        completed_tasks = tasks.filter(status='COMPLETED').count()
        pending_tasks = total_tasks - completed_tasks

        # Serialize task data
        task_data = tasks.values(
            'id', 'title', 'status', 'priority', 'task_date', 'completed_at'
        )

        return Response({
            'range': date_range,
            'start_date': start_date,
            'end_date': end_date,
            'summary': {
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks,
                'pending_tasks': pending_tasks
            },
            'tasks': task_data
        })
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
def dashhabitview(request):
    """Get habit summary and list of completed/pending habits for a date range"""
    try:
        # Get date range parameters
        date_range = request.query_params.get('range', 'today').lower()
        
        # Calculate date range based on parameter
        if date_range == 'yesterday':
            start_date = end_date = timezone.now().date() - timedelta(days=1)
        elif date_range == 'today':
            start_date = end_date = timezone.now().date()
        elif date_range == 'custom':
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            
            if not start_date or not end_date:
                return Response(
                    {'error': 'Both start_date and end_date are required for custom range'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'error': 'Invalid date format. Use YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            return Response(
                {'error': 'Invalid range parameter. Use yesterday, today, or custom'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Query habits and logs
        habits = Habit.objects.all()
        logs = HabitLog.objects.filter(completed_at__date__range=[start_date, end_date])

        # Calculate summary
        total_habits = habits.count()
        completed_habits = logs.values('habit').distinct().count()
        pending_habits = total_habits - completed_habits

        # Get completed and pending habit lists
        completed_habit_list = habits.filter(
            id__in=logs.values('habit').distinct()
        ).values('id', 'name', 'frequency', 'created_at')

        pending_habit_list = habits.exclude(
            id__in=logs.values('habit').distinct()
        ).values('id', 'name', 'frequency', 'created_at')

        return Response({
            'range': date_range,
            'start_date': start_date,
            'end_date': end_date,
            'summary': {
                'total_habits': total_habits,
                'completed_habits': completed_habits,
                'pending_habits': pending_habits
            },
            'completed_habits': completed_habit_list,
            'pending_habits': pending_habit_list
        })
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
def dashgoalview(request):
    range_type = request.GET.get('range', 'today')
    today = timezone.now().date()

    # Set the date range based on the request
    if range_type == 'today':
        start_date = end_date = today
    elif range_type == 'yesterday':
        start_date = end_date = today - timedelta(days=1)
    elif range_type == 'custom':
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        if not start_date or not end_date:
            return Response(
                {"error": "start_date and end_date are required for custom range"},
                status=400
            )
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"},
                status=400
            )
    else:
        return Response(
            {"error": "Invalid range type. Use 'today', 'yesterday', or 'custom'"},
            status=400
        )

    # Get subprocesses created within or before the date range
    subprocesses = SubProcess.objects.filter(
        created_at__date__lte=end_date,  # Created on or before end date
        created_at__date__gte=start_date  # Created on or after start date
    ).select_related('goal')

    # Get completed subprocesses
    completed_subprocesses = subprocesses.filter(
        status='DONE',
        updated_at__date__gte=start_date,  # Completed on or after start date
        updated_at__date__lte=end_date     # Completed on or before end date
    ).values('id', 'name', 'goal__name', 'estimated_days', 'created_at', 'updated_at')

    # Get pending subprocesses
    pending_subprocesses = subprocesses.exclude(
        status='DONE'
    ).values('id', 'name', 'goal__name', 'estimated_days', 'created_at')

    # Calculate summary
    total_subprocesses = subprocesses.count()
    completed_count = completed_subprocesses.count()
    pending_count = pending_subprocesses.count()

    response_data = {
        'range': range_type,
        'start_date': start_date,
        'end_date': end_date,
        'summary': {
            'total_subprocesses': total_subprocesses,
            'completed_subprocesses': completed_count,
            'pending_subprocesses': pending_count,
            'completion_percentage': round((completed_count / total_subprocesses * 100) if total_subprocesses > 0 else 0, 2)
        },
        'completed_subprocesses': [
            {
                **subprocess,
                'created_at': subprocess['created_at'].strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': subprocess['updated_at'].strftime('%Y-%m-%d %H:%M:%S')
            }
            for subprocess in completed_subprocesses
        ],
        'pending_subprocesses': [
            {
                **subprocess,
                'created_at': subprocess['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            }
            for subprocess in pending_subprocesses
        ],
        'focus_goals': list(Goal.objects.filter(
            status='FOCUS',
            created_at__date__lte=end_date,
            created_at__date__gte=start_date
        ).values('id', 'name', 'created_at'))
    }

    return Response(response_data)

@api_view(['GET'])
def dashboard_report(request):
    """Get consolidated dashboard report for all metrics"""
    try:
        # Get date range parameters
        date_range = request.query_params.get('range', 'today').lower()
        
        # Calculate date range based on parameter
        if date_range == 'yesterday':
            start_date = end_date = timezone.now().date() - timedelta(days=1)
        elif date_range == 'today':
            start_date = end_date = timezone.now().date()
        elif date_range == 'custom':
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            
            if not start_date or not end_date:
                return Response(
                    {'error': 'Both start_date and end_date are required for custom range'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'error': 'Invalid date format. Use YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            return Response(
                {'error': 'Invalid range parameter. Use yesterday, today, or custom'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 1. Time Entries Summary
        categories = Category.objects.all()
        time_summary = []
        
        for category in categories:
            total_duration = TimeEntry.objects.filter(
                activity__category=category,
                start_time__date__gte=start_date,
                start_time__date__lte=end_date,
                end_time__isnull=False
            ).aggregate(
                total=Sum('duration_minutes')
            )['total'] or 0
            
            if total_duration > 0:
                time_summary.append({
                    'category_name': category.name,
                    'category_color': category.color,
                    'total_duration': total_duration,
                    'percentage': 0
                })
        
        total_time = sum(item['total_duration'] for item in time_summary)
        if total_time > 0:
            for item in time_summary:
                item['percentage'] = round((item['total_duration'] / total_time) * 100, 1)

        # 2. Tasks Summary
        tasks = Task.objects.filter(task_date__range=[start_date, end_date])
        task_summary = {
            'total_tasks': tasks.count(),
            'completed_tasks': tasks.filter(status='COMPLETED').count(),
            'pending_tasks': tasks.filter(status='PENDING').count(),
            'tasks_list': tasks.values('id', 'title', 'status', 'priority', 'task_date', 'completed_at')
        }

        # 3. Work Updates
        updates = WorkUpdate.objects.filter(
            date__range=[start_date, end_date]
        ).select_related('head').order_by('-date')
        work_updates = WorkUpdateReportSerializer(updates, many=True).data

        # 4. Habits Summary
        habits = Habit.objects.all()
        logs = HabitLog.objects.filter(completed_at__date__range=[start_date, end_date])
        habit_summary = {
            'total_habits': habits.count(),
            'completed_habits': logs.values('habit').distinct().count(),
            'pending_habits': habits.count() - logs.values('habit').distinct().count(),
            'completed_list': habits.filter(
                id__in=logs.values('habit').distinct()
            ).values('id', 'name', 'frequency', 'created_at'),
            'pending_list': habits.exclude(
                id__in=logs.values('habit').distinct()
            ).values('id', 'name', 'frequency', 'created_at')
        }

        # 5. Goals Summary
        subprocesses = SubProcess.objects.filter(goal__status=GoalStatus.FOCUS)
        completed_subprocesses = subprocesses.filter(
            status=ProcessStatus.DONE,
            completed_at__date__range=[start_date, end_date]
        )
        pending_subprocesses = subprocesses.filter(status=ProcessStatus.PENDING)
        
        goal_summary = {
            'total_subprocesses': subprocesses.count(),
            'completed_subprocesses': completed_subprocesses.count(),
            'pending_subprocesses': pending_subprocesses.count(),
            'completed_list': completed_subprocesses.values(
                'id', 'name', 'goal__name', 'estimated_days', 'completed_at'
            ),
            'pending_list': pending_subprocesses.values(
                'id', 'name', 'goal__name', 'estimated_days'
            )
        }

        return Response({
            'range': date_range,
            'start_date': start_date,
            'end_date': end_date,
            'time_summary': time_summary,
            'task_summary': task_summary,
            'work_updates': work_updates,
            'habit_summary': habit_summary,
            'goal_summary': goal_summary
        })

    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

class DailyScheduleViewSet(viewsets.ViewSet):
    def list(self, request):
        today = timezone.now().date()
        
        # Get today's habits - removed is_active filter
        habits = Habit.objects.filter(
            is_reminder_active=True  # Using is_reminder_active instead of is_active
        ).order_by('reminder_time')
        
        # Get today's tasks
        tasks = Task.objects.filter(
            task_date=today,
            status__in=['PENDING', 'IN_PROGRESS']
        ).order_by('task_time')
        
        # Get focused sub-processes
        subprocesses = SubProcess.objects.filter(
            focus=True,
            status=ProcessStatus.PENDING
        ).order_by('sort_order')

        # Serialize all items
        schedule_items = []
        
        # Add habits with times
        schedule_items.extend(DailyHabitSerializer(habits, many=True).data)
        
        # Add tasks with times
        schedule_items.extend(DailyTaskSerializer(tasks, many=True).data)
        
        # Add focused sub-processes
        schedule_items.extend(DailySubProcessSerializer(subprocesses, many=True).data)

        # Sort items by time (if available)
        schedule_items.sort(
            key=lambda x: (
                x.get('time') or '23:59:59'  # Put items without time at the end
            )
        )

        return Response({
            'date': today,
            'schedule_items': schedule_items
        })
    
    @action(detail=True, methods=['post'], url_path='complete-habit')
    def complete_habit(self, request, pk=None):
        try:
            habit = Habit.objects.get(pk=pk)
            today = timezone.now().date()
            
            # Toggle completion
            if habit.is_completed_for_date(today):
                # If already completed, remove the log
                HabitLog.objects.filter(habit=habit, log_date=today).delete()
                completed = False
            else:
                # If not completed, create a log
                HabitLog.objects.create(habit=habit, log_date=today)
                completed = True
            
            return Response({'completed': completed})
        except Habit.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'], url_path='update-task')
    def update_task(self, request, pk=None):
        try:
            task = Task.objects.get(pk=pk)
            new_status = request.data.get('status')
            
            if new_status not in dict(Task.STATUS_CHOICES):
                return Response(
                    {'error': 'Invalid status'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            task.status = new_status
            if new_status == 'COMPLETED':
                task.completed_at = timezone.now()
            task.save()
            
            return Response({'status': task.status})
        except Task.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'], url_path='complete-subprocess')
    def complete_subprocess(self, request, pk=None):
        try:
            subprocess = SubProcess.objects.get(pk=pk)
            subprocess.status = ProcessStatus.DONE
            subprocess.completed_at = timezone.now()
            subprocess.save()
            
            return Response({'status': subprocess.status})
        except SubProcess.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)