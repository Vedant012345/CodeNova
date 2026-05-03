"""
CodeNova Forms — v8
Changes:
  - RegistrationForm: added course dropdown (student picks at registration)
  - AIQuizGenerateForm: n now accepts 5-50
  - CourseSelectionForm: unchanged (still used for old students without reg course)
"""
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from .models import CustomUser, Submission, Course


# ─── Registration ─────────────────────────────────────────────────────────────

class RegistrationForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"placeholder": "Create a password (min 8 chars)", "autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={"placeholder": "Repeat password", "autocomplete": "new-password"}),
    )
    # v8: Course selection at registration (students only)
    # Non-student roles ignore this field.
    # WARNING: queryset filtered to is_active=True. If no active courses exist,
    # this field will be empty and required=False so students can still register.
    course = forms.ModelChoiceField(
        queryset=Course.objects.filter(is_active=True).order_by("order", "title"),
        required=False,
        empty_label="— Select your course (optional) —",
        label="Course",
        help_text="Choose the course you're enrolling in. Required for students.",
        widget=forms.Select(attrs={"class": "course-select-dropdown"}),
    )

    class Meta:
        model  = CustomUser
        fields = ("username", "email", "first_name", "last_name", "role")
        widgets = {
            "username":   forms.TextInput(attrs={"placeholder": "Choose a username", "autocomplete": "username"}),
            "email":      forms.EmailInput(attrs={"placeholder": "your@email.com"}),
            "first_name": forms.TextInput(attrs={"placeholder": "First name"}),
            "last_name":  forms.TextInput(attrs={"placeholder": "Last name"}),
            "role":       forms.Select(),
        }

    def clean_password2(self):
        p1 = self.cleaned_data.get("password1")
        p2 = self.cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            raise ValidationError("Passwords do not match.")
        if p1 and len(p1) < 8:
            raise ValidationError("Password must be at least 8 characters.")
        return p2

    def clean(self):
        cleaned = super().clean()
        role   = cleaned.get("role")
        course = cleaned.get("course")
        # Students should select a course, but we make it a soft warning (not hard error)
        # to avoid blocking registration if no courses exist yet.
        # The host can assign courses manually after approval.
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        user.is_approved = False
        # Store the selected course on the user model
        course = self.cleaned_data.get("course")
        if course and user.role == CustomUser.ROLE_STUDENT:
            user.registration_course = course
            # Mark course_selection_done=True so on approval → straight to dashboard
            # WARNING: enrolled_courses M2M is set in host_user_action on approval,
            # not here, because the user object must be saved first before M2M.
            user.course_selection_done = True
        if commit:
            user.save()
        return user


# ─── Login ───────────────────────────────────────────────────────────────────

class LoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={"placeholder": "Username", "autocomplete": "username"})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"placeholder": "Password", "autocomplete": "current-password"})
    )


# ─── Profile ─────────────────────────────────────────────────────────────────

class ProfileForm(forms.ModelForm):
    class Meta:
        model  = CustomUser
        fields = ("first_name", "last_name", "email", "bio", "avatar")
        widgets = {
            "first_name": forms.TextInput(attrs={"placeholder": "First name"}),
            "last_name":  forms.TextInput(attrs={"placeholder": "Last name"}),
            "email":      forms.EmailInput(attrs={"placeholder": "your@email.com"}),
            "bio":        forms.Textarea(attrs={"rows": 3}),
        }


# ─── Submission ───────────────────────────────────────────────────────────────

class SubmissionForm(forms.ModelForm):
    class Meta:
        model  = Submission
        fields = ("file", "text")
        widgets = {
            "text": forms.Textarea(attrs={"rows": 4, "placeholder": "Optional notes..."}),
        }


# ─── AI Quiz Generator Form ───────────────────────────────────────────────────

# v8: expanded range from 5-10 to 5-50
QUESTION_COUNT_CHOICES = [
    (5,  "5 Questions"),
    (10, "10 Questions"),
    (15, "15 Questions"),
    (20, "20 Questions"),
    (25, "25 Questions"),
    (30, "30 Questions"),
    (40, "40 Questions"),
    (50, "50 Questions"),
]

class AIQuizGenerateForm(forms.Form):
    topic   = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Python decorators, World War II..."})
    )
    subject = forms.CharField(
        max_length=100, required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Computer Science (optional)"})
    )
    # v8: 5 to 50 questions
    num_questions = forms.ChoiceField(
        choices=QUESTION_COUNT_CHOICES,
        initial=10,
        label="Number of Questions (5–50)"
    )
    duration = forms.IntegerField(
        min_value=5, max_value=180, initial=20,
        widget=forms.NumberInput(attrs={"placeholder": "20"}),
        label="Time Limit (minutes)"
    )

    def clean_num_questions(self):
        n = int(self.cleaned_data["num_questions"])
        if not (5 <= n <= 50):
            raise ValidationError("Number of questions must be between 5 and 50.")
        return n


# ─── Course Selection Form (for legacy students without registration_course) ──

class CourseSelectionForm(forms.Form):
    """
    Used only for students who registered BEFORE v8 (no registration_course set).
    Students who registered with v8 form skip this page entirely.
    """
    courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.filter(is_active=True).order_by("order", "title"),
        widget=forms.CheckboxSelectMultiple,
        label="Select Your Course(s)",
        help_text="Choose one or more courses.",
        error_messages={"required": "Please select at least one course."},
    )

    def clean_courses(self):
        courses = self.cleaned_data.get("courses")
        if not courses:
            raise ValidationError("Please select at least one course.")
        inactive = [c.title for c in courses if not c.is_active]
        if inactive:
            raise ValidationError(f"Courses no longer available: {', '.join(inactive)}")
        return courses
