from django import forms

from .importer import SUFFIXES
from .models import Article, ClubItem, Payout, Person, Sale


class ArticleForm(forms.ModelForm):
    new_owner = forms.CharField(
        label="oder neue Besitzerin",
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "Nachname Vorname"}),
    )

    class Meta:
        model = Article
        fields = [
            "category",
            "number",
            "number_suffix",
            "owner",
            "description",
            "size",
            "price",
            "price_note",
            "owner_share",
            "intake_date",
            "notes",
        ]
        widgets = {
            "intake_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 2}),
            "size": forms.TextInput(attrs={"list": "sizes", "autocomplete": "off"}),
            "description": forms.TextInput(attrs={"autofocus": True}),
        }

    field_order = ["category", "number", "number_suffix", "owner", "new_owner", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owner"].required = False
        self.fields["owner"].empty_label = "– Besitzerin wählen –"

    def clean(self):
        data = super().clean()
        if not data.get("owner") and not data.get("new_owner"):
            self.add_error("owner", "Bitte eine Besitzerin wählen oder neu erfassen.")
        return data

    def save(self, commit=True):
        if not self.cleaned_data.get("owner"):
            self.instance.owner = Person.objects.create(name=self.cleaned_data["new_owner"].strip())
        return super().save(commit)


class PersonForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = ["name", "phone", "email", "twint", "address", "iban", "owner_share", "notes"]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }


class ImportUploadForm(forms.Form):
    file = forms.FileField(label="Inventarliste (Numbers, Excel oder CSV)")

    def clean_file(self):
        file = self.cleaned_data["file"]
        if not file.name.lower().endswith(SUFFIXES):
            raise forms.ValidationError("Bitte eine Numbers-, Excel- oder CSV-Datei wählen.")
        return file


class OtherItemForm(forms.Form):
    """Posten ohne Nummer: eigene Kleider, Evas Artikel, Diverses."""

    description = forms.CharField(label="Bezeichnung", max_length=300)
    size = forms.CharField(label="Grösse", max_length=60, required=False)
    price = forms.DecimalField(label="Preis (CHF)", min_value=0, max_digits=8, decimal_places=2)
    owner = forms.ModelChoiceField(
        label="Gehört", queryset=Person.objects.all(), required=False, empty_label="mir (eigener Artikel)"
    )


class ClubSaleForm(forms.Form):
    club_item = forms.ModelChoiceField(label="Clubartikel", queryset=ClubItem.objects.all(), empty_label=None)
    size = forms.CharField(label="Grösse", max_length=30, required=False)
    price = forms.DecimalField(label="Preis (CHF)", min_value=0, max_digits=8, decimal_places=2, required=False,
                               help_text="Leer = Preis aus der Liste")


class CheckoutForm(forms.Form):
    buyer = forms.ModelChoiceField(label="Käuferin", queryset=Person.objects.all(), required=False,
                                   empty_label="– ohne –")
    new_buyer = forms.CharField(label="oder neue Käuferin", max_length=200, required=False,
                                widget=forms.TextInput(attrs={"placeholder": "Nachname Vorname"}))
    payment = forms.ChoiceField(label="Bezahlt mit", choices=Sale.Payment.choices, initial=Sale.Payment.CASH,
                                widget=forms.RadioSelect)
    date = forms.DateField(label="Datum", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))


class PayoutForm(forms.Form):
    method = forms.ChoiceField(label="Art", choices=Payout.Method.choices)
    date = forms.DateField(label="Datum", required=False)


class ClubItemForm(forms.ModelForm):
    class Meta:
        model = ClubItem
        fields = ["name", "size", "customer_price", "club_price", "stock"]
