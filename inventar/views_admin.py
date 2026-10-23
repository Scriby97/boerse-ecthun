"""Clubabrechnung, Abrechnungen als PDF, Etiketten, Export und Einstellungen (inkl. Sicherungen)."""

from decimal import Decimal

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from . import backup, club_import, exports, sales
from .forms import ClubBackfillForm, ClubItemForm, ClubStatementForm, SettingsForm
from .models import AppSettings, ClubItem, ClubStatement, Payout, Person, SaleItem
from .pdf import club_statement_pdf, labels_pdf, payout_pdf
from .views import filter_articles

MAX_LABELS = 500


def _download(content: bytes, content_type: str, filename: str, inline: bool = False) -> HttpResponse:
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'{"inline" if inline else "attachment"}; filename="{filename}"'
    return response


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
        "statement_form": ClubStatementForm(initial={"end_date": sales.default_statement_end()}),
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
            f"{stats['created']} Clubverkäufe übernommen, davon {stats['settled']} schon abgerechnet"
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


@require_http_methods(["GET", "POST"])
def club_statement_new(request):
    form = ClubStatementForm(request.POST or request.GET or None)
    if not form.is_valid():
        messages.error(request, "Bitte ein Datum wählen.")
        return redirect("club_items")
    end_date = form.cleaned_data["end_date"]
    if request.method == "POST":
        try:
            statement = sales.create_club_statement(end_date)
        except sales.SaleError as error:
            messages.error(request, str(error))
            return redirect("club_items")
        messages.success(request, f"Clubabrechnung per {end_date:%d.%m.%Y} erstellt: CHF {statement.total:.2f}.")
        return redirect("club_items")
    items = sales.open_club_items(end_date)
    return render(request, "inventar/club_statement_new.html", {
        "end_date": end_date,
        "items": items,
        "total": sum((i.club_amount for i in items), Decimal("0")),
    })


def club_statement_pdf_view(request, pk):
    statement = get_object_or_404(ClubStatement, pk=pk)
    return _download(club_statement_pdf(statement), "application/pdf",
                     f"Clubabrechnung-{statement.end_date:%Y-%m-%d}.pdf")


@require_POST
def club_statement_delete(request, pk):
    statement = get_object_or_404(ClubStatement, pk=pk)
    sales.delete_club_statement(statement)
    messages.success(request, "Clubabrechnung gelöscht. Die Posten sind wieder offen.")
    return redirect("club_items")


# --- Abrechnung Besitzerin ------------------------------------------------------------------------


def payout_pdf_view(request, pk):
    payout = get_object_or_404(Payout.objects.select_related("person"), pk=pk)
    name = "".join(c for c in payout.person.name if c.isalnum() or c in " -").strip().replace(" ", "-")
    return _download(payout_pdf(payout), "application/pdf", f"Abrechnung-{name}-{payout.date:%Y-%m-%d}.pdf")


# --- Etiketten ------------------------------------------------------------------------------------


def labels(request, fmt):
    articles = list(filter_articles(request.GET)[0][:MAX_LABELS])
    if not articles:
        messages.warning(request, "Keine Artikel für Etiketten gefunden.")
        return redirect("article_list")
    if fmt == "xlsx":
        return _download(exports.dymo_labels(articles),
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "Etiketten.xlsx")
    return _download(labels_pdf(articles), "application/pdf", "Etiketten.pdf")


# --- Export ---------------------------------------------------------------------------------------


def export_page(request):
    return render(request, "inventar/export.html")


def export_xlsx(request):
    return _download(exports.full_export(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     f"Boerse-EC-Thun-{timezone.localdate():%Y-%m-%d}.xlsx")


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
