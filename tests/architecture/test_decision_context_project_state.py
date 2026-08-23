import astro_score


def test_decision_context_uses_selected_project_state(
    monkeypatch,
):
    monkeypatch.setattr(
        astro_score,
        "project_state",
        lambda name: {
            "hours": 3.0,
            "target_hours": 20.0,
            "remaining": 17.0,
            "progress": 15.0,
        },
    )

    monkeypatch.setattr(
        astro_score,
        "project_priority",
        lambda name: 27.2,
    )

    monkeypatch.setattr(
        astro_score,
        "get_projects",
        lambda: {
            "M31": {},
            "IC1396": {},
        },
    )

    context = astro_score.build_decision_context(
        obj_name="M31",
        best={
            "clouds": 20,
            "humidity": 60,
            "wind": 5,
            "seeing": 1.5,
            "visibility": 10000,
            "sqm": 21.0,
            "moon_sep": 120,
            "target_altitude": 70,
        },
        selected_setup_profile={
            "camera_manufacturer": "ZWO",
            "camera_model": "ASI183MM",
            "pixel_size_um": 2.4,
            "sensor_width_px": 5496,
            "sensor_height_px": 3672,
            "monochrome": True,
            "optics_manufacturer": "Samyang",
            "optics_model": "135mm",
            "focal_length_mm": 135,
            "aperture_mm": 48,
            "f_ratio": 2.8,
        },
        profile={
            "preferences": {
                "bortle": 3,
                "productive_hours_per_night": 5.5,
            },
            "sessions": [
                {
                    "date": "2026-08-16",
                    "object": "M31",
                    "hours": 2.0,
                },
                {
                    "date": "2026-08-16",
                    "object": "Rosette",
                    "hours": 1.0,
                },
                {
                    "date": "2026-08-17",
                    "object": "IC1396",
                    "hours": 5.0,
                },
            ],
        },
        illumination=0.3,
        lat=46.7508,
        lon=6.5495,
    )

    assert context.portfolio.active_projects == 2
    assert context.portfolio.total_remaining_hours == 17.0
    assert context.portfolio.highest_priority == 27.2
    assert context.portfolio.average_progress == 15.0
    assert context.portfolio.productive_hours_per_night == 4.0

def test_decision_context_session_times_are_timezone_aware():
    context = astro_score.build_decision_context(
        obj_name="M31",
        best={
            "clouds": 20,
            "humidity": 60,
            "wind": 5,
            "seeing": 1.5,
            "visibility": 10000,
            "sqm": 21.0,
            "moon_sep": 120,
            "target_altitude": 70,
        },
        selected_setup_profile={
            "camera_manufacturer": "ZWO",
            "camera_model": "ASI183MM",
            "pixel_size_um": 2.4,
            "sensor_width_px": 5496,
            "sensor_height_px": 3672,
            "monochrome": True,
            "optics_manufacturer": "Samyang",
            "optics_model": "135mm",
            "focal_length_mm": 135,
            "aperture_mm": 48,
            "f_ratio": 2.8,
        },
        profile={
            "preferences": {
                "bortle": 3,
            }
        },
        illumination=0.3,
        lat=46.7508,
        lon=6.5495,
    )

    assert context.portfolio.productive_hours_per_night == 4.0
    assert context.session.start_time.tzinfo is not None
    assert context.session.end_time.tzinfo is not None
    assert (
        context.session.start_time.tzinfo.key
        == astro_score.TIMEZONE
    )
    assert (
        context.session.end_time.tzinfo.key
        == astro_score.TIMEZONE
    )
