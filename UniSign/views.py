from django.shortcuts import render, redirect
from .forms import CourseAdminForm
from .models import Student, Course, Signature, Enrollment
from django.contrib.auth.decorators import user_passes_test
import os, re, arabic_reshaper, fitz
from bidi.algorithm import get_display
from django.conf import settings
from jalali_date import datetime2jalali, date2jalali
from .utils import extract_students_from_pdf
from django.http import JsonResponse
from django.utils import timezone
from datetime import datetime, timedelta
import json
import base64
from django.core.files.base import ContentFile
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.views.decorators.csrf import csrf_exempt


def fix_repeated_digits(text):
    return re.sub(r'(\d)\1{2,}', r'\1', text)


@user_passes_test(lambda u: u.is_superuser)
def add_course(request):
    if request.method == 'POST':
        form = CourseAdminForm(request.POST, request.FILES)
        if form.is_valid():
            course = form.save()

            try:
                students_data = extract_students_from_pdf(course)
                students_to_create = []
                students_to_enroll = []

                for student_data in students_data:
                    # Check if student already exists
                    student, created = Student.objects.get_or_create(
                        national_id=student_data['national_id'],
                        defaults={
                            'row': student_data['row'],
                            'exam_place': student_data['exam_place'],
                            'seat_number': student_data['seat_number'],
                            'student_number': student_data['student_number'],
                            'student_name': student_data['student_name'],
                            'entry_year': student_data['entry_year'],
                            'student_image': student_data['student_image'],
                        }
                    )
                    
                    # Create enrollment for the course
                    enrollment, created = Enrollment.objects.get_or_create(
                        student=student,
                        course=course
                    )

                return redirect('course_list')
            except Exception as e:
                form.add_error(None, f"خطا در پردازش فایل PDF: {e}")
    else:
        form = CourseAdminForm()
    return render(request, 'add_course.html', {'form': form})


class APITokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return None

        try:
            token = auth_header.split(' ')[1]
            if token == settings.API_TOKEN:
                return (None, None)  # (user, auth) tuple
            raise AuthenticationFailed('Invalid token')
        except:
            raise AuthenticationFailed('Invalid token format')


def check_api_token(view_func):
    def wrapper(request, *args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return JsonResponse({
                'status': 'error',
                'message': 'توکن API الزامی است'
            }, status=401)

        try:
            token = auth_header.split(' ')[1]
            if token != settings.API_TOKEN:
                return JsonResponse({
                    'status': 'error',
                    'message': 'توکن نامعتبر است'
                }, status=401)
        except:
            return JsonResponse({
                'status': 'error',
                'message': 'فرمت توکن نامعتبر است'
            }, status=401)

        return view_func(request, *args, **kwargs)

    return wrapper


@check_api_token
def get_course_students(request, course_id):
    try:
        course = Course.objects.get(id=course_id)
        enrollments = Enrollment.objects.filter(course=course)

        students_data = []
        for enrollment in enrollments:
            student = enrollment.student
            signature = Signature.objects.filter(course=course, student=student).first()

            student_info = {
                'student_id': student.id,
                'student_name': student.student_name,
                'student_number': student.student_number,
                'national_id': student.national_id,
                'exam_place': student.exam_place,
                'seat_number': student.seat_number,
                'has_signed': signature is not None,
                'signed_at': datetime2jalali(signature.signed_at).strftime('%Y/%m/%d - %H:%M:%S') if signature else None,
                'signature': signature.signature_base64 if signature else None,
                'student_image': request.build_absolute_uri(student.student_image.url) if student.student_image else None
            }
            students_data.append(student_info)

        return JsonResponse({
            'status': 'success',
            'course_name': course.course_name,
            'exam_time': course.exam_time_jalali(),
            'professor': course.professor,
            'group_info': course.group_info,
            'term_info': course.term_info,
            'students': students_data
        })

    except Course.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'درس مورد نظر یافت نشد'
        }, status=404)


@csrf_exempt
@check_api_token
def upload_signature(request, student_id):
    if request.method != 'POST':
        return JsonResponse({
            'status': 'error',
            'message': 'این API فقط درخواست POST را می‌پذیرد'
        }, status=405)

    try:
        data = json.loads(request.body)
        course_id = data.get('course_id')
        signature_base64 = data.get('signature')

        if not all([course_id, signature_base64]):
            return JsonResponse({
                'status': 'error',
                'message': 'اطلاعات ناقص است'
            }, status=400)

        # حذف هدر base64 اگر وجود داشته باشد
        if ',' in signature_base64:
            signature_base64 = signature_base64.split(',')[1]

        try:
            # بررسی معتبر بودن base64
            base64.b64decode(signature_base64)

            # ذخیره امضا
            course = Course.objects.get(id=course_id)
            student = Student.objects.get(id=student_id)

            # بررسی زمان امضا
            current_time = timezone.now()
            exam_time = course.exam_time
            one_hour_after_exam = exam_time + timedelta(hours=1)

            if current_time < exam_time or current_time > one_hour_after_exam:
                return JsonResponse({
                    'status': 'error',
                    'message': 'امضا فقط در بازه زمانی آزمون تا یک ساعت بعد از آن مجاز است'
                }, status=400)

            # ایجاد یا به‌روزرسانی امضا
            signature, created = Signature.objects.update_or_create(
                course=course,
                student=student,
                defaults={'signature_base64': signature_base64}
            )

            return JsonResponse({
                'status': 'success',
                'message': 'امضا با موفقیت ذخیره شد',
                'signed_at': datetime2jalali(signature.signed_at).strftime('%Y/%m/%d - %H:%M:%S'),
                'signature': signature.signature_base64
            })

        except base64.binascii.Error:
            return JsonResponse({
                'status': 'error',
                'message': 'فرمت base64 نامعتبر است'
            }, status=400)

    except Course.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'درس مورد نظر یافت نشد'
        }, status=404)
    except Student.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'دانشجوی مورد نظر یافت نشد'
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'فرمت JSON نامعتبر است'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'خطا در پردازش درخواست: {str(e)}'
        }, status=500)



