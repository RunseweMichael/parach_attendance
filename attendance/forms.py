# forms.py
from django import forms
from .models import User
from django.contrib.auth.forms import UserCreationForm

class StudentRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    phone_number = forms.CharField(required=True)

    user_type = forms.ChoiceField(
        choices=(
            ("student", "Student"),
            ("tutor", "Tutor"),
        ),
        widget=forms.Select(),
        required=True
    )

    class Meta:
        model = User
        fields = [
            'username',
            'email',
            'phone_number',
            'user_type',   # 👈 ADD THIS
            'password1',
            'password2'
        ]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.user_type = self.cleaned_data["user_type"]  # 👈 use selected role
        if commit:
            user.save()
        return user
