from django.core.mail import send_mail
from django.urls import reverse
from django.core.signing import dumps


def email_sender(req, email, user_id):
    signed_data = dumps({"user_id": user_id, "email": email})
    verification_link = f"https://telethu-frontend-secoder-e8a.app.secoder.net/users/verify/{signed_data}"
    print("verification link: ", verification_link)
    subject = "Identity Authorization"
    message = f"Welcome to Telethu! To authorize your your identity, please click the link: {verification_link}"
    from_email = "telethu@126.com"
    recipient_list = [email]
    print("ready to send mail! ")
    send_mail(subject, message, from_email, recipient_list, fail_silently=False)
