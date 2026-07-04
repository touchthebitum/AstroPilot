from decision.rule_contribution import RuleContribution
from decision.models.resolution_model import ResolutionModel
from decision.calculators.setup_calculator import SetupCalculator



class ResolutionRule:

    name = "Resolution"

    def evaluate(self, context, profile):

        capabilities = SetupCalculator.compute(context.equipment.setup)

        resolution = ResolutionModel.evaluate(
            object_type=context.sky.target.object_type,
            object_size_arcmin=context.sky.target.angular_size_arcmin,
            pixel_size = capabilities.sampling_arcsec_per_pixel,
        )
        pixels = resolution.pixels

        if resolution.score >= 8:
            reason = f"Résolution excellente (Objet projeté sur {pixels:.0f} px)"
        elif resolution.score >= 5:
            reason = f"Bonne résolution (Objet projeté sur {pixels:.0f} px)"
        elif resolution.score > 0:
            reason = f"Résolution correcte (Objet projeté sur {pixels:.0f} px)"
        else:
            reason = f"Résolution insuffisante (Objet projeté sur {pixels:.0f} px)"
        details = ""
        
        return RuleContribution(
            rule=self.name,
            score=resolution.score,
            confidence=1.0,
            reason=reason,
            details=details,
        )