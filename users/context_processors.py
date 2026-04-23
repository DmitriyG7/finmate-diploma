from django.conf import settings

def default_avatar(request):
    return {'DEFAULT_AVATAR': settings.DEFAULT_AVATAR}