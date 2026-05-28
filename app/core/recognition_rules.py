from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import json
import os
import re

from PIL import Image, ImageOps
import pytesseract

from .ocr import DEFAULT_TIMEOUT
from .schemas import ElementArtifact


@dataclass
class RuleApplication:
    profile_ids: List[str]
    applied_rule_ids: List[str]
    suppressed_element_ids: List[str]


def apply_document_recognition_rules(
    *,
    doc_id: str,
    source_filename: str,
    page_no: int,
    image_path: Path,
    image_width: int,
    image_height: int,
    page_elements: List[ElementArtifact],
    ocr_elements: List[ElementArtifact],
) -> RuleApplication:
    """Apply deterministic external recognition rules to OCR artifacts."""
    profiles = _matching_profiles(_load_rule_profiles(), doc_id, source_filename, page_elements, ocr_elements)
    applied: List[str] = []
    suppressed: List[str] = []
    for profile in profiles:
        if profile.get("compact_cjk_spacing"):
            applied.extend(_compact_cjk_text(ocr_elements, profile["id"]))
        applied.extend(
            _apply_text_rewrites(
                ocr_elements,
                profile,
                image_width=image_width,
                image_height=image_height,
            )
        )
        applied.extend(
            _apply_region_ocr_rewrites(
                page_no=page_no,
                image_path=image_path,
                image_width=image_width,
                image_height=image_height,
                ocr_elements=ocr_elements,
                profile=profile,
            )
        )
        applied.extend(
            _apply_page_number_rules(
                page_no=page_no,
                image_width=image_width,
                image_height=image_height,
                ocr_elements=ocr_elements,
                profile=profile,
            )
        )
        rule_ids, element_ids = _apply_suppressions(
            page_no=page_no,
            image_width=image_width,
            image_height=image_height,
            ocr_elements=ocr_elements,
            profile=profile,
        )
        applied.extend(rule_ids)
        suppressed.extend(element_ids)
    return RuleApplication(
        profile_ids=[profile["id"] for profile in profiles],
        applied_rule_ids=_dedupe(applied),
        suppressed_element_ids=_dedupe(suppressed),
    )


def is_ignored_by_recognition_rule(element: ElementArtifact) -> bool:
    return element.quality.get("status") == "ignored" or "suppressed_by_external_rule" in element.quality.get("signals", [])


def is_excluded_from_primary_text(element: ElementArtifact) -> bool:
    signals = element.quality.get("signals", [])
    return is_ignored_by_recognition_rule(element) or "page_number" in signals


def _load_rule_profiles() -> List[Dict[str, Any]]:
    configured = os.getenv("DOCQA_RECOGNITION_RULES_PATH")
    if configured:
        path = Path(configured)
    else:
        path = Path(__file__).resolve().parents[2] / "rules" / "document_recognition_rules.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("profiles", []))


def _matching_profiles(
    profiles: List[Dict[str, Any]],
    doc_id: str,
    source_filename: str,
    page_elements: List[ElementArtifact],
    ocr_elements: List[ElementArtifact],
) -> List[Dict[str, Any]]:
    text = "\n".join(
        [doc_id, source_filename]
        + [item.text for item in page_elements if item.text]
        + [item.text for item in ocr_elements if item.text]
    )
    return [profile for profile in profiles if _matches_profile(profile, text)]


def _matches_profile(profile: Dict[str, Any], text: str) -> bool:
    match = profile.get("match", {})
    all_patterns = match.get("all_text_patterns", [])
    any_patterns = match.get("any_text_patterns", [])
    if all_patterns and not all(re.search(pattern, text, flags=re.IGNORECASE) for pattern in all_patterns):
        return False
    if any_patterns and not any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in any_patterns):
        return False
    return bool(all_patterns or any_patterns)


def _compact_cjk_text(elements: List[ElementArtifact], profile_id: str) -> List[str]:
    applied: List[str] = []
    for element in elements:
        text = element.text
        compacted = _compact_cjk_spacing(text)
        if compacted == text:
            continue
        _update_text(element, compacted, f"{profile_id}.compact_cjk_spacing")
        applied.append(f"{profile_id}.compact_cjk_spacing")
    return applied


def _compact_cjk_spacing(text: str) -> str:
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[，。；：、）】])", "", text)
    text = re.sub(r"(?<=[（【])\s+(?=[\u4e00-\u9fff])", "", text)
    return text.strip()


