# 🖥️ UniSign Backend – University Attendance Management System

**UniSign Backend** is a web-based university attendance and digital signature management system built with Python and Django.

It provides a centralized backend for managing university courses, students, teachers, academic terms, exam sessions, attendance records, and digital signatures.

The system also includes a Django Admin interface and REST API to communicate with the UniSign Android application.

## 🌟 Key Features

- **👨‍🎓 Student Management:** Manage student information, profiles, and academic records.
- **👨‍🏫 Teacher Management:** Manage university teachers and their assigned courses.
- **📚 Course Management:** Create and manage courses, exam dates, groups, and academic terms.
- **📊 Enrollment Management:** Connect students to courses and manage enrollment records.
- **📥 Excel Import:** Import student registration and course information from Excel files.
- **📄 PDF Processing:** Upload attendance PDF files and extract student information and available student photos.
- **✍️ Digital Signature Management:** Store and retrieve student signatures for individual courses.
- **📅 Persian Calendar Support:** Display and manage dates using the Persian calendar.
- **🔐 JWT Authentication:** Secure API authentication using JSON Web Tokens.
- **📱 Android Integration:** Provide REST API endpoints for the UniSign Android application.
- **📈 Exam Statistics:** Retrieve overall attendance and signature statistics.

## 🖼️ Screenshots

The following screenshots can be added to the `screenshots/` directory:

```text
screenshots/
├── admin_dashboard.png
├── courses.png
├── students.png
├── excel_upload.png
├── pdf_upload.png
└── attendance.png
```

<!-- Replace these placeholders with actual screenshots of your Django application. -->

| Admin Dashboard | Course Management |
|---|---|
| ![Dashboard](screenshots/admin_dashboard.png) | ![Courses](screenshots/courses.png) |

| Excel Import | PDF Processing |
|---|---|
| ![Excel Import](screenshots/excel_upload.png) | ![PDF Processing](screenshots/pdf_upload.png) |

## 🛠️ Tech Stack

| Category | Technology |
|---|---|
| Programming Language | Python |
| Backend Framework | Django 5.2 |
| Database | MySQL |
| API | Django REST API |
| Authentication | JWT |
| Data Import | Excel Processing |
| Document Processing | PyMuPDF |
| Persian Text Processing | arabic_reshaper / python-bidi |
| Frontend | Django Templates |
| Date System | Persian (Jalali) Calendar |

## 📂 Project Structure

```text
UniSign-Backend/
│
├── manage.py
├── requirements.txt
│
├── unisign/
│   ├── settings.py
│   ├── urls.py
│   ├── models.py
│   ├── admin.py
│   ├── api_views.py
│   └── ...
│
├── templates/
│   └── ...
│
├── static/
│   └── ...
│
├── staticfiles/
│   └── ...
│
└── media/
    └── ...
```

**Main components:**

- `models.py`: Database models and relationships.
- `admin.py`: Django Admin configuration and custom management pages.
- `api_views.py`: API endpoints for Android application integration.
- `settings.py`: Django project configuration.
- `templates/`: HTML templates.
- `static/`: Static assets.
- `media/`: Uploaded files and generated media.

## ⚙️ Requirements

Before installing the project, make sure you have:

- Python 3.11 (recommended for the current dependency set).
- MySQL Server.
- pip.
- Git.

**Python compatibility note:**

The current dependency set includes `django-jalali-date==2.0.0`, which relies on `distutils`. Since `distutils` was removed from the Python standard library in Python 3.12, Python 3.11 is the recommended option for this version of the project.

Python 3.12 and newer have not been verified with the current dependencies.

## 🚀 Installation & Setup

The following instructions are for Windows and PowerShell.

### 1. Clone the Repository

```bash
git clone https://github.com/USERNAME/UniSign-Backend.git
```

Navigate to the project directory:

```bash
cd UniSign-Backend
```

### 2. Create a Virtual Environment

```powershell
python -m venv .venv
```

Activate the environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks script execution, use the virtual environment's Python executable directly:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```

### 3. Install Dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4. Configure MySQL Database

Start your MySQL server and create a database:

```sql
CREATE DATABASE university
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;
```

Configure the database connection in:

```text
unisign/settings.py
```

Set the appropriate values for:

