class SkyEngine:
    """
    Analyse uniquement le ciel.

    Responsabilités :
    - météo
    - Lune
    - humidité
    - vent
    - visibilité
    - qualité astronomique
    - fenêtres utiles

    Ne connaît pas :
    - portefeuille
    - ROI
    - setup
    - utilisateur
    - stratégie projet
    """

    def __init__(self, context=None):
        self.context = context or {}

    def sky_quality(self):
        """
        Retourne une qualité de ciel simple.
        Version initiale volontairement minimale.
        """
        return {
            "score": None,
            "reasons": [],
            "warnings": []
        }

    def moon_phase_name(self,illumination):

        if illumination < 5:
            return "🌑 Nouvelle lune"

        if illumination < 25:
            return "🌒 Premier croissant"

        if illumination < 45:
            return "🌓 Premier quartier"

        if illumination < 75:
            return "🌔 Gibbeuse"

        return "🌕 Pleine lune"