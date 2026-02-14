from django.shortcuts import render,redirect
from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import UserRegistrationForm
# Create your views here.
@login_required(login_url='/login/')
def home(request):
    return render(request, 'authentication/home.html')

def login_page(request):
    form = AuthenticationForm(request, data=request.POST or None)
    form.fields["username"].widget.attrs.update({"id": "username", "placeholder": "Enter username"})
    form.fields["password"].widget.attrs.update({"id": "password", "placeholder": "Enter password"})
    if request.method == "POST":
        if form.is_valid():
            login(request, form.get_user())
            return redirect('home')
        messages.error(request, "Invalid username or password.")

    return render(request, 'authentication/login.html', {"form": form})

# Define a view function for the registration page
def register_page(request):
    form = UserRegistrationForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.info(request, "Account created successfully!")
            return redirect('login_page')

    return render(request, 'authentication/register.html', {"form": form})


def guest_page(request):
    return render(request, 'authentication/guest.html')
