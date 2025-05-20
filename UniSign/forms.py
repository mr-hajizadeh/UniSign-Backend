from django import forms
from jalali_date_new.fields import JalaliDateTimeField
from jalali_date_new.widgets import AdminJalaliDateTimeWidget  # نام صحیح
from .models import Course

class CourseAdminForm(forms.ModelForm):
    exam_time = JalaliDateTimeField(
        widget=AdminJalaliDateTimeWidget(  # تغییر نام ویجت
            attrs={
                "id": "id_exam_time",
                "time": "true"  # فعال کردن بخش زمان
            }
        ),
        label='تاریخ و زمان آزمون'
    )

    class Meta:
        model = Course
        fields = '__all__'