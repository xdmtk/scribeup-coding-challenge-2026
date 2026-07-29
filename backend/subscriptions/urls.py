from django.urls import path

from . import views

urlpatterns = [
    path("users/", views.list_users),
    path("users/<int:user_id>/transactions/", views.list_user_transactions),
    path("users/<int:user_id>/merchant-groups/", views.list_user_merchant_groups),
    # TODO (candidate): add the subscription detection endpoint here.
]
