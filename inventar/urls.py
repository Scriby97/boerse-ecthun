from django.urls import path

from . import views, views_kasse

urlpatterns = [
    path("", views.start, name="start"),
    path("artikel/", views.article_list, name="article_list"),
    path("artikel/neu/", views.article_create, name="article_create"),
    path("artikel/<int:pk>/", views.article_edit, name="article_edit"),
    path("kunden/", views.person_list, name="person_list"),
    path("kunden/neu/", views.person_edit, name="person_create"),
    path("kunden/<int:pk>/", views.person_detail, name="person_detail"),
    path("kunden/<int:pk>/bearbeiten/", views.person_edit, name="person_edit"),
    path("import/", views.import_upload, name="import_upload"),
    path("import/<str:token>/", views.import_preview, name="import_preview"),
    # Kasse
    path("kasse/", views_kasse.kasse, name="kasse"),
    path("kasse/nummer/", views_kasse.kasse_add_number, name="kasse_add_number"),
    path("kasse/artikel/<int:pk>/", views_kasse.kasse_add_article, name="kasse_add_article"),
    path("kasse/ohne-nummer/", views_kasse.kasse_add_other, name="kasse_add_other"),
    path("kasse/club/", views_kasse.kasse_add_club, name="kasse_add_club"),
    path("kasse/posten/<int:index>/preis/", views_kasse.kasse_price, name="kasse_price"),
    path("kasse/posten/<int:index>/entfernen/", views_kasse.kasse_remove, name="kasse_remove"),
    path("kasse/leeren/", views_kasse.kasse_clear, name="kasse_clear"),
    path("kasse/verkauft/", views_kasse.kasse_checkout, name="kasse_checkout"),
    # Verkäufe und Abrechnen
    path("verkauft/", views_kasse.sale_list, name="sale_list"),
    path("verkauf/<int:pk>/", views_kasse.sale_detail, name="sale_detail"),
    path("verkauf/<int:pk>/quittung.pdf", views_kasse.sale_receipt, name="sale_receipt"),
    path("verkauf/<int:pk>/stornieren/", views_kasse.sale_cancel, name="sale_cancel"),
    path("verkauf/<int:pk>/auszahlen/", views_kasse.sale_payout, name="sale_payout"),
    path("abrechnen/", views_kasse.payout_list, name="payout_list"),
    path("abrechnen/<int:pk>/", views_kasse.payout_person, name="payout_person"),
    path("club/", views_kasse.club_items, name="club_items"),
    path("club/<int:pk>/", views_kasse.club_item_edit, name="club_item_edit"),
]
