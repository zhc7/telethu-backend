from django.core.mail import send_mail
#import os

#os.environ.setdefault("DJANGO_SETTINGS_MODULE", "telethu.settings")

def email_sender(email):
    print("welcome to email sender! ")
    print("email is: ", email)
    subject = "Identity Authorization"
    message = "Welcome to Telethu! To authorize your your identity, please click the link: ..."
    from_email = "telethu@126.com"
    recipient_list = [email]
    send_mail(subject, message, from_email, recipient_list, fail_silently=False)