def get_daily_courses(request):
    try:
        # Get the date from query parameters, default to today
        date_str = request.GET.get('date')
        if date_str:
            date = datetime.strptime(date_str, '%Y-%m-%d')
        else:
            date = timezone.now().date()

        # Create datetime objects for start and end of the day
        start_of_day = datetime.combine(date, datetime.min.time())
        end_of_day = datetime.combine(date, datetime.max.time())

        # Get all courses for the specified date (from 00:00:00 to 23:59:59)
        courses = Course.objects.filter(
            exam_time__gte=start_of_day,
            exam_time__lte=end_of_day
        )
        
        result = []
        total_absences = 0
        
        for course in courses:
            # Get total enrolled students
            total_students = Enrollment.objects.filter(course=course).count()
            
            # Get students who signed (present)
            present_students = Signature.objects.filter(course=course).count()
            
            # Calculate absences
            absences = total_students - present_students
            total_absences += absences
            
            course_data = {
                'course_id': course.id,
                'course_name': course.course_name,
                'professor': course.professor,
                'group_info': course.group_info,
                'exam_time': course.exam_time_jalali(),
                'total_students': total_students,
                'present_students': present_students,
                'absences': absences,
                'pdf_url': request.build_absolute_uri(course.pdf_file.url) if course.pdf_file else None
            }
            result.append(course_data)
        
        return JsonResponse({
            'status': 'success',
            'date': date_str or date.strftime('%Y-%m-%d'),
            'summary': {
                'total_courses': len(courses),
                'total_absences': total_absences
            },
            'courses': result
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)


def get_absent_students(request, course_id):
    try:
        # Get the course
        course = Course.objects.get(id=course_id)

        # Get all enrolled students
        enrolled_students = Enrollment.objects.filter(course=course)

        # Get students who have signed (present)
        present_students = Signature.objects.filter(course=course).values_list('student_id', flat=True)

        # Get absent students (enrolled but not signed)
        absent_students = []
        for enrollment in enrolled_students:
            if enrollment.student.id not in present_students:
                student = enrollment.student
                absent_students.append({
                    'student_id': student.id,
                    'student_name': student.student_name,
                    'student_number': student.student_number,
                    'national_id': student.national_id,
                    'exam_place': student.exam_place,
                    'seat_number': student.seat_number
                })

        return JsonResponse({
            'status': 'success',
            'course': {
                'course_name': course.course_name,
                'professor': course.professor,
                'group_info': course.group_info,
                'exam_time': course.exam_time_jalali()
            },
            'summary': {
                'total_students': enrolled_students.count(),
                'present_students': len(present_students),
                'absent_students': len(absent_students)
            },
            'absent_students': absent_students
        })

    except Course.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'درس مورد نظر یافت نشد'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)


def get_daily_course_absences(request):
    try:
        # Get the date from query parameters, default to today
        date_str = request.GET.get('date')
        if date_str:
            date = datetime.strptime(date_str, '%Y-%m-%d')
        else:
            date = timezone.now().date()

        # Get all courses for the specified date
        courses = Course.objects.filter(exam_time__date=date)

        course_details = []
        total_absences = 0

        for course in courses:
            # Get all enrolled students
            enrolled_students = Enrollment.objects.filter(course=course)

            # Get students who have signed (present)
            present_students = Signature.objects.filter(course=course).values_list('student_id', flat=True)

            # Get absent students
            absent_students = []
            for enrollment in enrolled_students:
                if enrollment.student.id not in present_students:
                    student = enrollment.student
                    absent_students.append({
                        'student_id': student.id,
                        'student_name': student.student_name,
                        'student_number': student.student_number,
                        'national_id': student.national_id,
                        'exam_place': student.exam_place,
                        'seat_number': student.seat_number
                    })

            total_absences += len(absent_students)

            course_details.append({
                'course_id': course.id,
                'course_name': course.course_name,
                'professor': course.professor,
                'group_info': course.group_info,
                'exam_time': course.exam_time_jalali(),
                'total_students': enrolled_students.count(),
                'present_students': len(present_students),
                'absent_students_count': len(absent_students),
                'absent_students_list': absent_students
            })

        # Sort courses by number of absences (descending)
        course_details.sort(key=lambda x: x['absent_students_count'], reverse=True)

        return JsonResponse({
            'status': 'success',
            'date': date_str or date.strftime('%Y-%m-%d'),
            'summary': {
                'total_courses': len(courses),
                'total_absences': total_absences
            },
            'courses': course_details
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)
