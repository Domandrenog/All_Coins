#!/usr/bin/env python3
"""Formatos de imagem suportados pelos Souvenirs."""

from __future__ import annotations


SUPPORTED_SOUVENIR_TYPES = frozenset({"pressed", "other"})
SOUVENIR_CROP_SIZES = {
    "pressed": {
        "landscape": (200, 115),
        "portrait": (80, 140),
    },
    "other": {
        "landscape": (200, 140),
        "portrait": (140, 200),
    },
}


def crop_size(record_type: object, orientation: object) -> tuple[int, int]:
    normalized_type = str(record_type or "pressed")
    normalized_orientation = str(orientation or "landscape")
    if normalized_type not in SUPPORTED_SOUVENIR_TYPES:
        raise ValueError(f"Tipo de Souvenir não suportado: {normalized_type}")
    sizes = SOUVENIR_CROP_SIZES[normalized_type]
    if normalized_orientation not in sizes:
        raise ValueError(f"Orientação inválida: {normalized_orientation}")
    return sizes[normalized_orientation]
