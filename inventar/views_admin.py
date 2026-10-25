"""Clubabrechnung, Abrechnungen als PDF, Etiketten, Export und Einstellungen (inkl. Sicherungen)."""

from decimal import Decimal

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from . import backup, club_import, exports, numbers_export, sales
from .delivery import NUMBERS, PDF, XLSX, deliver
from .forms import ClubBackfillForm, ClubItemForm, SettingsForm
from .models import AppSettings, ClubItem, ClubStatement, Payout, Person, SaleItem
from .pdf import club_receipt_pdf, club_statement_pdf, guide_pdf, labels_pdf, payout_pdf
from .views import filter_articles

MAX_LABELS = 500


# --- Club EC Thun ---------------------------------------------------------------------------------


@require_http_methods(["GET", "POST"])
def club_items(request):
    form = ClubItemForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        item = form.save()
        messages.success(request, f"{item} hinzugefügt.")
        return redirect("club_items")
    open_items = sales.open_club_items()
    return render(request, "inventar/club_items.html", {
        "items": ClubItem.objects.all(),
        "form": form,
        "open_items": open_items,
        "open_total": sum((i.club_amount for i in open_items), Decimal("0")),
        "statements": ClubStatement.objects.all(),
        "backfill_form": ClubBackfillForm(initial={"date": timezone.localdate()}),
        "sold_items": SaleItem.objects.filter(kind=SaleItem.Kind.CLUB, sale__cancelled_at__isnull=True)
        .select_related("sale", "sale__buyer", "club_statement")
        .order_by("-sale__date", "-pk"),
    })


@require_POST
def club_import_csv(request):
    upload = request.FILES.get("file")
    if not upload:
        messages.error(request, "Bitte eine CSV-Datei wählen.")
        return redirect("club_items")
    try:
        content = upload.read().decode("utf-8-sig")
        stats = club_import.import_rows(club_import.parse(content))
    except UnicodeDecodeError:
        messages.error(request, "Die Datei ist nicht als UTF-8 gespeichert.")
    except club_import.ClubImportFehler as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            f"{stats['created']} Clubverkäufe übernommen, davon {stats['settled']} schon beglichen"
            + (f"; {stats['skipped']} waren schon da" if stats["skipped"] else "") + ".",
        )
    return redirect("club_items")


@require_POST
def club_backfill(request):
    form = ClubBackfillForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Bitte Datum und Clubartikel angeben.")
        return redirect("club_items")
    data = form.cleaned_data
    item: ClubItem = data["club_item"]
    buyer = None
    if data["buyer"].strip():
        name = " ".join(data["buyer"].split())
        buyer = Person.objects.filter(name__iexact=name).first() or Person.objects.create(name=name)
    club_amount = data["club_amount"] if data["club_amount"] is not None else item.club_price
    entry = {
        "kind": SaleItem.Kind.CLUB,
        "club_item_id": item.pk,
        "description": item.name,
        "size": data["size"] or item.size,
        "price": str(item.customer_price),
        "club_amount": str(club_amount),
    }
    sale = sales.create_sale([entry], buyer=buyer, date=data["date"], adjust_stock=False)
    messages.success(request, f"Nachgetragen: {item.name} {entry['size']} vom {data['date']:%d.%m.%Y} (Quittung Nr. {sale.number}).")
    return redirect("club_items")


def club_receipt_pdf_view(request):
    """Laufende Clubquittung (noch nicht beglichen) als PDF – jederzeit zum Ansehen oder Drucken."""
    items = list(sales.open_club_items())
    if not items:
        messages.warning(request, "Auf der laufenden Clubquittung steht noch nichts.")
        return redirect("club_items")
    today = timezone.localdate()
    pdf = club_receipt_pdf(items, today, sum((i.club_amount for i in items), Decimal("0")))
    return deliver(request, pdf, f"Clubquittung-Stand-{today:%Y-%m-%d}.pdf", PDF)


@require_POST
def club_settle(request):
    """«Begleichen»: laufende Quittung abschliessen; die nächsten Clubverkäufe kommen auf eine neue."""
    try:
        statement = sales.create_club_statement(timezone.localdate())
    except sales.SaleError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Clubquittung über CHF {statement.total:.2f} beglichen. Eine neue Quittung ist gestartet.")
    return redirect("club_items")


def club_statement_pdf_view(request, pk):
    statement = get_object_or_404(ClubStatement, pk=pk)
    return deliver(request, club_statement_pdf(statement),
                   f"Clubquittung-beglichen-{statement.end_date:%Y-%m-%d}.pdf", PDF)


@require_POST
def club_statement_delete(request, pk):
    statement = get_object_or_404(ClubStatement, pk=pk)
    sales.delete_club_statement(statement)
    messages.success(request, "Die Quittung ist wieder offen; ihre Posten stehen auf der laufenden Clubquittung.")
    return redirect("club_items")


# --- Abrechnung Besitzerin ------------------------------------------------------------------------


def payout_pdf_view(request, pk):
    payout = get_object_or_404(Payout.objects.select_related("person"), pk=pk)
    name = "".join(c for c in payout.person.name if c.isalnum() or c in " -").strip().replace(" ", "-")
    return deliver(request, payout_pdf(payout), f"Abrechnung-{name}-{payout.date:%Y-%m-%d}.pdf", PDF)


# --- Etiketten ------------------------------------------------------------------------------------


def labels(request, fmt):
    articles = list(filter_articles(request.GET)[0][:MAX_LABELS])
    if not articles:
        messages.warning(request, "Keine Artikel für Etiketten gefunden.")
        return redirect("article_list")
    if fmt == "xlsx":
        return deliver(request, exports.dymo_labels(articles), "Etiketten.xlsx", XLSX)
    return deliver(request, labels_pdf(articles), "Etiketten.pdf", PDF)


# --- Export ---------------------------------------------------------------------------------------


def export_page(request):
    return render(request, "inventar/export.html")


def export_xlsx(request):
    return deliver(request, exports.full_export(), f"Boerse-EC-Thun-{timezone.localdate():%Y-%m-%d}.xlsx", XLSX)


def export_numbers(request):
    return deliver(request, numbers_export.build(), f"Boerse-EC-Thun-{timezone.localdate():%Y-%m-%d}.numbers", NUMBERS)


# --- Anleitung ------------------------------------------------------------------------------------


def guide(request):
    return render(request, "inventar/guide.html")


def guide_pdf_view(request):
    content = guide_pdf(render_to_string("inventar/_guide_content.html"))
    return deliver(request, content, "Anleitung-Boerse-EC-Thun.pdf", PDF)


# --- Einstellungen und Sicherungen ----------------------------------------------------------------


@require_http_methods(["GET", "POST"])
def settings_page(request):
    form = SettingsForm(request.POST or None, instance=AppSettings.load())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen gespeichert.")
        return redirect("settings")
    return render(request, "inventar/settings.html", {
        "form": form,
        "backups": backup.list_backups()[:30],
        "icloud": backup.icloud_dir(),
        "last_backup": backup.last_backup_time(),
    })


@require_POST
def backup_now(request):
    target = backup.backup_database("manuell")
    messages.success(request, f"Sicherung angelegt: {target.name}")
    return redirect("settings")


@require_POST
def backup_restore(request):
    name = request.POST.get("name", "")
    try:
        safety = backup.restore_backup(name)
    except FileNotFoundError:
        messages.error(request, "Diese Sicherung gibt es nicht.")
    else:
        messages.success(request, f"Sicherung {name} zurückgeholt. Der Stand davor ist gesichert als {safety.name}.")
    return redirect("settings")
