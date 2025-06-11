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
import io

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
    change_list_template = 'admin/course_change_list.html'

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
        html = '<div class="student-list">'
        for sc in student_courses:
            student = sc.student
            signature = StudentSignature.objects.filter(student=student, course=obj).first()
            
            html += f'<div class="student-item">'
            # Add student photo if exists
            if student.national_id:
                photo_path = f'students/{student.national_id}.jpg'
                if default_storage.exists(photo_path):
                    html += f'<img src="/media/{photo_path}" width="50" height="50" style="border-radius: 50%;" />'
            
            # Add student info
            html += f'<div class="student-info">'
            html += f'<strong>{student.first_name} {student.last_name}</strong><br>'
            html += f'شماره دانشجویی: {student.student_number}<br>'
            html += f'کد ملی: {student.national_id}'
            
            # Add signature if exists
            if signature and signature.signature_image:
                html += f'<br>امضا: <img src="{signature.signature_image.url}" width="100" />'
            
            html += '</div></div>'
        
        html += '</div>'
        return format_html(html)

    def formfield_for_dbfield(self, db_field, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, **kwargs)
        if db_field.name == "exam_date":
            formfield.widget = forms.DateTimeInput(attrs={'type': 'datetime-local'})
        return formfield

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        
        # فیلتر بر اساس کاربر (استاد یا ادمین)
        if is_teacher(request.user):
            qs = qs.filter(teacher=request.user.teacher)
        
        # اگر فیلتر ترم اعمال نشده بود و ترمی وجود داشت، بر اساس آخرین ترم فیلتر کن
        if 'term__id__exact' not in request.GET and Term.objects.exists():
            latest_term = Term.objects.latest('created_at')
            if latest_term:
                qs = qs.filter(term=latest_term)
                
        return qs

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('upload-excel/', self.upload_excel_view, name='course-upload-excel'),
            path('upload-pdf/', self.upload_pdf_view, name='course-upload-pdf'),
            path('download-excel-template/', self.download_excel_template, name='download-excel-template'),
            path('export-excel/<int:course_id>/', self.export_excel, name='export-excel'),
        ]
        return custom_urls + urls

    def upload_excel_button(self, obj):
        if not obj:
            return "—"
        return format_html(
            '<a class="button" href="{}">آپلود Excel</a>',
            reverse('admin:course-upload-excel')
        )
    upload_excel_button.short_description = 'آپلود Excel'

    def upload_pdf_button(self, obj):
        if not obj:
            return "—"
        return format_html(
            '<a class="button" href="{}">آپلود PDF</a>',
            reverse('admin:course-upload-pdf')
        )
    upload_pdf_button.short_description = 'آپلود PDF'

    def upload_excel_view(self, request):
        if request.method == 'POST':
            form = ExcelUploadForm(request.POST, request.FILES)
            if form.is_valid():
                excel_file = request.FILES['excel_file']
                term_name = form.cleaned_data['term']
                
                try:
                    # 1. Create or get term first
                    term, _ = Term.objects.get_or_create(name=term_name)
                    
                    # Read Excel file
                    df = pd.read_excel(excel_file)
                    
                    success_count = 0
                    duplicate_count = 0
                    
                    for _, row in df.iterrows():
                        try:
                            # 2. Create or get teacher
                            teacher_national_id = row['کدملی‌مدرس']
                            teacher_name = row['نام‌مدرس']
                            
                            # First check if teacher exists
                            try:
                                teacher = Teacher.objects.get(national_id=teacher_national_id)
                            except Teacher.DoesNotExist:
                                # Convert national_id to string for username and password
                                teacher_national_id_str = str(teacher_national_id)
                                # Create user first
                                teacher_user = User.objects.create_user(
                                    username=teacher_national_id_str,
                                    password=teacher_national_id_str,
                                    is_active=True,
                                    is_staff=True
                                )
                                
                                # Create teacher with user
                                teacher = Teacher.objects.create(
                                    user=teacher_user,
                                    national_id=teacher_national_id_str,
                                    first_name=teacher_name.split()[0] if pd.notna(teacher_name) else '',
                                    last_name=' '.join(teacher_name.split()[1:]) if pd.notna(teacher_name) else ''
                                )
                            
                            # 3. Create or get course with term and teacher
                            course, _ = Course.objects.get_or_create(
                                course_code=row['کددرس'],
                                term=term,
                                defaults={
                                    'course_name': row['درس'],
                                    'group_code': row.get('کد‌گروه‌درسی', ''),
                                    'teacher': teacher,
                                    'max_capacity': int(row.get('حداکثر‌ظرفیت', 0)) or 0,
                                    'student_count': int(row.get('تعداددانشجو', 0)) or 0,
                                    'empty_capacity': int(row.get('ظرفیت‌خالی', 0)) or 0,
                                    'class_time': row.get('زمان‌تشکیل‌کلاس', ''),
                                    'faculty_id': row.get('شناسه‌دانشکده', ''),
                                    'group_type': row.get('نوع‌گروه‌درسی', ''),
                                    'exam_location': row.get('محل‌آزمون', ''),
                                    'group_id': row.get('شناسه‌گروه‌درسی', '')
                                }
                            )
                            
                            # 4. Create or get student
                            student, student_created = Student.objects.get_or_create(
                                national_id=row['کدملی'],
                                defaults={
                                    'student_number': row['شماره‌دانشجویی'],
                                    'first_name': row['نام'],
                                    'last_name': row['نام‌خانوادگی'],
                                    'entry_term': row.get('ترم‌ورود', ''),
                                    'gender': row.get('جنسیت', ''),
                                    'major_code': row.get('کدرشته', ''),
                                    'major_name': row.get('رشته', '')
                                }
                            )
                            
                            # 5. Create student-course relationship
                            StudentCourse.objects.get_or_create(
                                student=student,
                                course=course,
                                term=term
                            )
                            
                            if student_created:
                                success_count += 1
                            else:
                                duplicate_count += 1
                                
                        except Exception as e:
                            messages.error(request, f'خطا در پردازش ردیف: {str(e)}')
                            continue
                    
                    messages.success(request, f'تعداد {success_count} دانشجو با موفقیت اضافه شد. تعداد {duplicate_count} دانشجوی تکراری یافت شد.')
                    return redirect('admin:unisign_course_changelist')
                    
                except Exception as e:
                    messages.error(request, f'خطا در پردازش فایل: {str(e)}')
        else:
            form = ExcelUploadForm()
        
        return render(request, 'admin/upload_excel.html', {
            'form': form,
            'title': 'آپلود فایل Excel'
        })

    def upload_pdf_view(self, request):
        if request.method == 'POST':
            form = PDFUploadForm(request.POST, request.FILES)
            if form.is_valid():
                pdf_file = request.FILES['pdf_file']
                
                try:
                    # Extract student information from PDF
                    students_data = extract_students_from_pdf(pdf_file)

                    success_count = 0
                    for student_data in students_data:
                        try:
                            # فقط دانشجوی موجود رو پیدا می‌کنیم
                            try:
                                student = Student.objects.get(national_id=student_data['national_id'])
                                
                                # فقط عکس دانشجو رو به‌روز می‌کنیم
                                if student_data['student_image']:
                                    student.photo.name = student_data['student_image']
                                    student.save()
                                    success_count += 1
                                
                            except Student.DoesNotExist:
                                # اگر دانشجو پیدا نشد، فقط پیام خطا نمایش میدیم
                                messages.warning(request, f'دانشجو با کد ملی {student_data["national_id"]} یافت نشد.')
                                continue
                            
                        except Exception as e:
                            messages.error(request, f'خطا در پردازش اطلاعات دانشجو: {str(e)}')
                            continue
                    
                    messages.success(request, f'تعداد {success_count} عکس دانشجو با موفقیت به‌روز شد.')
                    return redirect('admin:unisign_course_changelist')
                    
                except Exception as e:
                    messages.error(request, f'خطا در پردازش فایل: {str(e)}')
        else:
            form = PDFUploadForm()

        return render(request, 'admin/upload_pdf.html', {
            'form': form,
            'title': 'آپلود فایل PDF'
        })

    def download_excel_template(self, request):
        """View for downloading the Excel template"""
        # Create a sample DataFrame with the required columns
        df = pd.DataFrame({
            'کد ملی': ['0123456789'],
            'شماره دانشجویی': ['123456789'],
            'نام': ['نام'],
            'نام خانوادگی': ['نام خانوادگی']
        })

        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='دانشجویان')
            
            # Get the workbook and worksheet objects
            workbook = writer.book
            worksheet = writer.sheets['دانشجویان']
            
            # Add some formatting
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'top',
                'bg_color': '#D9E1F2',
                'border': 1
            })
            
            # Write the column headers with the defined format
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
                worksheet.set_column(col_num, col_num, 15)  # Set column width

        # Set up the response
        output.seek(0)
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename=template.xlsx'
        return response

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