def _apply_text_rewrites(
    elements: List[ElementArtifact],
    profile: Dict[str, Any],
    *,
    image_width: int,
    image_height: int,
) -> List[str]:
    applied: List[str] = []
    for rule in profile.get("text_rewrites", []):
        rule_id = f"{profile['id']}.{rule['id']}"
        pattern = re.compile(rule["pattern"], flags=re.IGNORECASE)
        replacement = rule.get("replacement", "")
        for element in elements:
            if not _element_matches_rule_scope(element, rule, image_width=image_width, image_height=image_height):
                continue
            updated = pattern.sub(replacement, element.text).strip()
            if updated == element.text:
                continue
            _update_text(element, updated, rule_id)
            applied.append(rule_id)
    return applied


def _element_matches_rule_scope(
    element: ElementArtifact,
    rule: Dict[str, Any],
    *,
    image_width: int,
    image_height: int,
) -> bool:
    page_no = int(element.page_no or 0)
    if not _page_matches(rule, page_no):
        return False
    ratio = rule.get("bbox_ratio")
    if ratio is None:
        return True
    bbox = element.bbox or []
    if not _valid_bbox(bbox):
        return False
    region_bbox = _ratio_bbox(ratio, image_width, image_height)
    if region_bbox is None:
        return False
    return _bbox_overlap_candidate_ratio(bbox, region_bbox) >= float(rule.get("min_overlap", 0.35))


def _apply_region_ocr_rewrites(
    *,
    page_no: int,
    image_path: Path,
    image_width: int,
    image_height: int,
    ocr_elements: List[ElementArtifact],
    profile: Dict[str, Any],
) -> List[str]:
    applied: List[str] = []
    for rule in profile.get("region_ocr_rewrites", []):
        if not _page_matches(rule, page_no):
            continue
        rule_id = f"{profile['id']}.{rule['id']}"
        region_bbox = _ratio_bbox(rule.get("bbox_ratio", []), image_width, image_height)
        if region_bbox is None:
            continue
        text = _ocr_region(image_path, region_bbox, rule)
        match = re.search(rule["pattern"], text, flags=re.IGNORECASE | re.DOTALL)
        if match is None:
            continue
        normalized_groups = {
            key: _normalize_region_value(value, rule.get("normalizers", []))
            for key, value in match.groupdict().items()
        }
        replacement = rule.get("template", "").format(**normalized_groups).strip()
        if not replacement:
            continue
        target = _first_overlapping_ocr(ocr_elements, region_bbox)
        if target is None:
            continue
        _update_text(target, replacement, rule_id, extra_raw_ref={"region_ocr_text": text})
        applied.append(rule_id)
        if rule.get("suppress_overlapping"):
            for element in ocr_elements:
                if element.element_id == target.element_id:
                    continue
                if _bbox_overlap_candidate_ratio(element.bbox or [], region_bbox) >= 0.35:
                    _suppress(element, rule_id)
                    applied.append(rule_id)
    return applied


def _ocr_region(image_path: Path, bbox: List[int], rule: Dict[str, Any]) -> str:
    with Image.open(image_path) as image:
        crop = image.crop((bbox[0], bbox[1], bbox[0] + bbox[2], bbox[1] + bbox[3]))
        scale = int(rule.get("scale") or 1)
        if scale > 1:
            crop = crop.resize((crop.width * scale, crop.height * scale))
        crop = ImageOps.grayscale(crop)
        config = f"--psm {int(rule.get('psm') or 6)}"
        return pytesseract.image_to_string(
            crop,
            lang=rule.get("lang") or "eng",
            config=config,
            timeout=DEFAULT_TIMEOUT,
        ).strip()


def _normalize_region_value(value: str, normalizers: List[Dict[str, str]]) -> str:
    result = value.strip()
    for normalizer in normalizers:
        result = re.sub(normalizer["pattern"], normalizer.get("replacement", ""), result)
    return result.strip()


def _first_overlapping_ocr(elements: List[ElementArtifact], region_bbox: List[int]) -> Optional[ElementArtifact]:
    candidates: List[Tuple[float, ElementArtifact]] = []
    for element in elements:
        overlap = _bbox_overlap_candidate_ratio(element.bbox or [], region_bbox)
        if overlap >= 0.35:
            candidates.append((overlap, element))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1].reading_order))
    return candidates[0][1]