- `ENGINE`
- `NAME`
- `USER`
- `PASSWORD`
- `HOST`
- `PORT`

**Important:** The current local database configuration may need to be changed according to your own MySQL installation.

### 5. Apply Database Migrations

Run the following commands from the project root:

```bash
python manage.py check
python manage.py migrate
```

To create an administrator account:

```bash
python manage.py createsuperuser
```

If you already have an administrator account, you can skip this step.

### 6. Run the Development Server

```bash
python manage.py runserver
```

Open the following address in your browser:

```text
http://127.0.0.1:8000/admin/
```

Log in using your Django administrator account.

The root URL (`/`) redirects to the Django Admin panel.

To stop the development server, press `Ctrl + C`.

## 📥 Excel & PDF Processing

UniSign provides custom upload pages through the Django Admin interface.

### Excel Import

Administrators can upload Excel files containing university registration information.

The system processes the uploaded information to manage:

- Courses
- Students
- Teachers
- Student enrollment records

### PDF Processing

Administrators can upload attendance PDF files.

The processing workflow extracts available student information and photos from the uploaded documents and updates the corresponding records.

**Upload pages:**

| Feature | URL |
|---|---|
| Excel Upload | `/admin/unisign/course/upload-excel/` |
| PDF Upload | `/admin/unisign/course/upload-pdf/` |

The upload pages are accessible after logging in with an authorized administrator account.

## 🔌 REST API Documentation

The backend provides REST API endpoints for communication with the Android application.

### Main Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/login/` | Authenticate users and obtain JWT |
| GET | `/api/courses/exam-dates/` | Retrieve courses and exam dates |
| GET | `/api/statistics/overall/` | Retrieve overall statistics |
| GET | `/api/courses/<course_id>/students/` | Retrieve students enrolled in a course |
| POST | `/api/students/<student_id>/signature/<course_id>/` | Submit or update a student's signature |
| GET | `/api/courses/search/` | Search courses |

### Authentication

Endpoints that require authentication must receive the JWT access token through the HTTP Authorization header:

```http
Authorization: Bearer <access_token>
```

The exact authentication requirements, request parameters, and response structures are defined in:

```text
unisign/api_views.py
```

For complete API documentation, refer to the endpoint implementations and their corresponding serializers or response logic.

## 📱 Android Application Integration

UniSign Backend serves as the API provider for the UniSign Android application.

**Android Repository:**

[UniSign-Android](https://github.com/mr-hajizadeh/UniSign-Android)

The Android application communicates with the backend to:

- Authenticate users.
- Retrieve course and exam information.
- Load student lists.
- Search for courses.
- Submit student signatures.
- Retrieve exam statistics.

### Local Network Configuration

For Android Emulator, the API base URL can use:

```text
http://10.0.2.2:8000/
```

For a physical Android device, use your computer's local network IP address:

```text
http://YOUR_PC_IP:8000/
```

The Django development server must be configured to accept connections from the device, and the appropriate host and network settings must be configured.

Use HTTPS for production deployments.

## 🔒 Security & Configuration

**Do not publish the current local configuration without reviewing it first.**

Before making this repository public:

- Remove hardcoded Django `SECRET_KEY` values.
- Remove database usernames and passwords.
- Remove hardcoded JWT secrets or API credentials.
- Move sensitive settings into environment variables or a private local configuration file.
- Add `.env` and other private configuration files to `.gitignore`.
- Provide a `.env.example` file containing only placeholder values.
- Set `DEBUG = False` in production.
- Configure `ALLOWED_HOSTS` with trusted domain names.
- Never upload real student information, photos, signatures, or database backups to a public repository.

If any real credentials have already been committed or exposed, rotate them. Removing them from the latest version of the source code does not invalidate previously exposed credentials.

## 🧪 Development

Useful Django management commands:

```bash
# Check project configuration
python manage.py check

# Apply database migrations
python manage.py migrate

# Create a new migration
python manage.py makemigrations

# Create an administrator
python manage.py createsuperuser

# Run the development server
python manage.py runserver
```

## 📌 Project Status

UniSign is an academic software project developed to simplify university exam attendance management and digital signature collection.

The system combines a Django-based management platform with an Android application to provide an integrated workflow for administrators and university staff.
