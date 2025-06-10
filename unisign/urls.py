from django.urls import path
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from . import views
from . import api_views
from .views import StudentSignatureView

urlpatterns = [
    path('', RedirectView.as_view(url='admin/', permanent=True)),
    path('admin/', admin.site.urls),
    path('upload-excel/', views.upload_excel, name='upload-excel'),
    path('teacher/dashboard/', views.teacher_dashboard, name='teacher-dashboard'),
    path('teacher/register/', views.teacher_register, name='teacher-register'),
    path('upload-pdf/', views.upload_course_pdf, name='upload_course_pdf'),
    path('api/login/', api_views.login_view, name='api-login'),
    path('api/courses/exam-dates/', api_views.courses_with_exam_dates, name='api-courses-exam-dates'),
    path('api/statistics/overall/', api_views.overall_statistics, name='api-overall-statistics'),
    path('api/courses/<int:course_id>/students/', api_views.get_course_students, name='api-course-students'),
    path('api/students/<int:student_id>/signature/<int:course_id>/', StudentSignatureView.as_view(), name='student_signature'),
    path('api/courses/search/', api_views.search_courses, name='api-search-courses'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) 