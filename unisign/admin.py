from django.contrib import admin
from django.shortcuts import render, redirect
from django.urls import path
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.contrib.auth.models import User, Permission
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.contrib.contenttypes.models import ContentType
from .models import Course, Student, StudentCourse, Teacher, Term, StudentSignature
from .forms import ExcelUploadForm, CourseAdminForm
import pandas as pd
from collections import defaultdict
from django.utils import timezone
from datetime import datetime
import jdatetime
from django.utils.html import format_html
from django.urls import reverse
from django.http import HttpResponseRedirect, JsonResponse, HttpResponse
from django import forms
from .utils import extract_students_from_pdf
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import xlsxwriter
from io import BytesIO

# Customize admin site
admin.site.site_header = 'بخش مدیریت'
admin.site.site_title = 'سامانه حضور و غیاب'
admin.site.index_title = 'مدیریت سامانه'

class JalaliDateMixin:
    def format_jalali_date(self, date):
        if not date:
            return ''
        if isinstance(date, str):
            try:
                date = datetime.strptime(date, '%Y-%m-%d')
            except ValueError:
                return date
        try:
            if timezone.is_aware(date):
                date = timezone.localtime(date)
            return jdatetime.date.fromgregorian(date=date).strftime('%Y/%m/%d')
        except (AttributeError, TypeError):
            return str(date)

    def format_jalali_datetime(self, datetime_obj):
        if not datetime_obj:
            return ''
        if isinstance(datetime_obj, str):
            try:
                datetime_obj = datetime.strptime(datetime_obj, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                return datetime_obj
        try:
            if timezone.is_aware(datetime_obj):
                datetime_obj = timezone.localtime(datetime_obj)
            return jdatetime.datetime.fromgregorian(datetime=datetime_obj).strftime('%Y/%m/%d %H:%M:%S')
        except (AttributeError, TypeError):
            return str(datetime_obj)

def is_teacher(user):
    return hasattr(user, 'teacher')

def is_admin(user):
    return user.is_superuser

def add_teacher_permissions(user):
    """Add necessary permissions for teacher users"""
    # Set is_staff to True
    user.is_staff = True
    user.save()
    
    # Get content types for models
    course_ct = ContentType.objects.get_for_model(Course)
    student_ct = ContentType.objects.get_for_model(Student)
    teacher_ct = ContentType.objects.get_for_model(Teacher)
    studentcourse_ct = ContentType.objects.get_for_model(StudentCourse)
    
    # Add view and change permissions for each model
    for model_ct in [course_ct, student_ct, teacher_ct, studentcourse_ct]:
        for codename in ['view', 'change']:
            try:
                perm = Permission.objects.get(
                    content_type=model_ct,
                    codename=f'{codename}_{model_ct.model}'
                )
                user.user_permissions.add(perm)
            except Permission.DoesNotExist:
                pass

def parse_exam_datetime(date_str, time_str):
    if not date_str:
        return None
    
    try:
        # Check if date and time are combined with dash
        if '-' in date_str:
            date_part, time_part = date_str.split('-')
        else:
            date_part = date_str
            time_part = time_str if time_str else '00:00'
        
        # Parse Jalali date (format: YYYY/MM/DD)
        date_parts = date_part.split('/')
        if len(date_parts) != 3:
            return None
        
        # Parse time (format: HH:MM)
        time_parts = time_part.split(':')
        if len(time_parts) != 2:
            return None
            
        # Convert Jalali to Gregorian
        jalali_year = int(date_parts[0])
        jalali_month = int(date_parts[1])
        jalali_day = int(date_parts[2])
        hour = int(time_parts[0])
        minute = int(time_parts[1])
        
        # Create Jalali date and convert to Gregorian
        jalali_date = jdatetime.date(jalali_year, jalali_month, jalali_day)
        gregorian_date = jalali_date.togregorian()
        
        # Create datetime object with timezone
        dt = datetime(
            gregorian_date.year,
            gregorian_date.month,
            gregorian_date.day,
            hour,
            minute
        )
        return timezone.make_aware(dt)
    except (ValueError, IndexError):
        return None

class PDFUploadForm(forms.Form):
    pdf_file = forms.FileField(label='فایل PDF')

class StudentCourseInline(admin.TabularInline):
    model = StudentCourse
    extra = 0
    readonly_fields = ('student', 'created_at_jalali', 'student_photo')
    fields = ('student_photo', 'student', 'created_at_jalali')
    ordering = ('student__last_name', 'student__first_name')
    can_delete = False

    def student_photo(self, obj):
        if obj.student.national_id:
            photo_path = f'students/{obj.student.national_id}.jpg'
            if default_storage.exists(photo_path):
                return format_html('<img src="/media/{}" width="50" height="50" style="border-radius: 50%;" />', photo_path)
        return "—"
    student_photo.short_description = 'عکس'

    def student(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name} - {obj.student.student_number}"
    student.short_description = 'دانشجو'

    def created_at_jalali(self, obj):
        if obj.created_at:
            return jdatetime.datetime.fromgregorian(datetime=obj.created_at).strftime('%Y/%m/%d %H:%M:%S')
        return "—"
    created_at_jalali.short_description = 'تاریخ ثبت'

@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'national_id')
    search_fields = ('first_name', 'last_name', 'national_id')
    list_filter = ('user__is_active',)

    def has_module_permission(self, request):
        # فقط ادمین می‌تواند به لیست اساتید دسترسی داشته باشد
        return request.user.is_superuser

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('change-password/', self.change_password_view, name='teacher-change-password'),
        ]
        return custom_urls + urls

    @method_decorator(login_required)
    @method_decorator(user_passes_test(is_teacher))
    def change_password_view(self, request):
        if request.method == 'POST':
            form = PasswordChangeForm(request.user, request.POST)
            if form.is_valid():
                user = form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'رمز عبور با موفقیت تغییر کرد.')
                return redirect('admin:index')
            else:
                messages.error(request, 'لطفاً خطاهای زیر را اصلاح کنید.')
        else:
            form = PasswordChangeForm(request.user)
        return render(request, 'admin/teacher_change_password.html', {'form': form})

