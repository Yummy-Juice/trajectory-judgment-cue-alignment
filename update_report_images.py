#!/usr/bin/env python3
"""Replace only Figure 2 and Figure 4 media parts in the concise DOCX report."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import zipfile
import xml.etree.ElementTree as ET


NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}

TARGETS = {
    "Confidence calibration curves and adjusted odds ratios for accuracy, confidence, and confidence-accuracy coupling":
        "Figure_2_metacognitive_monitoring.png",
    "Zero-gravity duration transition matrix, continuous AUC-signature association, and directed transition network":
        "Figure_4_scanpath_organization.png",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def png_size(data: bytes) -> tuple[int, int]:
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("Replacement is not a valid PNG")
    return struct.unpack(">II", data[16:24])


def resolve_media_parts(
    doc_xml: bytes, rels_xml: bytes, targets: dict[str, str]
) -> dict[str, str]:
    document = ET.fromstring(doc_xml)
    rels = ET.fromstring(rels_xml)
    rel_targets = {
        node.attrib["Id"]: node.attrib["Target"]
        for node in rels.findall("pr:Relationship", NS)
    }
    found: dict[str, str] = {}
    embed_attr = f"{{{NS['r']}}}embed"
    for drawing in document.findall(".//w:drawing", NS):
        doc_pr = drawing.find(".//wp:docPr", NS)
        blip = drawing.find(".//a:blip", NS)
        if doc_pr is None or blip is None:
            continue
        descr = doc_pr.attrib.get("descr", "")
        if descr not in targets:
            continue
        rel_id = blip.attrib.get(embed_attr)
        if not rel_id or rel_id not in rel_targets:
            raise RuntimeError(f"Missing image relationship for: {descr}")
        target = rel_targets[rel_id].replace("\\", "/")
        if target.startswith("/"):
            part = target.lstrip("/")
        else:
            part = str(Path("word") / target).replace("\\", "/")
        found[descr] = part
    if set(found) != set(targets):
        missing = sorted(set(targets) - set(found))
        raise RuntimeError(f"Could not locate target images in DOCX: {missing}")
    if len(set(found.values())) != len(found):
        raise RuntimeError("Target figures unexpectedly share the same media part")
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("docx", type=Path)
    parser.add_argument("figures_dir", type=Path)
    parser.add_argument("--only", choices=("all", "figure2", "figure4"),
                        default="all")
    args = parser.parse_args()

    if args.only == "figure2":
        selected_targets = {descr: filename for descr, filename in TARGETS.items()
                            if filename.startswith("Figure_2_")}
    elif args.only == "figure4":
        selected_targets = {descr: filename for descr, filename in TARGETS.items()
                            if filename.startswith("Figure_4_")}
    else:
        selected_targets = TARGETS

    docx = args.docx.resolve()
    figures_dir = args.figures_dir.resolve()
    with zipfile.ZipFile(docx, "r") as zin:
        infos = zin.infolist()
        before = {info.filename: zin.read(info.filename) for info in infos}

    media_by_descr = resolve_media_parts(
        before["word/document.xml"], before["word/_rels/document.xml.rels"],
        selected_targets,
    )
    replacements: dict[str, bytes] = {}
    sizes: dict[str, tuple[int, int]] = {}
    for descr, filename in selected_targets.items():
        data = (figures_dir / filename).read_bytes()
        part = media_by_descr[descr]
        replacements[part] = data
        sizes[part] = png_size(data)

    fd, temp_name = tempfile.mkstemp(prefix=docx.stem + "_", suffix=".docx", dir=docx.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        with zipfile.ZipFile(temp, "w") as zout:
            for info in infos:
                data = replacements.get(info.filename, before[info.filename])
                zout.writestr(info, data)

        with zipfile.ZipFile(temp, "r") as check:
            after = {info.filename: check.read(info.filename) for info in check.infolist()}
        if set(before) != set(after):
            raise RuntimeError("DOCX part list changed during image replacement")
        changed = sorted(name for name in before if sha256(before[name]) != sha256(after[name]))
        expected = sorted(replacements)
        if changed != expected:
            raise RuntimeError(f"Unexpected changed parts: {changed}; expected: {expected}")

        os.replace(temp, docx)
    finally:
        if temp.exists():
            temp.unlink()

    print(json.dumps({
        "docx": str(docx),
        "changed_parts": expected,
        "replacement_dimensions_px": {name: list(size) for name, size in sizes.items()},
        "unchanged_part_count": len(before) - len(expected),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
