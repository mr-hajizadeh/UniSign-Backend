from django.db import models
from jalali_date import datetime2jalali


class Course(models.Model):
    term_info = models.CharField(max_length=100, verbose_name='نیمسال')
    course_name = models.CharField(max_length=100, verbose_name="نام درس")
    exam_time = models.DateTimeField(verbose_name="تاریخ و ساعت آزمون")
    professor = models.CharField(max_length=100, verbose_name='استاد')
    group_info = models.CharField(max_length=100, verbose_name='کد گروه درسی')
    pdf_file = models.FileField(upload_to='pdfs/', blank=True, null=True, verbose_name='pdf')

    def exam_time_jalali(self):
        return datetime2jalali(self.exam_time).strftime('%Y/%m/%d - %H:%M:%S')

    exam_time_jalali.short_description = 'تاریخ و زمان آزمون'

    class Meta:
        verbose_name = "درس"
        verbose_name_plural = "دروس"

    def __str__(self):
        return self.course_name


def student_image_upload_path(instance, filename):
    return f"students/{instance.national_id}/{filename}"


class Student(models.Model):
    row = models.CharField(max_length=10, verbose_name='')
    exam_place = models.CharField(max_length=100, verbose_name='محل آزمون')
    seat_number = models.CharField(max_length=20, verbose_name='صندلی')
    student_number = models.CharField(max_length=20, verbose_name='شماره دانشجویی')
    national_id = models.CharField(max_length=20, verbose_name='کد ملی')
    student_name = models.CharField(max_length=100, verbose_name='نام و نام خانوادگی')
    entry_year = models.CharField(max_length=10, verbose_name='نیمسال ورودی')
    student_image = models.ImageField(upload_to=student_image_upload_path, blank=True, null=True,
                                      verbose_name='عکس دانسجو')

    class Meta:
        verbose_name = "دانشجو"
        verbose_name_plural = "دانشجویان"

    def __str__(self):
        return f"{self.student_name} - {self.student_number}"


class Enrollment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, verbose_name='دانشجو')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, verbose_name='درس')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'course')

    def __str__(self):
        return f"{self.student.student_name} در درس {self.course.course_name}"


class Signature(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, verbose_name='درس')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, verbose_name='دانشجو')
    signature_base64 = models.TextField(verbose_name='امضا (base64)')
    signed_at = models.DateTimeField(auto_now=True, verbose_name='تاریخ و ساعت امضا')

    class Meta:
        unique_together = ('course', 'student')
        verbose_name = "امضا"
        verbose_name_plural = "امضا"

    def __str__(self):
        return f"امضای {self.student.student_name} در درس {self.course.course_name}"
