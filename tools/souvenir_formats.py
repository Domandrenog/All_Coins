#!/usr/bin/env python3
"""Formatos e lados suportados pelos Souvenirs."""

from __future__ import annotations


SUPPORTED_SOUVENIR_TYPES = frozenset({"pressed", "coin", "card", "other"})
SUPPORTED_SIDES = ("front", "back")
SIDE_FIELDS = {"front": "image_front", "back": "image_back"}
SIDE_FOLDERS = {"front": "frente", "back": "tras"}
SIDE_LINK_FIELDS = {"front": "frente", "back": "tras"}


def normalize_crop_format(
    record_type: object,
    crop_format: object,
    display_shape: object = "",
) -> str:
    normalized_type = str(record_type or "pressed")
    requested = str(crop_format or "")
    shape = str(display_shape or "")
    if normalized_type not in SUPPORTED_SOUVENIR_TYPES:
        raise ValueError(f"Tipo de Souvenir não suportado: {normalized_type}")
    if normalized_type == "coin" or shape in {"circle", "square"}:
        return "square"
    if requested in {"portrait", "landscape"}:
        return requested
    return "landscape"


def crop_size(
    record_type: object,
    crop_format: object,
    display_shape: object = "",
) -> tuple[int, int]:
    normalized_type = str(record_type or "pressed")
    normalized_format = normalize_crop_format(normalized_type, crop_format, display_shape)
    if normalized_format == "square":
        return 140, 140
    if normalized_type == "pressed":
        return (80, 140) if normalized_format == "portrait" else (200, 115)
    return (140, 200) if normalized_format == "portrait" else (200, 140)


def display_orientation_for_crop(
    record_type: object,
    crop_format: object,
    display_shape: object = "",
) -> str:
    normalized = normalize_crop_format(record_type, crop_format, display_shape)
    return "auto" if normalized == "square" else normalized
