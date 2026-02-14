from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm


User = get_user_model()


class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(
            attrs={"id": "email", "name": "email", "placeholder": "Enter email"}
        ),
    )
    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2", "role")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"id": "username", "name": "username", "placeholder": "Enter username"}
        )
        self.fields["password1"].widget.attrs.update(
            {"id": "password", "name": "password1", "placeholder": "Enter password"}
        )
        self.fields["password2"].widget.attrs.update(
            {
                "id": "confirm_password",
                "name": "password2",
                "placeholder": "Confirm password",
            }
        )
        self.fields["role"].widget.attrs.update(
            {"id": "role", "name": "role", "placeholder": "Select role"}
        )
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.role = self.cleaned_data["role"]
        if commit:
            user.save()
        return user