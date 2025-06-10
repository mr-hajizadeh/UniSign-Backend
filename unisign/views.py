from django.shortcuts import render, redirect
from .forms import ExcelUploadForm
from .models import Student, Course, StudentCourse, Term
import pandas as pd
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from .forms import TeacherRegistrationForm
from django.http import JsonResponse
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import pymupdf
import re
import arabic_reshaper
from bidi.algorithm import get_display
import os
from .utils import extract_students_from_pdf
from rest_framework.parsers import MultiPartParser
from .models import StudentSignature
from .serializers import StudentSignatureSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
import logging

logger = logging.getLogger(__name__)

def upload_excel(request):
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
                df = pd.read_excel(excel_file)
                success_count = 0
                duplicate_count = 0
                
                for _, row in df.iterrows():
                    try:
                        # Create or get course
                        course, _ = Course.objects.get_or_create(
                            course_code=row.get('کددرس', ''),
                            group_code=row.get('کد‌گروه‌درسی', ''),
                            term=term,
                            defaults={
                                'course_name': row.get('درس', ''),
                                'teacher_national_id': row.get('کدملی‌مدرس', ''),
                                'teacher_name': row.get('نام‌مدرس', ''),
                                'max_capacity': row.get('حداکثر‌ظرفیت', 0) or 0,
                                'student_count': row.get('تعداددانشجو', 0) or 0,
                                'empty_capacity': row.get('ظرفیت‌خالی', 0) or 0,
                                'class_time': row.get('زمان‌تشکیل‌کلاس', ''),
                                'faculty_id': row.get('شناسه‌دانشکده', ''),
                                'group_type': row.get('نوع‌گروه‌درسی', ''),
                                'exam_location': row.get('محل‌آزمون', ''),
                                'exam_date': row.get('تاریخ‌امتحان', ''),
                                'exam_time': row.get('زمان‌آزمون', ''),
                                'group_id': row.get('شناسه‌گروه‌درسی', ''),
                                'registration_date': row.get('تاریخ‌ثبت', ''),
                            }
                        )
                        
                        # Create or get student (without term)
                        student, _ = Student.objects.get_or_create(
                            national_id=row.get('کدملی', ''),
                            student_number=row.get('شماره‌دانشجویی', ''),
                            defaults={
                                'first_name': row.get('نام', ''),
                                'last_name': row.get('نام‌خانوادگی', ''),
                                'entry_term': row.get('ترم‌ورود', ''),
                                'gender': row.get('جنسیت', ''),
                                'major_code': row.get('کدرشته', ''),
                                'major_name': row.get('رشته', ''),
                            }
                        )
                        
                        # Try to create student-course relationship with term
                        StudentCourse.objects.get_or_create(
                            student=student,
                            course=course,
                            term=term
                        )
                        success_count += 1
                        
                    except Exception as e:
                        if 'Duplicate entry' in str(e):
                            duplicate_count += 1
                            continue
                        raise e
                
                if duplicate_count > 0:
                    messages.warning(request, f'{duplicate_count} ثبت‌نام تکراری نادیده گرفته شد.')
                if success_count > 0:
                    messages.success(request, f'{success_count} ثبت‌نام با موفقیت انجام شد.')
                return redirect('upload_excel')
                
            except Exception as e:
                messages.error(request, f'خطا در پردازش فایل: {e}')
    else:
        form = ExcelUploadForm()
    return render(request, 'excel_processor/upload_excel.html', {'form': form})

@login_required
def teacher_register(request):
    if request.method == 'POST':
        form = TeacherRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'ثبت‌نام با موفقیت انجام شد.')
            return redirect('teacher_dashboard')
    else:
        form = TeacherRegistrationForm()
    return render(request, 'registration/teacher_register.html', {'form': form})

@login_required
def teacher_dashboard(request):
    if not hasattr(request.user, 'teacher'):
        messages.error(request, 'شما دسترسی به این صفحه را ندارید.')
        return redirect('teacher-register')
    
    courses = Course.objects.filter(teacher=request.user.teacher)
    return render(request, 'teacher/dashboard.html', {'courses': courses})\

@login_required
def upload_course_pdf(request, course_id):
    if request.method == 'POST' and request.FILES.get('pdf_file'):
        try:
            course = Course.objects.get(id=course_id)
            if course.teacher != request.user.teacher:
                messages.error(request, 'شما دسترسی به این درس را ندارید.')
                return redirect('teacher_dashboard')

            pdf_file = request.FILES['pdf_file']
            
            # Save PDF file
            pdf_path = f'pdfs/{course.course_code}_{course.group_code}.pdf'
            default_storage.save(pdf_path, ContentFile(pdf_file.read()))
            
            # Process PDF and extract student information
            students_data = extract_students_from_pdf(course)

            # Update database
            for student_data in students_data:
                student, created = Student.objects.get_or_create(
                    national_id=student_data['national_id'],
                    defaults={
                        'first_name': student_data['student_name'].split()[0],
                        'last_name': ' '.join(student_data['student_name'].split()[1:]),
                        'student_number': student_data['student_number'],
                        'entry_term': student_data['entry_year'],
                        'gender': '',  # Default value
                        'major_code': '',  # Default value
                        'major_name': '',  # Default value
                    }
                )

                # Create or update student-course relationship
                StudentCourse.objects.get_or_create(
                    student=student,
                    course=course
                )

            messages.success(request, f'{len(students_data)} دانشجو با موفقیت ثبت شدند.')
            return redirect('teacher_dashboard')

        except Exception as e:
            messages.error(request, f'خطا در پردازش فایل: {str(e)}')
            return redirect('teacher_dashboard')

    return redirect('teacher_dashboard')

class StudentSignatureView(APIView):
    parser_classes = (MultiPartParser,)
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def post(self, request, student_id, course_id):
        try:
            # Log authentication info
            logger.info(f"User from request: {request.user}")
            logger.info(f"User ID: {request.user.id}")
            logger.info(f"Auth header: {request.headers.get('Authorization')}")
            
            if not request.user or not request.user.id:
                return Response(
                    {"error": "کاربر احراز هویت نشده است."},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            student = Student.objects.get(id=student_id)
            course = Course.objects.get(id=course_id)
            
            # Check if signature already exists
            existing_signature = StudentSignature.objects.filter(
                student=student,
                course=course
            ).first()

            # Create signature data
            signature_data = {
                'student': student.id,
                'course': course.id,
                'signature_image': request.FILES.get('image')
            }
            
            logger.info(f"Signature data: {signature_data}")
            
            if existing_signature:
                # Update existing signature
                serializer = StudentSignatureSerializer(existing_signature, data=signature_data, context={'request': request})
            else:
                # Create new signature
                serializer = StudentSignatureSerializer(data=signature_data, context={'request': request})

            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            logger.error(f"Serializer errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        except Student.DoesNotExist:
            return Response(
                {"error": "دانشجو یافت نشد."},
                status=status.HTTP_404_NOT_FOUND
            )
        except Course.DoesNotExist:
            return Response(
                {"error": "درس یافت نشد."},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return Response(
                {"error": f"خطای غیرمنتظره: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
