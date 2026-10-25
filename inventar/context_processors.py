from boerse import __version__


def app_version(request):
    return {"app_version": __version__}


def update_available(request):
    """Neue Version, falls die Prüfung eine gefunden hat – für den Hinweis in der Navigation."""
    from .updates import available

    return {"update_available": available()}


def open_statements(request):
    """Anzahl offener Tagesabrechnungen für das Zeichen bei «Abrechnen» in der Navigation."""
    from .sales import daily_groups

    return {"open_statements": len(daily_groups())}
