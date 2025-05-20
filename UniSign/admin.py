from django.contrib import admin
from django.db import models
from django_jalali.db import models as jmodels
from django.utils.safestring import mark_safe
from jalali_date.admin import ModelAdminJalaliMixin
from jalali_date import datetime2jalali
from .models import Course, Student, Enrollment, Signature
from .forms import CourseAdminForm
from .utils import extract_students_from_pdf
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from django.contrib.admin.sites import site

if site.is_registered(BlacklistedToken):
    admin.site.unregister(BlacklistedToken)

if site.is_registered(OutstandingToken):
    admin.site.unregister(OutstandingToken)

PER_PAGE = 25

admin.site.site_header = _("پنل مدیریت سامانه حضور و غیاب")
admin.site.index_title = _("خوش آمدید به بخش مدیریت")


# ----------------------------
# نمایش عکس دانشجوها در صفحه دانشجو
# ----------------------------
@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('student_name', 'student_number', 'national_id', 'courses_display', 'student_image_display')
    list_per_page = PER_PAGE
    search_fields = ('student_name', 'student_number', 'national_id')

    # استفاده از دکوراتور به جای استاتیک متد
    @admin.display(description='درس')
    def courses_display(self, obj):
        return ", ".join([e.course.course_name for e in obj.enrollment_set.all()])

    @admin.display(description='تصویر دانشجو')
    def student_image_display(self, obj):
        if obj.student_image:
            return mark_safe(f'<img src="{obj.student_image.url}" width="50" height="50" />')
        return "بدون تصویر"


# ----------------------------
# نمایش دانشجوها در صفحه درس
# ----------------------------
class EnrollmentInline(admin.TabularInline):
    model = Enrollment
    extra = 0
    readonly_fields = ['student', 'student_image_display', 'student_name', 'student_number', 'national_id', 'signature_display', 'signature_date']
    fields = ['student', 'student_image_display', 'student_name', 'student_number', 'national_id', 'signature_display', 'signature_date']
    verbose_name = "دانشجو"
    verbose_name_plural = "دانشجویان این درس"

    def student_name(self, obj):
        return obj.student.name

    student_name.short_description = "نام و نام خانوادگی"

    def student_number(self, obj):
        return obj.student.student_number

    student_number.short_description = "کد دانشجویی"

    def national_id(self, obj):
        return obj.student.national_id

    national_id.short_description = "کد ملی"

    @admin.display(description='تصویر دانشجو')
    def student_image_display(self, obj):
        if obj.student.student_image:
            return mark_safe(
                f'<img src="{obj.student.student_image.url}" width="50" height="50" />')
        return "بدون تصویر"

    @admin.display(description='امضا')
    def signature_display(self, obj):
        signature = Signature.objects.filter(course=obj.course, student=obj.student).first()
        if signature and signature.signature_base64:
            return mark_safe(f'<img src="data:image/png;base64,{signature.signature_base64}" width="100" height="50" />')
        return "بدون امضا"

    @admin.display(description='تاریخ امضا')
    def signature_date(self, obj):
        signature = Signature.objects.filter(course=obj.course, student=obj.student).first()
        if signature:
            return datetime2jalali(signature.signed_at).strftime('%Y/%m/%d - %H:%M:%S')
        return "—"


# ----------------------------
# صفحه درس
# ----------------------------
@admin.register(Course)
class CourseAdmin(ModelAdminJalaliMixin, admin.ModelAdmin):
    form = CourseAdminForm
    list_display = [
        'course_name',
        'term_info',
        'professor',
        'group_info',
        'pdf_file_link',
        'get_exam_time_jalali'
    ]
    list_per_page = PER_PAGE  # تعداد آیتم در هر صفحه
    search_fields = [  # فیلدهای قابل جستجو
        'course_name',
        'term_info',
        'professor',
        'group_info'
    ]
    inlines = [EnrollmentInline]

    def pdf_file_link(self, obj):
        if obj.pdf_file:
            return mark_safe(f'<a href="{obj.pdf_file.url}" target="_blank">مشاهده فایل PDF</a>')
        return "—"

    pdf_file_link.short_description = 'فایل پی‌دی‌اف'

    def get_exam_time_jalali(self, obj):
        if obj.exam_time:
            return datetime2jalali(obj.exam_time).strftime('%Y/%m/%d %H:%M:%S')
        return "—"

    get_exam_time_jalali.short_description = 'تاریخ و زمان آزمون'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.pdf_file:
            try:
                Enrollment.objects.filter(course=obj).delete()
                Student.objects.filter(enrollment__course=obj).delete()

                students_data = extract_students_from_pdf(obj)

                if students_data:
                    for data in students_data:
                        student = Student.objects.create(
                            student_name=data["student_name"],
                            student_number=data["student_number"],
                            national_id=data["national_id"],
                            seat_number=data["seat_number"],
                            exam_place=data["exam_place"],
                            row=data["row"],
                            entry_year=data["entry_year"],
                            student_image=data["student_image"]
                        )
                        Enrollment.objects.create(student=student, course=obj)

                    self.message_user(request, f"{len(students_data)} دانشجو با موفقیت ذخیره شدند.")
                else:  # این بخش اضافه شده
                    self.message_user(request, "هیچ داده دانشجویی در فایل PDF یافت نشد.", level='warning')

            except Exception as e:
                self.message_user(request, f"خطا در پردازش PDF: {str(e)}", level='error')


# ----------------------------
# صفحه امضای دیجیتال
# ----------------------------
@admin.register(Signature)
class SignatureAdmin(admin.ModelAdmin):
    list_display = ['student', 'course', 'signature_image', 'signed_at_jalali']
    list_filter = ['course', 'signed_at']
    search_fields = ['student__student_name', 'course__course_name', 'course__group_info']
    readonly_fields = ['student_image_display', 'signature_image', 'signed_at_jalali']
    fields = ['student', 'course', 'student_image_display', 'signature_image', 'signed_at_jalali']

    def signature_image(self, obj):
        if obj.signature_base64:
            return mark_safe(f'<img src="data:image/png;base64,{obj.signature_base64}" width="200" height="100" />')
        return "بدون امضا"
    signature_image.short_description = 'امضا'

    def student_image_display(self, obj):
        if obj.student and obj.student.student_image:
            return mark_safe(f'<img src="{obj.student.student_image.url}" width="100" height="100" />')
        return "بدون تصویر"
    student_image_display.short_description = 'عکس دانشجو'

    def signed_at_jalali(self, obj):
        return datetime2jalali(obj.signed_at).strftime('%Y/%m/%d - %H:%M:%S')
    signed_at_jalali.short_description = 'تاریخ امضا'
