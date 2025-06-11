from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from jalali_date_new.fields import JalaliDateTimeField
from jalali_date_new.widgets import AdminJalaliDateTimeWidget
from .models import Teacher, Course, Term
import jdatetime

class ExcelUploadForm(forms.Form):
    excel_file = forms.FileField(
        label='فایل Excel',
        help_text='فایل Excel را انتخاب کنید'
    )
    term = forms.CharField(
        max_length=50,
        label='ترم',
        widget=forms.TextInput(attrs={
            'placeholder': 'مثال: 032',
            'class': 'vTextField'
        })
    )

class TeacherRegistrationForm(UserCreationForm):
    national_id = forms.CharField(max_length=10, label='کد ملی')
    first_name = forms.CharField(max_length=100, label='نام')
    last_name = forms.CharField(max_length=100, label='نام خانوادگی')

    class Meta:
        model = User
        fields = ('username', 'national_id', 'first_name', 'last_name', 'password1', 'password2')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        if commit:
            user.save()
            Teacher.objects.create(
                user=user,
                national_id=self.cleaned_data['national_id'],
                first_name=self.cleaned_data['first_name'],
                last_name=self.cleaned_data['last_name']
            )
        return user

class CourseAdminForm(forms.ModelForm):
    exam_date = JalaliDateTimeField(
        widget=AdminJalaliDateTimeWidget(
            attrs={
                'class': 'vDateField',
                'time': 'true',  # Enable time selection
                'date_format': 'yy/mm/dd',
                'time_format': 'HH:mm:ss',
                'change_month': 'true',
                'change_year': 'true',
                'year_range': '1300:1500'
            }
        ),
        label='تاریخ و زمان امتحان',
        required=False
    )
    registration_date = JalaliDateTimeField(
        widget=AdminJalaliDateTimeWidget(
            attrs={
                'class': 'vDateField',
                'time': 'true',  # Enable time selection
                'date_format': 'yy/mm/dd',
                'time_format': 'HH:mm:ss',
                'change_month': 'true',
                'change_year': 'true',
                'year_range': '1300:1500',
                'disabled': 'disabled'  # Make the field read-only
            }
        ),
        label='تاریخ و زمان ثبت',
        required=False
    )

    class Meta:
        model = Course
        fields = ['course_code', 'course_name', 'group_code', 'teacher', 'class_time', 'faculty_id', 'group_type', 'exam_location', 'exam_date', 'group_id', 'registration_date']

    def clean_exam_date(self):
        date = self.cleaned_data.get('exam_date')
        if date:
            try:
                # Convert Jalali datetime to Gregorian
                jalali_datetime = jdatetime.datetime.fromgregorian(datetime=date)
                return jalali_datetime.togregorian()
            except:
                return date
        return date

    def clean_registration_date(self):
        date = self.cleaned_data.get('registration_date')
        if date:
            try:
                # Convert Jalali date to Gregorian
                jalali_date = jdatetime.date.fromgregorian(date=date)
                return jalali_date.togregorian()
            except:
                return date
        return date

class PDFUploadForm(forms.Form):
    pdf_file = forms.FileField(label='فایل PDF') 