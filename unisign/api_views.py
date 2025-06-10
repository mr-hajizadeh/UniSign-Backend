from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth.models import User
from .models import Course, StudentCourse, Attendance, StudentSignature
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
from datetime import datetime, timedelta
import jdatetime
import logging
from django.db import models

logger = logging.getLogger(__name__)

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'next_page': self.page.next_page_number() if self.page.has_next() else None,
            'previous_page': self.page.previous_page_number() if self.page.has_previous() else None,
            'results': data
        })

def get_user_from_token(request):
    """
    Get user from JWT token in Authorization header
    """
    try:
        jwt_authenticator = JWTAuthentication()
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            validated_token = jwt_authenticator.get_validated_token(token)
            user = jwt_authenticator.get_user(validated_token)
            return user
    except Exception as e:
        return None
    return None

def add_security_headers(response):
    """
    Add security headers to the response
    """
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response["X-Content-Type-Options"] = "nosniff"
    response["X-Frame-Options"] = "DENY"
    response["X-XSS-Protection"] = "1; mode=block"
    response["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

@api_view(['GET'])
@permission_classes([AllowAny])
def courses_with_exam_dates(request):
    """
    API endpoint for getting courses with exam dates and attendance information
    Query parameters:
    - date: Date in format YYYY-MM-DD
    - all: If 'all' is provided, returns all courses regardless of exam date
    """
    # Handle OPTIONS request for CORS
    if request.method == "OPTIONS":
        response = Response()
        return add_security_headers(response)

    # Get user from token
    user = get_user_from_token(request)
    if not user:
        response = Response({
            'message': 'توکن نامعتبر است'
        }, status=status.HTTP_401_UNAUTHORIZED)
        return add_security_headers(response)

    date = request.query_params.get('date')
    get_all = request.query_params.get('all')

    if get_all == 'all':
        courses = Course.objects.all()
        start_datetime = None
        end_datetime = None
    else:
        if not date:
            response = Response({
                'message': 'لطفا تاریخ را وارد کنید'
            }, status=status.HTTP_400_BAD_REQUEST)
            return add_security_headers(response)

        try:
            # Parse the input date
            input_date = datetime.strptime(date, '%Y-%m-%d')
            
            # Create start of day (00:00:00)
            start_datetime = timezone.make_aware(datetime.combine(input_date.date(), datetime.min.time()))
            
            # Create end of day (23:59:59)
            end_datetime = timezone.make_aware(datetime.combine(input_date.date(), datetime.max.time()))

        except ValueError:
            response = Response({
                'message': 'فرمت تاریخ نامعتبر است. لطفا از فرمت YYYY-MM-DD استفاده کنید'
            }, status=status.HTTP_400_BAD_REQUEST)
            return add_security_headers(response)

        courses = Course.objects.filter(
            exam_date__gte=start_datetime,
            exam_date__lte=end_datetime
        )

    # Get attendance statistics for each course
    courses_with_stats = []
    for course in courses:
        # Get total students in course
        course_total_students = StudentCourse.objects.filter(course=course).count()
        
        # Get all signatures for this course
        signatures = StudentSignature.objects.filter(course=course)
        
        # Log all signatures for debugging
        logger.info(f"Course: {course.course_name} ({course.course_code})")
        logger.info(f"Total students: {course_total_students}")
        logger.info(f"All signatures for this course:")
        for sig in signatures:
            logger.info(f"- Student: {sig.student.first_name} {sig.student.last_name}, Created at: {sig.created_at}")
        
        # Count present students (those who have signed)
        course_present_students = signatures.count()
        
        # Calculate absent students
        course_absent_students = course_total_students - course_present_students

        # Log attendance statistics
        logger.info(f"Present students (with signatures): {course_present_students}")
        logger.info(f"Absent students: {course_absent_students}")
        logger.info(f"Attendance percentage: {round((course_present_students / course_total_students * 100) if course_total_students > 0 else 0, 2)}%")

        courses_with_stats.append({
            'id': course.id,
            'course_code': course.course_code,
            'course_name': course.course_name,
            'group_code': course.group_code,
            'teacher': f"{course.teacher.first_name} {course.teacher.last_name}",
            'exam_date': course.exam_date_jalali() if course.exam_date else None,
            'exam_location': course.exam_location,
            'term': course.term.name if course.term else None,
            'attendance_stats': {
                'total_students': course_total_students,
                'present_students': course_present_students,
                'absent_students': course_absent_students,
                'attendance_percentage': round((course_present_students / course_total_students * 100) if course_total_students > 0 else 0, 2)
            }
        })

    # Pagination
    paginator = StandardResultsSetPagination()
    paginated_courses = paginator.paginate_queryset(courses_with_stats, request)

    response = paginator.get_paginated_response(paginated_courses)
    return add_security_headers(response)

@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    """
    API endpoint for user login
    """
    # Handle OPTIONS request for CORS
    if request.method == "OPTIONS":
        response = Response()
        return add_security_headers(response)

    username = request.data.get('username')
    password = request.data.get('password')

    if not username or not password:
        response = Response({
            'message': 'لطفا نام کاربری و رمز عبور را وارد کنید'
        }, status=status.HTTP_400_BAD_REQUEST)
        return add_security_headers(response)

    user = authenticate(username=username, password=password)

    if user is not None:
        refresh = RefreshToken.for_user(user)
        response = Response({
            'access_token': str(refresh.access_token),
            'refresh_token': str(refresh),
            'user': {
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'email': user.email
            }
        })
        return add_security_headers(response)
    else:
        response = Response({
            'message': 'نام کاربری یا رمز عبور اشتباه است'
        }, status=status.HTTP_401_UNAUTHORIZED)
        return add_security_headers(response)

@api_view(['GET'])
@permission_classes([AllowAny])
def overall_statistics(request):
    """
    API endpoint for getting overall attendance statistics
    Query parameters:
    - date: Date in format YYYY-MM-DD (optional) or 'all' for all dates
    """
    # Handle OPTIONS request for CORS
    if request.method == "OPTIONS":
        response = Response()
        return add_security_headers(response)

    # Get user from token
    user = get_user_from_token(request)
    if not user:
        response = Response({
            'message': 'توکن نامعتبر است'
        }, status=status.HTTP_401_UNAUTHORIZED)
        return add_security_headers(response)

    date = request.query_params.get('date')
    courses = Course.objects.all()
    start_datetime = None
    end_datetime = None

    if date and date != 'all':
        try:
            # Parse the input date
            input_date = datetime.strptime(date, '%Y-%m-%d')
            
            # Create start of day (00:00:00)
            start_datetime = timezone.make_aware(datetime.combine(input_date.date(), datetime.min.time()))
            
            # Create end of day (23:59:59)
            end_datetime = timezone.make_aware(datetime.combine(input_date.date(), datetime.max.time()))

            courses = courses.filter(
                exam_date__gte=start_datetime,
                exam_date__lte=end_datetime
            )

        except ValueError:
            response = Response({
                'message': 'فرمت تاریخ نامعتبر است. لطفا از فرمت YYYY-MM-DD استفاده کنید'
            }, status=status.HTTP_400_BAD_REQUEST)
            return add_security_headers(response)

    # Get overall statistics
    total_courses = courses.count()
    total_students = StudentCourse.objects.filter(course__in=courses).count()
    
    if start_datetime and end_datetime:
        total_present = Attendance.objects.filter(
            course__in=courses,
            signed_at__gte=start_datetime,
            signed_at__lte=end_datetime
        ).count()
    else:
        total_present = Attendance.objects.filter(course__in=courses).count()
    
    total_absent = total_students - total_present
    overall_attendance_percentage = round((total_present / total_students * 100) if total_students > 0 else 0, 2)

    response = Response({
        'total_courses': total_courses,
        'total_students': total_students,
        'total_present': total_present,
        'total_absent': total_absent,
        'overall_attendance_percentage': overall_attendance_percentage
    })
    return add_security_headers(response)

@api_view(['GET'])
@permission_classes([AllowAny])
def get_course_students(request, course_id):
    """
    API endpoint for getting students in a course with their signature information
    """
    # Handle OPTIONS request for CORS
    if request.method == "OPTIONS":
        response = Response()
        return add_security_headers(response)

    # Get user from token
    user = get_user_from_token(request)
    if not user:
        response = Response({
            'message': 'توکن نامعتبر است'
        }, status=status.HTTP_401_UNAUTHORIZED)
        return add_security_headers(response)

    try:
        # Get the course
        course = Course.objects.get(id=course_id)
        
        # Get all students enrolled in this course
        student_courses = StudentCourse.objects.filter(course=course).select_related('student')
        
        # Prepare the response data
        students_data = []
        for sc in student_courses:
            student = sc.student
            photo_url = None
            if student.photo:
                photo_url = request.build_absolute_uri(student.photo.url)
            
            # Get student signature if exists
            signature = StudentSignature.objects.filter(student=student, course=course).first()
            signature_data = None
            if signature:
                signature_data = {
                    'id': signature.id,
                    'signature_image_url': request.build_absolute_uri(signature.signature_image.url) if signature.signature_image else None,
                    'created_at': signature.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'created_at_jalali': signature.created_at_jalali(),
                    'signed_by': {
                        'id': signature.signed_by.id,
                        'username': signature.signed_by.username,
                        'first_name': signature.signed_by.first_name,
                        'last_name': signature.signed_by.last_name,
                        'full_name': f"{signature.signed_by.first_name} {signature.signed_by.last_name}".strip()
                    }
                }
            
            students_data.append({
                'id': student.id,
                'first_name': student.first_name,
                'last_name': student.last_name,
                'student_number': student.student_number,
                'national_id': student.national_id,
                'entry_term': student.entry_term,
                'gender': student.gender,
                'major_code': student.major_code,
                'major_name': student.major_name,
                'enrollment_date': sc.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'photo_url': photo_url,
                'signature': signature_data
            })

        # Pagination
        paginator = StandardResultsSetPagination()
        paginated_students = paginator.paginate_queryset(students_data, request)

        response = paginator.get_paginated_response(paginated_students)
        return add_security_headers(response)

    except Course.DoesNotExist:
        response = Response({
            'message': 'درس مورد نظر یافت نشد'
        }, status=status.HTTP_404_NOT_FOUND)
        return add_security_headers(response)
    except Exception as e:
        response = Response({
            'message': f'خطا در دریافت اطلاعات: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return add_security_headers(response)

@api_view(['GET'])
@permission_classes([AllowAny])
def search_courses(request):
    """
    API endpoint for searching courses based on text input
    Query parameters:
    - q: Search query text
    """
    # Handle OPTIONS request for CORS
    if request.method == "OPTIONS":
        response = Response()
        return add_security_headers(response)

    # Get user from token
    user = get_user_from_token(request)
    if not user:
        response = Response({
            'message': 'توکن نامعتبر است'
        }, status=status.HTTP_401_UNAUTHORIZED)
        return add_security_headers(response)

    search_query = request.query_params.get('q', '')
    if not search_query:
        response = Response({
            'message': 'لطفا متن جستجو را وارد کنید'
        }, status=status.HTTP_400_BAD_REQUEST)
        return add_security_headers(response)

    # Search in course fields
    courses = Course.objects.filter(
        models.Q(course_code__icontains=search_query) |
        models.Q(course_name__icontains=search_query) |
        models.Q(group_code__icontains=search_query) |
        models.Q(teacher__first_name__icontains=search_query) |
        models.Q(teacher__last_name__icontains=search_query) |
        models.Q(exam_location__icontains=search_query)
    ).select_related('teacher', 'term')

    # Prepare response data
    courses_data = []
    for course in courses:
        # Get total students in course
        course_total_students = StudentCourse.objects.filter(course=course).count()
        
        # Get all signatures for this course
        signatures = StudentSignature.objects.filter(course=course)
        
        # Count present students (those who have signed)
        course_present_students = signatures.count()
        
        # Calculate absent students
        course_absent_students = course_total_students - course_present_students

        courses_data.append({
            'id': course.id,
            'course_code': course.course_code,
            'course_name': course.course_name,
            'group_code': course.group_code,
            'teacher': f"{course.teacher.first_name} {course.teacher.last_name}",
            'exam_date': course.exam_date_jalali() if course.exam_date else None,
            'exam_location': course.exam_location,
            'term': course.term.name if course.term else None,
            'attendance_stats': {
                'total_students': course_total_students,
                'present_students': course_present_students,
                'absent_students': course_absent_students,
                'attendance_percentage': round((course_present_students / course_total_students * 100) if course_total_students > 0 else 0, 2)
            }
        })

    # Pagination
    paginator = StandardResultsSetPagination()
    paginated_courses = paginator.paginate_queryset(courses_data, request)

    response = paginator.get_paginated_response(paginated_courses)
    return add_security_headers(response) 