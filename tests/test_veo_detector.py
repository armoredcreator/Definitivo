from __future__ import annotations

from unittest.mock import patch

import cv2
import numpy as np

from ArmoredStudio.analysis import veo_detector
from ArmoredStudio import unified


def _result(found: bool, *, score: float, location=(1, 2, 3, 4)):
    return {
        "found": found,
        "best_score": score,
        "scores": [(0, score)],
        "locations": [(0, location)],
        "frames_analyzed": 1,
    }


def test_veo2_positive_adds_detection_without_overriding_veo1():
    veo1 = _result(False, score=0.31)
    veo2 = _result(True, score=0.96, location=(500, 800, 41, 20))
    with (
        patch.object(veo_detector, "detect_veo1_fast", return_value=veo1),
        patch.object(veo_detector, "detect_veo2", return_value=veo2),
    ):
        combined = veo_detector.detect_fast("input.mp4")

    assert combined["found"] is True
    assert combined["detector"] == "veo2"
    assert combined["locations"] == veo2["locations"]
    assert combined["detectors"]["veo1"] is veo1
    assert combined["detectors"]["veo2"] is veo2


def test_veo1_positive_is_preserved_even_if_veo2_is_negative():
    veo1 = _result(True, score=0.88, location=(610, 900, 41, 20))
    veo2 = _result(False, score=0.42)
    with (
        patch.object(veo_detector, "detect_veo1_fast", return_value=veo1),
        patch.object(veo_detector, "detect_veo2", return_value=veo2),
    ):
        combined = veo_detector.detect_fast("input.mp4")

    assert combined["found"] is True
    assert combined["detector"] == "veo1"
    assert combined["locations"] == veo1["locations"]


def test_veo2_matches_watermark_under_alternate_image_preprocessing():
    template = veo_detector.load_template_veo2()
    height, width = 1920, 1080
    frame = np.tile(np.linspace(40, 180, width, dtype=np.uint8), (height, 1))
    x, y = 950, 1830
    patch = frame[y : y + template.shape[0], x : x + template.shape[1]].astype(np.int16)
    frame[y : y + template.shape[0], x : x + template.shape[1]] = np.clip(
        patch + template.astype(np.int16),
        0,
        255,
    ).astype(np.uint8)
    color_frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

    score, location, _mode = veo_detector.score_frame_veo2(
        color_frame,
        template,
    )

    assert score >= veo_detector.VEO2_SINGLE_FRAME_THRESHOLD
    assert location[:2] == (x, y)


def test_studio_runs_visual_detectors_without_speech_audio_classification(tmp_path):
    calls = []

    source = tmp_path / "input.mp4"
    source.write_bytes(b"fixture")
    with (
        patch.object(
            unified,
            "obter_informacoes_video",
            side_effect=lambda _path: calls.append("video") or {"sucesso": True},
        ),
        patch.object(
            unified,
            "analisar_bordas_video",
            side_effect=lambda _path: calls.append("blackbar") or {},
        ),
        patch.object(
            unified,
            "analisar_banner",
            side_effect=lambda _path: calls.append("banner") or {"banner_detectado": False},
        ),
        patch.object(
            unified,
            "detectar_veo",
            side_effect=lambda _path: calls.append("veo") or {"found": False},
        ),
        patch.object(
            unified,
            "detectar_gemini",
            side_effect=lambda _path: calls.append("gemini") or {"gemini": False},
        ),
        patch.object(unified, "criar_plano_exportacao", return_value={}),
        patch.object(
            unified,
            "validar_plano_exportacao",
            return_value={"valido": True, "erros": []},
        ),
    ):
        unified.AnalysisEngine().analyze(source)

    assert calls == ["video", "blackbar", "banner", "veo", "gemini"]
