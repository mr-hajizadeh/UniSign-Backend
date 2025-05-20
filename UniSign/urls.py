from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from .views import (
    get_course_students,
    upload_signature,
    add_course,
    get_daily_courses,
    get_absent_students,
    get_daily_course_absences,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(url='/admin/', permanent=False)),
    path('add-course/', add_course, name='add-course'),
    path('api/courses/<int:course_id>/students/', get_course_students, name='course-students'),
    path('api/students/<int:student_id>/signature/', upload_signature, name='upload-signature'),
    path('api/daily-courses/', get_daily_courses, name='daily_courses'),
    path('api/courses/<int:course_id>/absent-students/', get_absent_students, name='absent_students'),
    path('api/daily-course-absences/', get_daily_course_absences, name='daily_course_absences'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