def _apply_page_number_rules(
    *,
    page_no: int,
    image_width: int,
    image_height: int,
    ocr_elements: List[ElementArtifact],
    profile: Dict[str, Any],
) -> List[str]:
    applied: List[str] = []
    for rule in profile.get("page_number_rules", []):
        if not _page_matches(rule, page_no):
            continue
        rule_id = f"{profile['id']}.{rule['id']}"
        region_bbox = _ratio_bbox(rule.get("bbox_ratio", []), image_width, image_height)
        patterns = [re.compile(pattern, flags=re.IGNORECASE) for pattern in rule.get("patterns", [])]
        for element in ocr_elements:
            bbox = element.bbox or []
            if region_bbox is not None and _bbox_overlap_candidate_ratio(bbox, region_bbox) < 0.95:
                continue
            if not _within_ratio_limits(bbox, image_width, image_height, rule):
                continue
            text = element.text.strip()
            if not text or not any(pattern.fullmatch(text) for pattern in patterns):
                continue
            element.raw_ref["semantic_type"] = "page_number"
            element.raw_ref.setdefault("recognition_rule_ids", [])
            if rule_id not in element.raw_ref["recognition_rule_ids"]:
                element.raw_ref["recognition_rule_ids"].append(rule_id)
            element.quality.setdefault("signals", [])
            for signal in ["external_rule_applied", "page_number", "not_body_text"]:
                if signal not in element.quality["signals"]:
                    element.quality["signals"].append(signal)
            applied.append(rule_id)
    return applied


def _within_ratio_limits(bbox: List[int], image_width: int, image_height: int, rule: Dict[str, Any]) -> bool:
    if not _valid_bbox(bbox):
        return False
    max_width_ratio = float(rule.get("max_width_ratio") or 1.0)
    max_height_ratio = float(rule.get("max_height_ratio") or 1.0)
    return bbox[2] <= image_width * max_width_ratio and bbox[3] <= image_height * max_height_ratio


def _apply_suppressions(
    *,
    page_no: int,
    image_width: int,
    image_height: int,
    ocr_elements: List[ElementArtifact],
    profile: Dict[str, Any],
) -> Tuple[List[str], List[str]]:
    applied: List[str] = []
    suppressed: List[str] = []
    for rule in profile.get("suppressions", []):
        if not _page_matches(rule, page_no):
            continue
        rule_id = f"{profile['id']}.{rule['id']}"
        region_bbox = _ratio_bbox(rule.get("bbox_ratio", []), image_width, image_height)
        patterns = [re.compile(pattern, flags=re.IGNORECASE) for pattern in rule.get("patterns", [])]
        for element in ocr_elements:
            if region_bbox is not None and _bbox_overlap_candidate_ratio(element.bbox or [], region_bbox) < 0.35:
                continue
            if patterns and not any(pattern.search(element.text.strip()) for pattern in patterns):
                continue
            _suppress(element, rule_id)
            applied.append(rule_id)
            suppressed.append(element.element_id)
    return applied, suppressed


def _update_text(
    element: ElementArtifact,
    updated: str,
    rule_id: str,
    *,
    extra_raw_ref: Optional[Dict[str, Any]] = None,
) -> None:
    original = element.raw_ref.get("original_text", element.text)
    element.raw_ref["original_text"] = original
    element.raw_ref.setdefault("recognition_rule_ids", [])
    if rule_id not in element.raw_ref["recognition_rule_ids"]:
        element.raw_ref["recognition_rule_ids"].append(rule_id)
    if extra_raw_ref:
        element.raw_ref.update(extra_raw_ref)
    element.text = updated
    element.quality.setdefault("signals", [])
    if "external_rule_applied" not in element.quality["signals"]:
        element.quality["signals"].append("external_rule_applied")


def _suppress(element: ElementArtifact, rule_id: str) -> None:
    element.raw_ref["suppressed_text"] = element.raw_ref.get("suppressed_text", element.text)
    element.raw_ref.setdefault("recognition_rule_ids", [])
    if rule_id not in element.raw_ref["recognition_rule_ids"]:
        element.raw_ref["recognition_rule_ids"].append(rule_id)
    element.quality["status"] = "ignored"
    element.quality.setdefault("signals", [])
    for signal in ["suppressed_by_external_rule", rule_id]:
        if signal not in element.quality["signals"]:
            element.quality["signals"].append(signal)


def _page_matches(rule: Dict[str, Any], page_no: int) -> bool:
    pages = rule.get("page_numbers")
    return not pages or page_no in pages


def _ratio_bbox(ratio: Iterable[Any], image_width: int, image_height: int) -> Optional[List[int]]:
    values = list(ratio)
    if len(values) != 4:
        return None
    x, y, w, h = [float(value) for value in values]
    return [
        int(round(x * image_width)),
        int(round(y * image_height)),
        int(round(w * image_width)),
        int(round(h * image_height)),
    ]


def _bbox_overlap_candidate_ratio(candidate: List[int], container: List[int]) -> float:
    if not _valid_bbox(candidate) or not _valid_bbox(container):
        return 0.0
    ax1, ay1, aw, ah = candidate
    bx1, by1, bw, bh = container
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    return ((ix2 - ix1) * (iy2 - iy1)) / max(1, aw * ah)


def _valid_bbox(bbox: List[int]) -> bool:
    return len(bbox) == 4 and bbox[2] > 0 and bbox[3] > 0


def _dedupe(items: List[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        result.append(item)
        seen.add(item)
    return result
