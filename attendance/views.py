from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count
from datetime import datetime
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.contrib.auth import login, logout, get_user_model

from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny

from .models import Course, QRCode, Attendance, OrganizationLocation
from .forms import StudentRegistrationForm
import json
import qrcode
from io import BytesIO
from django.core.files import File
import uuid


User = get_user_model()


# =====================================================
# API VIEWS
# =====================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def studentProfile(request):
    user = request.user
    return Response(
        {
            "id": user.id,
            "username": user.username,
            "course": getattr(user, "course", None),
        },
        status=status.HTTP_200_OK
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def signupStudent(request):
    serializer = SignupSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([AllowAny])
def Login(request):
    serializer = LoginSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.validated_data["user"]
        login(request, user)
        return Response(
            {
                "id": user.id,
                "username": user.username,
                "user_type": user.user_type
            },
            status=status.HTTP_200_OK
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@login_required
def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect("login")


# =====================================================
# QR SCANNING (GPS REMOVED)
# =====================================================

@login_required
def scan_qr(request):
    courses = Course.objects.filter(is_active=True)

    if request.method == "POST":
        qr_code_value = request.POST.get("qr_code")
        course_id = request.POST.get("course")

        if not qr_code_value or not course_id:
            messages.error(request, "Missing QR code or course.")
            return redirect("scan_qr")

        # Validate QR
        try:
            qr_code = QRCode.objects.get(code=qr_code_value, is_active=True)
        except QRCode.DoesNotExist:
            messages.error(request, "Invalid QR code.")
            return redirect("scan_qr")

        # Validate Course
        course = get_object_or_404(Course, id=course_id)

        # Prevent duplicate sign-in same day
        today = timezone.now().date()
        already_signed = Attendance.objects.filter(
            user=request.user,
            course=course,
            check_in_time__date=today
        ).exists()

        if already_signed:
            messages.warning(
                request,
                f"You have already signed in for {course.name} today."
            )
            return redirect("scan_qr")

        # Create attendance record (NO GPS)
        Attendance.objects.create(
            user=request.user,
            course=course,
            latitude=0.0,
            longitude=0.0,
            qr_code=qr_code,
            is_valid=True
        )

        messages.success(request, f"Successfully signed in for {course.name}!")
        return redirect("attendance_success")

    return render(request, "attendance/scan.html", {"courses": courses})


@login_required
def attendance_success(request):
    return render(request, "attendance/success.html")


# =====================================================
# ADMIN DASHBOARD
# =====================================================

@login_required
def admin_dashboard(request):
    if request.user.user_type != "admin":
        messages.error(request, "Access denied.")
        return redirect("scan_qr")

    # Filters
    date_filter = request.GET.get("date")
    course_filter = request.GET.get("course")
    user_type_filter = request.GET.get("user_type")
    location_filter = request.GET.get("location")

    if date_filter:
        try:
            date_filter = datetime.strptime(date_filter, "%Y-%m-%d").date()
        except ValueError:
            date_filter = timezone.now().date()
    else:
        date_filter = timezone.now().date()

    attendances = Attendance.objects.select_related(
        "user", "course", "qr_code"
    ).filter(check_in_time__date=date_filter)

    if course_filter:
        attendances = attendances.filter(course_id=course_filter)

    if user_type_filter:
        attendances = attendances.filter(user__user_type=user_type_filter)

    if location_filter:
        attendances = attendances.filter(qr_code__location__id=location_filter)

    # Statistics
    total_count = attendances.count()
    students_count = attendances.filter(user__user_type="student").count()
    tutors_count = attendances.filter(user__user_type="tutor").count()

    course_stats = attendances.values("course__name").annotate(
        total=Count("id")
    )
    course_labels = [c["course__name"] for c in course_stats]
    course_totals = [c["total"] for c in course_stats]

    location_stats = attendances.values("qr_code__location__name").annotate(
        total=Count("id")
    )
    location_labels = [l["qr_code__location__name"] for l in location_stats]
    location_totals = [l["total"] for l in location_stats]

    courses = Course.objects.filter(is_active=True)
    locations = OrganizationLocation.objects.filter(is_active=True)

    current_month = timezone.now().month
    current_year = timezone.now().year

    monthly_attendance = Attendance.objects.filter(
        check_in_time__month=current_month,
        check_in_time__year=current_year
    )

    monthly_total = monthly_attendance.count()

    top_course = (
        monthly_attendance.values("course__name")
        .annotate(total=Count("id"))
        .order_by("-total")
        .first()
    )

    paginator = Paginator(attendances, 15)
    page_number = request.GET.get("page")
    attendances = paginator.get_page(page_number)

    context = {
        "attendances": attendances,
        "total_today": total_count,
        "students_today": students_count,
        "tutors_today": tutors_count,
        "courses": courses,
        "locations": locations,
        "date_filter": date_filter,
        "course_filter": course_filter,
        "user_type_filter": user_type_filter,
        "location_filter": location_filter,
        "course_labels": json.dumps(course_labels),
        "course_totals": json.dumps(course_totals),
        "location_labels": json.dumps(location_labels),
        "location_totals": json.dumps(location_totals),
        "monthly_total": monthly_total,
        "top_course": top_course,
    }

    return render(request, "attendance/admin_dashboard.html", context)


# =====================================================
# ADMIN UTILITIES
# =====================================================

def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if request.user.user_type != "admin":
            messages.error(request, "Access denied.")
            return redirect("scan_qr")
        return view_func(request, *args, **kwargs)
    return login_required(wrapper)


@admin_required
def add_course(request):
    if request.method == "POST":
        name = request.POST.get("name")
        code = request.POST.get("code")
        description = request.POST.get("description")

        if Course.objects.filter(code=code).exists():
            messages.error(request, "Course code already exists.")
            return redirect("add_course")

        Course.objects.create(
            name=name,
            code=code,
            description=description
        )

        messages.success(request, "Course added successfully.")
        return redirect("add_course")

    courses = Course.objects.all()
    return render(request, "attendance/add_course.html", {"courses": courses})



@admin_required
@admin_required
def add_location(request):

    if request.method == "POST":
        name = request.POST.get("name")
        latitude = request.POST.get("latitude")
        longitude = request.POST.get("longitude")
        radius = request.POST.get("radius")

        location = OrganizationLocation.objects.create(
            name=name,
            latitude=latitude,
            longitude=longitude,
            radius_meters=radius
        )

        qr_code_string = str(uuid.uuid4())

        QRCode.objects.create(
            code=qr_code_string,
            location=location,
            is_active=True
        )

        messages.success(request, "Location and QR code created successfully.")

    locations = OrganizationLocation.objects.prefetch_related("qr_codes")

    return render(
        request,
        "attendance/add_location.html",
        {
            "locations": locations
        }
    )


from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from .models import OrganizationLocation

def delete_location(request, pk):
    if request.method == "POST":
        location = get_object_or_404(OrganizationLocation, pk=pk)
        location.delete()
        messages.success(request, f"Location '{location.name}' deleted successfully.")
    return redirect('admin_dashboard')  # or the page where locations are listed





# =====================================================
# AUTH REDIRECT
# =====================================================

@login_required
def post_login_redirect(request):
    if request.user.user_type == "admin":
        return redirect("admin_dashboard")
    return redirect("scan_qr")


# =====================================================
# STUDENT REGISTRATION
# =====================================================

def student_register(request):
    if request.method == "POST":
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Account created successfully!")
            return redirect("login")
        messages.error(request, "Please correct the errors below.")
    else:
        form = StudentRegistrationForm()

    return render(request, "attendance/student_register.html", {"form": form})


# =====================================================
# DEBUG LOCATIONS
# =====================================================

@login_required
def get_locations_debug(request):
    locations = OrganizationLocation.objects.filter(is_active=True).values(
        "name", "latitude", "longitude", "radius_meters"
    )

    return JsonResponse({
        "locations": [
            {
                "name": l["name"],
                "latitude": str(l["latitude"]),
                "longitude": str(l["longitude"]),
                "radius": l["radius_meters"],
            }
            for l in locations
        ]
    })
