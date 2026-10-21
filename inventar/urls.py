from django.urls import path

from . import views

urlpatterns = [
    path("", views.start, name="start"),
    path("artikel/", views.article_list, name="article_list"),
    path("artikel/neu/", views.article_create, name="article_create"),
    path("artikel/<int:number>/", views.article_edit, name="article_edit"),
    path("kunden/", views.person_list, name="person_list"),
    path("kunden/neu/", views.person_edit, name="person_create"),
    path("kunden/<int:pk>/", views.person_detail, name="person_detail"),
    path("kunden/<int:pk>/bearbeiten/", views.person_edit, name="person_edit"),
    path("import/", views.import_upload, name="import_upload"),
    path("import/<str:token>/", views.import_preview, name="import_preview"),
]