@admin.register(Course)
class CourseAdmin(JalaliDateMixin, admin.ModelAdmin):
    form = CourseAdminForm
    list_display = ('course_code', 'course_name', 'group_code', 'teacher', 'exam_date_jalali', 'exam_location', 'term')
    search_fields = ('course_code', 'course_name', 'group_code', 'teacher__first_name', 'teacher__last_name')
    list_filter = ('term', 'teacher')
    readonly_fields = ('exam_date_jalali', 'get_students_with_signatures')

    def get_readonly_fields(self, request, obj=None):
        if obj:  # editing an existing object
            return self.readonly_fields + ('course_code', 'course_name', 'group_code', 'teacher')
        return self.readonly_fields

    def get_fieldsets(self, request, obj=None):
        if obj:  # editing an existing object
            return [
                ('اطلاعات درس', {
                    'fields': ('course_code', 'course_name', 'group_code', 'teacher', 'term')
                }),
                ('اطلاعات امتحان', {
                    'fields': ('exam_date', 'exam_date_jalali', 'exam_location')
                }),
                ('اطلاعات ظرفیت', {
                    'fields': ('max_capacity', 'student_count', 'empty_capacity', 'class_time')
                }),
                ('لیست دانشجویان', {
                    'fields': ('get_students_with_signatures',)
                })
            ]
        return [
            ('اطلاعات درس', {
                'fields': ('course_code', 'course_name', 'group_code', 'teacher', 'term')
            }),
            ('اطلاعات امتحان', {
                'fields': ('exam_date', 'exam_location')
            }),
            ('اطلاعات ظرفیت', {
                'fields': ('max_capacity', 'student_count', 'empty_capacity', 'class_time')
            })
        ]

    def get_students_with_signatures(self, obj):
        if not obj:
            return "—"
        
        # Get all students in this course
        student_courses = StudentCourse.objects.filter(course=obj).select_related('student')
        
        # Prepare HTML content
        html = '<div style="margin-top: 10px;">'
        # Add export button
        html += f'<a href="/admin/unisign/course/{obj.id}/export-excel/" class="button" style="margin-bottom: 10px; display: inline-block; padding: 10px 20px; background-color: #417690; color: white; text-decoration: none; border-radius: 4px;">دانلود لیست به صورت Excel</a>'
        html += '<table style="width: 100%; border-collapse: collapse;">'
        html += '<tr style="background-color: #f5f5f5;">'
        html += '<th style="padding: 8px; border: 1px solid #ddd;">شماره دانشجویی</th>'
        html += '<th style="padding: 8px; border: 1px solid #ddd;">نام و نام خانوادگی</th>'
        html += '<th style="padding: 8px; border: 1px solid #ddd;">وضعیت امضا</th>'
        html += '<th style="padding: 8px; border: 1px solid #ddd;">تصویر امضا</th>'
        html += '<th style="padding: 8px; border: 1px solid #ddd;">تاریخ امضا</th>'
        html += '<th style="padding: 8px; border: 1px solid #ddd;">امضا کننده</th>'
        html += '</tr>'
        
        for sc in student_courses:
            student = sc.student
            signature = StudentSignature.objects.filter(student=student, course=obj).first()
            
            html += '<tr>'
            html += f'<td style="padding: 8px; border: 1px solid #ddd;">{student.student_number}</td>'
            html += f'<td style="padding: 8px; border: 1px solid #ddd;">{student.first_name} {student.last_name}</td>'
            
            if signature:
                html += '<td style="padding: 8px; border: 1px solid #ddd; color: green;">✓ امضا شده</td>'
                # Add signature image with thumbnail
                if signature.signature_image:
                    html += f'<td style="padding: 8px; border: 1px solid #ddd;">'
                    html += f'<a href="{signature.signature_image.url}" target="_blank">'
                    html += f'<img src="{signature.signature_image.url}" style="max-width: 100px; max-height: 50px; cursor: pointer;" />'
                    html += '</a></td>'
                else:
                    html += '<td style="padding: 8px; border: 1px solid #ddd;">—</td>'
                html += f'<td style="padding: 8px; border: 1px solid #ddd;">{signature.created_at_jalali()}</td>'
                
                # Show username if first_name and last_name are not available
                signed_by_name = f"{signature.signed_by.first_name} {signature.signed_by.last_name}".strip()
                if not signed_by_name:
                    signed_by_name = signature.signed_by.username
                html += f'<td style="padding: 8px; border: 1px solid #ddd;">{signed_by_name}</td>'
            else:
                html += '<td style="padding: 8px; border: 1px solid #ddd; color: red;">✗ امضا نشده</td>'
                html += '<td style="padding: 8px; border: 1px solid #ddd;">—</td>'
                html += '<td style="padding: 8px; border: 1px solid #ddd;">—</td>'
                html += '<td style="padding: 8px; border: 1px solid #ddd;">—</td>'
            
            html += '</tr>'
        
        html += '</table>'
        html += '</div>'
        
        return format_html(html)
    get_students_with_signatures.short_description = 'لیست دانشجویان'

    def formfield_for_dbfield(self, db_field, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, **kwargs)
        if db_field.name == 'get_students_with_signatures':
            formfield.label = 'لیست دانشجویان'
        return formfield

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        
        # فیلتر بر اساس کاربر (استاد یا ادمین)
        if is_teacher(request.user):
            qs = qs.filter(teacher=request.user.teacher)
        
        # اگر فیلتر ترم اعمال نشده بود، بر اساس آخرین ترم فیلتر کن
        # Django admin filter for ForeignKey uses param name 'field_name__id__exact'
        if 'term__id__exact' not in request.GET:
            latest_term = Term.objects.latest('created_at')
            if latest_term:
                qs = qs.filter(term=latest_term)
                
        return qs

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('upload-excel/', self.admin_site.admin_view(self.upload_excel_view), name='upload-excel'),
            path('upload-pdf/', self.admin_site.admin_view(self.upload_pdf_view), name='upload_course_pdf'),
            path(
                '<int:course_id>/export-excel/',
                self.admin_site.admin_view(self.export_excel),
                name='course-export-excel',
            ),
        ]
        return custom_urls + urls

    def upload_excel_view(self, request):
        if not request.user.is_authenticated:
            return redirect('admin:login')
        if not (is_admin(request.user) or is_teacher(request.user)):
            messages.error(request, 'شما دسترسی به این صفحه را ندارید.')
            return redirect('admin:index')
        return self.upload_excel(request)

    def upload_excel(self, request):
        if request.method == 'POST':
            form = ExcelUploadForm(request.POST, request.FILES)
            if form.is_valid():
                excel_file = request.FILES['file']
                term_name = form.cleaned_data['term']
                
                # Get or create term
                term, created = Term.objects.get_or_create(name=term_name)
                if created:
                    messages.success(request, f'ترم جدید "{term_name}" ایجاد شد.')
                
                try:
                    # خواندن فایل اکسل با حفظ فرمت اعداد
                    df = pd.read_excel(excel_file, dtype={
                        'کدملی': str,
                        'شماره‌دانشجویی': str,
                        'کدملی‌مدرس': str,
                        'کددرس': str,
                        'کد‌گروه‌درسی': str,
                        'ترم‌ورود': str,
                        'کدرشته': str,
                        'شناسه‌دانشکده': str
                    })
                    
                    # تبدیل ستون‌های عددی به رشته برای حفظ صفرهای ابتدایی
                    string_columns = ['کددرس', 'کد‌گروه‌درسی', 'کدملی‌مدرس', 'کدملی', 'شماره‌دانشجویی', 'ترم‌ورود', 'کدرشته', 'شناسه‌دانشکده']
                    for col in string_columns:
                        if col in df.columns:
                            df[col] = df[col].fillna('').astype(str).str.strip()
                    
                    # تبدیل مقادیر عددی به عدد صحیح
                    numeric_columns = ['حداکثر‌ظرفیت', 'تعداددانشجو', 'ظرفیت‌خالی']
                    for col in numeric_columns:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
                    
                    records = df.to_dict('records')
                    
                    with transaction.atomic():
                        # دریافت همه اساتید موجود
                        existing_teachers = {
                            t.national_id: t 
                            for t in Teacher.objects.all()
                        }
                        
                        # دریافت همه درس‌های موجود
                        existing_courses = {
                            (c.course_code, c.group_code, c.term_id): c # اضافه کردن term_id به کلید
                            for c in Course.objects.select_related('term').all() # واکشی ترم
                        }
                        
                        # دریافت همه دانشجویان موجود
                        existing_students = {
                            s.national_id: s 
                            for s in Student.objects.all()
                        }
                        
                        # دریافت همه ارتباطات موجود
                        existing_relationships = {
                            (sc.student.national_id, sc.course.course_code, sc.course.group_code, sc.term_id): sc # اضافه کردن term_id به کلید
                            for sc in StudentCourse.objects.select_related('student', 'course__term').all() # واکشی ترم درس و ترم انتخاب واحد
                        }
                        
                        # جمع‌آوری اساتید یکتا
                        unique_teachers = {}
                        for record in records:
                            teacher_national_id = str(record.get('کدملی‌مدرس', '')).strip()
                            if teacher_national_id and teacher_national_id not in existing_teachers:
                                teacher_name = str(record.get('نام‌مدرس', ''))
                                if teacher_name:
                                    first_name = teacher_name.split()[0]
                                    last_name = ' '.join(teacher_name.split()[1:])
                                else:
                                    first_name = ''
                                    last_name = ''
                                unique_teachers[teacher_national_id] = {
                                    'national_id': teacher_national_id,
                                    'first_name': first_name,
                                    'last_name': last_name
                                }
                        
                        # ایجاد اساتید جدید
                        for teacher_data in unique_teachers.values():
                            # چک کردن وجود کاربر
                            user = User.objects.filter(username=teacher_data['national_id']).first()
                            if not user:
                                try:
                                    user = User.objects.create_user(
                                        username=teacher_data['national_id'],
                                        password=teacher_data['national_id'],  # رمز عبور موقت
                                        first_name=teacher_data['first_name'],
                                        last_name=teacher_data['last_name']
                                    )
                                    # Add teacher permissions
                                    add_teacher_permissions(user)
                                except Exception as e:
                                    return JsonResponse({
                                        'success': False,
                                        'message': f'خطا در ایجاد کاربر با کد ملی {teacher_data["national_id"]}: {str(e)}'
                                    })
                            
                            teacher = Teacher(
                                user=user,
                                national_id=teacher_data['national_id'],
                                first_name=teacher_data['first_name'],
                                last_name=teacher_data['last_name']
                            )
                            teacher.save()
                            existing_teachers[teacher_data['national_id']] = teacher
                        
                        # حالا درس‌ها را ذخیره می‌کنیم
                        for record in records:
                            course_key = (str(record.get('کددرس', '')), str(record.get('کد‌گروه‌درسی', '')), term.id) # استفاده از ترم
                            teacher_national_id = str(record.get('کدملی‌مدرس', '')).strip()
                            
                            # اگر درس وجود نداشت و استاد وجود داشت، آن را ایجاد کن
                            if course_key not in existing_courses and teacher_national_id in existing_teachers:
                                # پردازش تاریخ امتحان
                                exam_date_str = str(record.get('تاریخ‌امتحان', ''))
                                exam_time_str = str(record.get('زمان‌آزمون', ''))
                                exam_date = parse_exam_datetime(exam_date_str, exam_time_str)
                                
                                # پردازش تاریخ ثبت
                                registration_date_str = str(record.get('تاریخ‌ثبت', ''))
                                registration_time_str = '00:00'  # زمان پیش‌فرض برای تاریخ ثبت
                                registration_date = parse_exam_datetime(registration_date_str, registration_time_str)
                                
                                course = Course(
                                    course_code=str(record.get('کددرس', '')),
                                    course_name=str(record.get('درس', '')),
                                    group_code=str(record.get('کد‌گروه‌درسی', '')),
                                    teacher=existing_teachers[teacher_national_id],
                                    max_capacity=record.get('حداکثر‌ظرفیت', 0) or 0,
                                    student_count=record.get('تعداددانشجو', 0) or 0,
                                    empty_capacity=record.get('ظرفیت‌خالی', 0) or 0,
                                    class_time=str(record.get('زمان‌تشکیل‌کلاس', '')),
                                    faculty_id=str(record.get('شناسه‌دانشکده', '')),
                                    group_type=str(record.get('نوع‌گروه‌درسی', '')),
                                    exam_location=str(record.get('محل‌آزمون', '')),
                                    exam_date=exam_date,
                                    group_id=str(record.get('شناسه‌گروه‌درسی', '')),
                                    registration_date=registration_date,
                                    term=term # مرتبط کردن درس با ترم
                                )
                                course.save()
                                existing_courses[course_key] = course
                            
                        # حالا دانشجویان و ارتباطات را ایجاد می‌کنیم
                        for record in records:
                            course_code = str(record.get('کددرس', ''))
                            group_code = str(record.get('کد‌گروه‌درسی', ''))
                            course_key = (course_code, group_code, term.id) # استفاده از ترم
                            national_id = str(record.get('کدملی', '')).strip()
                            
                            # پیدا کردن درس مرتبط با این ترم
                            course = existing_courses.get(course_key)
                            
                            # اگر دانشجو وجود نداشت، آن را ایجاد کن
                            if national_id not in existing_students:
                                student = Student(
                                    first_name=str(record.get('نام', '')),
                                    last_name=str(record.get('نام‌خانوادگی', '')),
                                    national_id=national_id,
                                    student_number=str(record.get('شماره‌دانشجویی', '')),
                                    entry_term=str(record.get('ترم‌ورود', '')),
                                    gender=str(record.get('جنسیت', '')),
                                    major_code=str(record.get('کدرشته', '')),
                                    major_name=str(record.get('رشته', ''))
                                )
                                student.save()
                                existing_students[national_id] = student
                            
                            # اگر درس مرتبط با این ترم و دانشجو وجود داشت و ارتباط هنوز ثبت نشده بود، آن را ایجاد کن
                            student_obj = existing_students.get(national_id)
                            relationship_key = (national_id, course_code, group_code, term.id) # استفاده از ترم
                            
                            if (student_obj and course and 
                                relationship_key not in existing_relationships):
                                StudentCourse.objects.create(
                                    student=student_obj,
                                    course=course,
                                    term=term # مرتبط کردن انتخاب واحد با ترم
                                )
                                existing_relationships[relationship_key] = True # ثبت ارتباط در دیکشنری

                    return JsonResponse({
                        'success': True,
                        'message': 'اطلاعات با موفقیت استخراج و ذخیره شد.',
                        'redirect_url': reverse('admin:unisign_course_changelist')
                    })
                except Exception as e:
                    return JsonResponse({
                        'success': False,
                        'message': f'خطا در پردازش فایل: {str(e)}'
                    })
            else:
                # اگر فرم نامعتبر بود، پیام خطا را در پاسخ برگردان
                errors = form.errors.as_json()
                return JsonResponse({
                    'success': False,
                    'message': 'لطفاً اطلاعات فرم را بررسی کنید.',
                    'errors': errors
                })
        else:
            form = ExcelUploadForm()
        return render(request, 'admin/excel_upload.html', {'form': form})

    def upload_pdf_button(self, obj):
        return format_html(
            '<a class="button" href="#" onclick="showPdfUploadModal(); return false;">آپلود PDF</a>'
        )
    upload_pdf_button.short_description = 'آپلود PDF'
    upload_pdf_button.allow_tags = True

    def upload_pdf_view(self, request):
        if request.method == 'POST':
            form = PDFUploadForm(request.POST, request.FILES)
            if form.is_valid():
                pdf_file = request.FILES['pdf_file']
                
                try:
                    # Process PDF directly from the uploaded file
                    students_data = extract_students_from_pdf(pdf_file)

                    # Update database
                    processed_count = 0
                    for student_data in students_data:
                        try:
                            # Try to find student by national ID or student number
                            student = Student.objects.filter(
                                national_id=student_data['national_id']
                            ).first() or Student.objects.filter(
                                student_number=student_data['student_number']
                            ).first()

                            if student:
                                # Save student photo if available
                                if 'student_image' in student_data and student_data['student_image']:
                                    # فقط مسیر عکس را در دیتابیس ذخیره کن
                                    student.photo = student_data['student_image']
                                student.save()
                                processed_count += 1
                        except Exception as e:
                            return JsonResponse({
                                'success': False,
                                'message': f'خطا در پردازش دانشجو {student_data.get("national_id", "نامشخص")}: {str(e)}'
                            })

                    return JsonResponse({
                        'success': True,
                        'message': f'{processed_count} دانشجو با موفقیت پردازش شدند.',
                        'redirect_url': reverse('admin:unisign_course_changelist')
                    })
                except Exception as e:
                    return JsonResponse({
                        'success': False,
                        'message': f'خطا در پردازش فایل PDF: {str(e)}'
                    })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'لطفاً یک فایل PDF معتبر انتخاب کنید.'
                })
        else:
            form = PDFUploadForm()

        context = {
            'form': form,
            'title': 'آپلود PDF',
            'opts': self.model._meta,
        }
        return render(request, 'admin/excel_processor/course/upload_pdf.html', context)

    def export_excel(self, request, course_id):
        course = Course.objects.get(id=course_id)
        student_courses = StudentCourse.objects.filter(course=course).select_related('student')
        
        # Create a new Excel file
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()

        # Add course information in header
        header_format = workbook.add_format({
            'bold': True,
            'font_size': 12,
            'align': 'center',
            'valign': 'vcenter'
        })
        
        # Write course information
        worksheet.merge_range('A1:G1', f'اطلاعات درس: {course.course_name} ({course.course_code})', header_format)
        worksheet.merge_range('A2:G2', f'گروه: {course.group_code} | استاد: {course.teacher.first_name} {course.teacher.last_name}', header_format)
        worksheet.merge_range('A3:G3', f'تاریخ امتحان: {course.exam_date_jalali()} | محل امتحان: {course.exam_location}', header_format)
        
        # Add empty row after header
        worksheet.write('A4', '')

        # Set column widths
        worksheet.set_column('A:A', 15)  # شماره دانشجویی
        worksheet.set_column('B:B', 20)  # نام
        worksheet.set_column('C:C', 20)  # نام خانوادگی
        worksheet.set_column('D:D', 15)  # وضعیت امضا
        worksheet.set_column('E:E', 15)  # تصویر امضا
        worksheet.set_column('F:F', 20)  # تاریخ امضا
        worksheet.set_column('G:G', 20)  # امضا کننده

        # Add headers
        headers = ['شماره دانشجویی', 'نام', 'نام خانوادگی', 'وضعیت امضا', 'تصویر امضا', 'تاریخ امضا', 'امضا کننده']
        for col, header in enumerate(headers):
            worksheet.write(4, col, header)

        # Add data
        row = 5
        for sc in student_courses:
            student = sc.student
            signature = StudentSignature.objects.filter(student=student, course=course).first()
            
            worksheet.write(row, 0, student.student_number)
            worksheet.write(row, 1, student.first_name)
            worksheet.write(row, 2, student.last_name)
            
            if signature:
                worksheet.write(row, 3, 'امضا شده')
                
                # Add signature image if exists
                if signature.signature_image:
                    try:
                        # Get the image path
                        image_path = signature.signature_image.path
                        # Insert the image with specific size
                        worksheet.insert_image(row, 4, image_path, {
                            'x_scale': 0.05,  # کاهش مقیاس به 0.05
                            'y_scale': 0.05,  # کاهش مقیاس به 0.05
                            'positioning': 1,  # Move and size with cells
                            'x_offset': 5,
                            'y_offset': 5,
                            'object_position': 1,  # تنظیم موقعیت تصویر در سلول
                            'x_size': 10,  # عرض تصویر
                            'y_size': 10   # ارتفاع تصویر
                        })
                    except Exception as e:
                        worksheet.write(row, 4, 'خطا در بارگذاری تصویر')
                else:
                    worksheet.write(row, 4, '—')
                
                worksheet.write(row, 5, signature.created_at_jalali())
                signed_by_name = f"{signature.signed_by.first_name} {signature.signed_by.last_name}".strip()
                if not signed_by_name:
                    signed_by_name = signature.signed_by.username
                worksheet.write(row, 6, signed_by_name)
            else:
                worksheet.write(row, 3, 'امضا نشده')
                worksheet.write(row, 4, '—')
                worksheet.write(row, 5, '—')
                worksheet.write(row, 6, '—')
            
            # تنظیم ارتفاع سطر برای تصویر
            worksheet.set_row(row, 15)  # کاهش ارتفاع سطر به 15
            row += 1

        workbook.close()
        output.seek(0)

        # Create the HttpResponse
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=course_{course.course_code}_{course.group_code}_students.xlsx'
        return response

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('student_photo', 'first_name', 'last_name', 'student_number', 'national_id')
    search_fields = ('first_name', 'last_name', 'student_number', 'national_id')
    list_filter = ('gender', 'major_name')
    ordering = ('last_name', 'first_name')
    readonly_fields = ('student_photo_large',)

    fieldsets = (
        ('اطلاعات شخصی', {
            'fields': ('student_photo_large', 'first_name', 'last_name', 'student_number', 'national_id', 'entry_term', 'gender')
        }),
        ('اطلاعات تحصیلی', {
            'fields': ('major_code', 'major_name')
        }),
    )

    def student_photo(self, obj):
        if obj.photo:
            return format_html('<img src="{}" width="50" height="50" style="border-radius: 50%;" />', obj.photo.url)
        elif obj.national_id:
            photo_path = f'students/{obj.national_id}.jpg'
            if default_storage.exists(photo_path):
                return format_html('<img src="/media/{}" width="50" height="50" style="border-radius: 50%;" />', photo_path)
        return "—"
    student_photo.short_description = 'عکس'

    def student_photo_large(self, obj):
        if obj.photo:
            return format_html('<img src="{}" width="200" height="200" style="border-radius: 50%;" />', obj.photo.url)
        elif obj.national_id:
            photo_path = f'students/{obj.national_id}.jpg'
            if default_storage.exists(photo_path):
                return format_html('<img src="/media/{}" width="200" height="200" style="border-radius: 50%;" />', photo_path)
        return "—"
    student_photo_large.short_description = 'عکس'

@admin.register(StudentCourse)
class StudentCourseAdmin(JalaliDateMixin, admin.ModelAdmin):
    list_display = ('student', 'course', 'created_at_jalali')
    search_fields = ('student__first_name', 'student__last_name', 'student__national_id', 'course__course_name')
    list_filter = ('course__group_type', 'course__faculty_id', 'term')
    readonly_fields = ('created_at_jalali',)

    def created_at_jalali(self, obj):
        return self.format_jalali_datetime(obj.created_at)
    created_at_jalali.short_description = 'تاریخ ثبت'
    created_at_jalali.admin_order_field = 'created_at'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        
        # فیلتر بر اساس کاربر (استاد می‌تواند فقط انتخاب واحد دروس خودش را ببیند)
        if is_teacher(request.user):
            qs = qs.filter(course__teacher=request.user.teacher)
        
        # اگر فیلتر ترم اعمال نشده بود، بر اساس آخرین ترم فیلتر کن
        if 'term__id__exact' not in request.GET:
            latest_term = Term.objects.latest('created_at')
            if latest_term:
                qs = qs.filter(term=latest_term)
                
        return qs
