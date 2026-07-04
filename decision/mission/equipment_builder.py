from decision.mission.night_mission import NightMission


class EquipmentBuilder:

    @staticmethod
    def build(context):

        equipment = []

        setup = context.equipment.setup

        #print("\n===== DEBUG SETUP =====")
        #print(setup)
        #print(vars(setup))

        if not setup:
            return equipment

        # Optique
        if getattr(setup, "optics", None):
            optics = setup.optics
            equipment.append(
                f"🔭 Objectif : {optics.manufacturer} {optics.model}"
            )

        elif getattr(setup, "telescope", None):
            equipment.append(
                f"🔭 Télescope : {setup.telescope.manufacturer} {setup.telescope.model}"
            )

        # Caméra
        if getattr(setup, "camera", None):
            equipment.append(
                f"📷 Caméra : {setup.camera.manufacturer} {setup.camera.model}"
            )

        # Filtre
        if getattr(setup, "filter", None):
            equipment.append(
                f"🔴 Filtre : {setup.filter.manufacturer} {setup.filter.name}"
            )

        return equipment

