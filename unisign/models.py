from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from jalali_date import datetime2jalali
import jdatetime
from datetime import datetime
from django.conf import settings
import time
import os

# Create your models here.

class Teacher(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name='کاربر')
    national_id = models.CharField(max_length=20, unique=True, verbose_name='کدملی')
    first_name = models.CharField(max_length=50, verbose_name='نام')
    last_name = models.CharField(max_length=50, verbose_name='نام خانوادگی')

    class Meta:
        db_table = 'teacher'
        verbose_name = 'استاد'
        verbose_name_plural = 'اساتید'

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class Term(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name='نام ترم')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'term'
        verbose_name = 'ترم'
        verbose_name_plural = 'ترم‌ها'

class Course(models.Model):
    course_code = models.CharField(max_length=20, verbose_name='کد درس')
    course_name = models.CharField(max_length=100, verbose_name='نام درس')
    group_code = models.CharField(max_length=20, verbose_name='کد گروه درسی')
    teacher = models.ForeignKey('Teacher', on_delete=models.CASCADE, verbose_name='استاد')
    max_capacity = models.IntegerField(default=0, verbose_name='حداکثر ظرفیت')
    student_count = models.IntegerField(default=0, verbose_name='تعداد دانشجو')
    empty_capacity = models.IntegerField(default=0, verbose_name='ظرفیت خالی')
    class_time = models.CharField(max_length=100, blank=True, null=True, verbose_name='زمان تشکیل کلاس')
    faculty_id = models.CharField(max_length=20, blank=True, null=True, verbose_name='شناسه دانشکده')
    group_type = models.CharField(max_length=50, blank=True, null=True, verbose_name='نوع گروه درسی')
    exam_location = models.CharField(max_length=100, blank=True, null=True, verbose_name='محل آزمون')
    exam_date = models.DateTimeField(blank=True, null=True, verbose_name='تاریخ و زمان امتحان')
    group_id = models.CharField(max_length=20, blank=True, null=True, verbose_name='شناسه گروه درسی')
    registration_date = models.DateTimeField(blank=True, null=True, verbose_name='تاریخ و زمان ثبت')
    term = models.ForeignKey(Term, on_delete=models.CASCADE, verbose_name='ترم', null=True, blank=True)

    def save(self, *args, **kwargs):
        if isinstance(self.exam_date, str):
            try:
                # Parse Jalali date and time (format: YYYY/MM/DD HH:MM)
                if '-' in self.exam_date:
                    date_part, time_part = self.exam_date.split('-')
                else:
                    date_part = self.exam_date
                    time_part = '00:00'

                
                date_parts = date_part.split('/')
                time_parts = time_part.split(':')
                
                # Convert Jalali to Gregorian
                jalali_date = jdatetime.date(
                    int(date_parts[0]),
                    int(date_parts[1]),
                    int(date_parts[2])
                )
                gregorian_date = jalali_date.togregorian()
                
                # Create datetime object with timezone
                self.exam_date = timezone.make_aware(datetime(
                    gregorian_date.year,
                    gregorian_date.month,
                    gregorian_date.day,
                    int(time_parts[0]),
                    int(time_parts[1])
                ))
            except (ValueError, IndexError):
                self.exam_date = None
        super().save(*args, **kwargs)

    def exam_date_jalali(self):
        if self.exam_date:
            return datetime2jalali(self.exam_date).strftime('%Y/%m/%d - %H:%M:%S')
        return "—"
    exam_date_jalali.short_description = 'تاریخ و زمان امتحان'

    def registration_date_jalali(self):
        if self.registration_date:
            return datetime2jalali(self.registration_date).strftime('%Y/%m/%d - %H:%M:%S')
        return "—"
    registration_date_jalali.short_description = 'تاریخ و زمان ثبت'

    class Meta:
        db_table = 'course'
        verbose_name = 'درس'
        verbose_name_plural = 'دروس'

    def __str__(self):
        return f"{self.course_code} - {self.course_name} ({self.group_code})"

class Student(models.Model):
    first_name = models.CharField(max_length=50, verbose_name='نام')
    last_name = models.CharField(max_length=50, verbose_name='نام خانوادگی')
    national_id = models.CharField(max_length=20, verbose_name='کدملی')
    student_number = models.CharField(max_length=20, verbose_name='شماره دانشجویی')
    entry_term = models.CharField(max_length=20, verbose_name='ترم ورود')
    gender = models.CharField(max_length=10, verbose_name='جنسیت')
    major_code = models.CharField(max_length=20, verbose_name='کد رشته')
    major_name = models.CharField(max_length=100, verbose_name='رشته')
    photo = models.ImageField(upload_to='students/', null=True, blank=True, verbose_name='عکس')

    class Meta:
        db_table = 'student'
        verbose_name = 'دانشجو'
        verbose_name_plural = 'دانشجویان'
        unique_together = ('national_id', 'student_number')

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.student_number})"

class StudentCourse(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, verbose_name='دانشجو')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, verbose_name='درس')
    term = models.ForeignKey(Term, on_delete=models.CASCADE, verbose_name='ترم', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ثبت')

    class Meta:
        db_table = 'student_course'
        verbose_name = 'ارتباط درس و دانشجو'
        verbose_name_plural = 'انتخاب واحد دانشجویان'
        unique_together = ('student', 'course', 'term')

    def __str__(self):
        return f"{self.student.first_name} {self.student.last_name} - {self.course.course_name} ({self.term.name if self.term else 'بدون ترم'})"

class Attendance(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, verbose_name='دانشجو')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, verbose_name='درس')
    signature_image = models.ImageField(upload_to='signatures/', verbose_name='امضای دیجیتال')
    signed_at = models.DateTimeField(auto_now_add=True, verbose_name='زمان امضا')
    term = models.ForeignKey(Term, on_delete=models.CASCADE, verbose_name='ترم', null=True, blank=True)
    registered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='ثبت کننده')

    class Meta:
        db_table = 'attendance'
        verbose_name = 'حضور و غیاب'
        verbose_name_plural = 'حضور و غیاب‌ها'
        unique_together = ('student', 'course', 'signed_at')

    def __str__(self):
        return f"{self.student.first_name} {self.student.last_name} - {self.course.course_name} ({self.signed_at.strftime('%Y/%m/%d %H:%M')})"

    def signed_at_jalali(self):
        return datetime2jalali(self.signed_at).strftime('%Y/%m/%d - %H:%M:%S')
    signed_at_jalali.short_description = 'زمان امضا'

def signature_file_path(instance, filename):
    # Get file extension
    ext = os.path.splitext(filename)[1]
    # Generate timestamp-based filename
    timestamp = int(time.time() * 1000)  # milliseconds
    # Return path: signatures/student_{id}_course_{id}_{timestamp}{ext}
    return f'signatures/student_{instance.student.id}_course_{instance.course.id}_{timestamp}{ext}'

class StudentSignature(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, verbose_name='دانشجو')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, verbose_name='درس')
    signed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name='امضا کننده')
    signature_image = models.ImageField(upload_to=signature_file_path, verbose_name='تصویر امضا')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ و زمان امضا')

    class Meta:
        db_table = 'student_signature'
        verbose_name = 'امضای دانشجو'
        verbose_name_plural = 'امضاهای دانشجویان'
        unique_together = ('student', 'course')

    def __str__(self):
        return f"امضای {self.student.first_name} {self.student.last_name} برای درس {self.course.course_name}"

    def created_at_jalali(self):
        return datetime2jalali(self.created_at).strftime('%Y/%m/%d - %H:%M')
