from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create a router and register our viewsets with it
router = DefaultRouter()
router.register(r'categories', views.CategoryViewSet, basename='category')
router.register(r'activities', views.ActivityViewSet, basename='activity')
router.register(r'time-entries', views.TimeEntryViewSet, basename='timeentry')
router.register(r'goals', views.GoalViewSet)
router.register(r'sub-processes', views.SubProcessViewSet)
router.register(r'vision', views.VisionViewSet, basename='vision') 
router.register(r'work-heads', views.WorkHeadViewSet, basename='work-head')
router.register(r'work-updates', views.WorkUpdateViewSet, basename='work-update')
router.register(r'tasks', views.TaskViewSet, basename='task')
router.register(r'habits', views.HabitViewSet, basename='habit')
router.register(r'habit-logs', views.HabitLogViewSet, basename='habit-log')
router.register(r'income-groups', views.IncomeGroupViewSet, basename='income-group')
router.register(r'expense-groups', views.ExpenseGroupViewSet, basename='expense-group')
router.register(r'incomes', views.IncomeViewSet)
router.register(r'expenses', views.ExpenseViewSet)
router.register(r'party-ledgers', views.PartyLedgerViewSet)
router.register(r'party-transactions', views.PartyTransactionViewSet, basename='party-transaction')
router.register(r'debts', views.DebtViewSet)
router.register(r'debt-payment-schedules', views.DebtPaymentScheduleViewSet, basename='debt-payment-schedule')
router.register(r'debt-payments', views.DebtPaymentViewSet, basename='debt-payment')
router.register(r'daily-schedule', views.DailyScheduleViewSet, basename='daily-schedule')


urlpatterns = [
    # Include the router URLs in our urlpatterns
    path('', include(router.urls)),
    path('reports/category/', views.category_report, name='category-report'),
    path('reports/category-summary/', views.category_summary_report, name='category-summary-report'),
    path('reports/activity/', views.activity_report, name='activity-report'),
    path('reports/activity-summary/', views.activity_summary_report, name='activity-summary-report'),
    path('reports/time-gaps/', views.time_entry_gaps, name='time-entry-gaps'),
    path('reports/recent-updates/', views.recent_updates_report, name='recent-updates-report'),
    path('reports/work-head-summary/', views.work_head_summary, name='work-head-summary'),
    path('reports/monthly-counts/', views.monthly_update_counts, name='monthly-update-counts'),
    path('reports/work-updates/search/', views.work_update_search, name='work-update-search'),
    path('focused-sub-processes/', views.FocusedSubProcessView.as_view(), name='focused-sub-processes'),
    path('tasks/summary/', views.TaskSummaryView.as_view(), name='task-summary'),
    path('tasks/upcoming/', views.UpcomingTasksView.as_view(), name='upcoming-tasks'),
    path('tasks/completion-stats/', views.TaskCompletionStatsView.as_view(), name='completion-stats'),
    path('tasks/completed/', views.CompletedTasksView.as_view(), name='completed-tasks'),
    path('habit-register/', views.HabitRegisterView.as_view(), name='habit-register'),
    path('habit-stats/', views.HabitStatsView.as_view(), name='habit-stats'),
    path('habit-trends/', views.HabitTrendsView.as_view(), name='habit-trends'),
    path('debts/<int:debt_id>/payments/', views.DebtPaymentViewSet.as_view({'get': 'list','post': 'create'}), name='debt-payments'),
    path('dashtimeview/', views.dashtimeview, name='dashtimeview'),
    path('dashtaskview/', views.dashtaskview, name='dashtaskview'),
    path('dashreport/work-updates/', views.dashreport_work_updates, name='dashreport-work-updates'),
    path('dashhabitview/', views.dashhabitview, name='dashhabitview'),
    path('dashgoalview/', views.dashgoalview, name='dashgoalview'),
    path('dashboard-report/', views.dashboard_report, name='dashboard-report'),
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
]

app_name = 'totfapp'