from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count
from datetime import datetime, timedelta
from geopy.distance import geodesic
from .models import User, Course, QRCode, Attendance, OrganizationLocation

from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth import get_user_model
from django.contrib.auth import login, logout


User= get_user_model()

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def studentProfile(request):
    user= request.user
    return Response(
        {"id":user.id, "username":user.username, "course": user.course}
        ,status=status.HTTP_200_OK
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def signupStudent(request):
    serializer= SignupSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(["POST"])
@permission_classes([AllowAny])
def Login(request):
    serializer= LoginSerializer(data=request.data)
    if serializer.is_valid():
        user= serializer.validated_data["user"]
        login(request, user)
        return Response(
            {"id":user.id,  "username":user.username, "user_type":user.user_type}, status=status.HTTP_200_OK
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@login_required
def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect("login") 





def verify_location(latitude, longitude):
    """Verify if user is within organization premises"""
    locations = OrganizationLocation.objects.filter(is_active=True)
    
    for location in locations:
        org_coords = (location.latitude, location.longitude)
        user_coords = (latitude, longitude)
        distance = geodesic(org_coords, user_coords).meters
        
        if distance <= location.radius_meters:
            return True
    
    return False

@login_required
def scan_qr(request):
    """Main QR scanning page"""
    courses = Course.objects.filter(is_active=True)
    
    if request.method == 'POST':
        qr_code_value = request.POST.get('qr_code')
        course_id = request.POST.get('course')
        latitude = float(request.POST.get('latitude', 0))
        longitude = float(request.POST.get('longitude', 0))
        
        # Verify location
        if not verify_location(latitude, longitude):
            messages.error(request, 'You must be within the organization premises to sign in.')
            return redirect('scan_qr')
        
        # Verify QR code
        try:
            qr_code = QRCode.objects.get(code=qr_code_value, is_active=True)
        except QRCode.DoesNotExist:
            messages.error(request, 'Invalid QR code.')
            return redirect('scan_qr')
        
        # Get course
        course = get_object_or_404(Course, id=course_id)
        
        # Check if already signed in today
        today = timezone.now().date()
        existing_attendance = Attendance.objects.filter(
            user=request.user,
            course=course,
            check_in_time__date=today
        ).first()
        
        if existing_attendance:
            messages.warning(request, f'You have already signed in for {course.name} today.')
            return redirect('scan_qr')
        
        # Create attendance record
        Attendance.objects.create(
            user=request.user,
            course=course,
            latitude=latitude,
            longitude=longitude,
            qr_code=qr_code,
            is_valid=True
        )
        
        messages.success(request, f'Successfully signed in for {course.name}!')
        return redirect('attendance_success')
    
    return render(request, 'attendance/scan.html', {'courses': courses})

@login_required
def attendance_success(request):
    """Success page after signing in"""
    return render(request, 'attendance/success.html')



from django.db.models import Count
import json
from django.core.paginator import Paginator

@login_required
def admin_dashboard(request):
    if request.user.user_type != 'admin':
        messages.error(request, 'Access denied.')
        return redirect('scan_qr')

    # ----------------------------
    # Get Filter Parameters
    # ----------------------------
    date_filter = request.GET.get('date')
    course_filter = request.GET.get('course')
    user_type_filter = request.GET.get('user_type')
    location_filter = request.GET.get('location')

    # Convert date string to proper date object
    if date_filter:
        try:
            date_filter = datetime.strptime(date_filter, "%Y-%m-%d").date()
        except ValueError:
            date_filter = timezone.now().date()
    else:
        date_filter = timezone.now().date()

    # ----------------------------
    # Base Queryset
    # ----------------------------
    attendances = Attendance.objects.select_related(
        'user', 'course', 'qr_code'
    )

    # ----------------------------
    # Apply Filters
    # ----------------------------
    # Base queryset
    attendances = Attendance.objects.select_related('user', 'course', 'qr_code')

    # Apply date filter
    attendances = attendances.filter(check_in_time__date=date_filter)

    # Apply course filter
    if course_filter:
        attendances = attendances.filter(course_id=course_filter)

    # Apply user type filter
    if user_type_filter:
        attendances = attendances.filter(user__user_type=user_type_filter)

    # Apply location filter (fixed)
    if location_filter:
        attendances = attendances.filter(qr_code__location__id=location_filter)

    location_stats = attendances.values('qr_code__location__name').annotate(
        total=Count('id')
    )

    location_labels = [l['qr_code__location__name'] for l in location_stats]
    location_totals = [l['total'] for l in location_stats]



    print("Location filter:", location_filter)
    print("Total attendances before location filter:", attendances.count())

    # ----------------------------
    # Statistics (BASED ON FILTERS)
    # ----------------------------
    total_count = attendances.count()
    students_count = attendances.filter(user__user_type='student').count()
    tutors_count = attendances.filter(user__user_type='tutor').count()

    # ----------------------------
    # Extra: Course Breakdown (For Future Charts)
    # ----------------------------
    course_stats = attendances.values('course__name').annotate(
        total=Count('id')
    )

    course_labels = [c['course__name'] for c in course_stats]
    course_totals = [c['total'] for c in course_stats]

    # ----------------------------
    # Fetch Dropdown Data
    # ----------------------------
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
        monthly_attendance.values('course__name')
        .annotate(total=Count('id'))
        .order_by('-total')
        .first()
    )


    #Pagination
    paginator = Paginator(attendances, 15)
    page_number = request.GET.get('page')
    attendances = paginator.get_page(page_number)

    context = {
        'attendances': attendances,
        'total_today': total_count,
        'students_today': students_count,
        'tutors_today': tutors_count,
        'courses': courses,
        'locations': locations,
        'date_filter': date_filter,
        'course_filter': course_filter,
        'user_type_filter': user_type_filter,
        'location_filter': location_filter,
        'course_stats': course_stats,  # For charts later
        'course_labels': json.dumps(course_labels),
        'course_totals': json.dumps(course_totals),
        'location_labels': json.dumps(location_labels),
        'location_totals': json.dumps(location_totals),
        'monthly_total': monthly_total,
        'top_course': top_course,
    }

    return render(request, 'attendance/admin_dashboard.html', context)












from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Course, OrganizationLocation


def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if request.user.user_type != 'admin':
            messages.error(request, "Access denied.")
            return redirect('scan_qr')
        return view_func(request, *args, **kwargs)
    return login_required(wrapper)


@admin_required
def add_course(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        code = request.POST.get('code')
        description = request.POST.get('description')

        if Course.objects.filter(code=code).exists():
            messages.error(request, "Course code already exists.")
            return redirect('add_course')

        Course.objects.create(
            name=name,
            code=code,
            description=description
        )

        messages.success(request, "Course added successfully.")
        return redirect('add_course')

    courses = Course.objects.all()
    return render(request, 'attendance/add_course.html', {'courses': courses})


@admin_required
def add_location(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')
        radius = request.POST.get('radius')

        OrganizationLocation.objects.create(
            name=name,
            latitude=latitude,
            longitude=longitude,
            radius_meters=radius
        )

        messages.success(request, "Location added successfully.")
        return redirect('add_location')

    locations = OrganizationLocation.objects.all()
    return render(request, 'attendance/add_location.html', {'locations': locations})







from django.contrib.auth import login
from django.shortcuts import redirect


@login_required
def post_login_redirect(request):
    if request.user.user_type == 'admin':
        return redirect('admin_dashboard')
    return redirect('scan_qr')






from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import StudentRegistrationForm
from django.contrib.auth import login

def student_register(request):
    if request.method == 'POST':
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Account created successfully!")
            return redirect('login')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = StudentRegistrationForm()
    return render(request, 'attendance/student_register.html', {'form': form})







