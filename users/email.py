from django.core.mail import send_mail
from django.urls import reverse
from django.core.signing import dumps
import random

def email_sender(email):
    # verification_link = f"https://telethu-frontend-secoder-e8a.app.secoder.net/users/verify/{signed_data}"
    # print("verification link: ", verification_link)
    random_six_digit_number = random.randint(100000, 999999)
    subject = "Identity Authorization"
    message = f"Welcome to Telethu! To authorize your your identity, please type in the following verification code: {random_six_digit_number}"
    from_email = "telethu@126.com"
    recipient_list = [email]
    print("ready to send mail! ")
    try:
        send_mail(subject, message, from_email, recipient_list, fail_silently=False)
        return random_six_digit_number
    except:
        return 0
