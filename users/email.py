from django.core.mail import send_mail


def email_sender(email):
    send_mail(
        "Identity Authorization",
        "Welcome to Telethu! To authorize your your identity, please click the link: ...",
        "telethu@126.com",
        [email],
        fail_silently=False,
    )