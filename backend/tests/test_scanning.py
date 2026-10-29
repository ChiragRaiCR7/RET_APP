import zipfile
from pathlib import Path

import pytest

from app.services.scanning import Limits, module_prefix, safe_member_path, scan_upload, zip_group
from tests.conftest import oracle_export, rowset, zip_bytes

LIMITS = Limits(max_files=1000, max_bytes=50 * 1024 * 1024, max_depth=10, max_ratio=200)


@pytest.mark.parametrize(
    ("name", "group"),
    [
        ("AR_PAYMENT_TERM", "AR"),
        ("FND_APP_DESCRIPTIVE_FLEXFIELD.zip", "FND"),
        ("ORA_FND_THING.xml", "ORA"),
        ("1_PO_LINES.zip", "PO"),
        ("2-GL_X.xml.gz", "GL"),
        ("X_Y.xml", "EXTRAS"),
        ("123.xml", "EXTRAS"),
        ("INVENTORYORGANIZATIONMASTER.xml", "INV"),
    ],
)
def test_module_prefix(name: str, group: str) -> None:
    assert module_prefix(name) == group


def test_batch_and_root_zips_are_not_groups() -> None:
    assert zip_group("1_BATCH.zip") is None
    assert zip_group("Export_20240101_1200.zip") is None
    assert zip_group("A very long container name with spaces.zip") is None
    assert zip_group("AR_TERMS.zip") == "AR"


def test_member_paths_cannot_traverse() -> None:
    assert safe_member_path("../../etc/passwd") == "etc/passwd"
    assert safe_member_path("..\\..\\win\\x.xml") == "win/x.xml"
    assert safe_member_path("/abs/./a:b.xml") == "abs/a_b.xml"


def _scan(tmp_path: Path, name: str, data: bytes, limits: Limits = LIMITS):  # type: ignore[no-untyped-def]
    tmp_path.mkdir(parents=True, exist_ok=True)
    up = tmp_path / "upload.bin"
    up.write_bytes(data)
    return scan_upload(up, name, tmp_path / "sources", limits)


def test_nested_export_grouping(tmp_path: Path) -> None:
    res = _scan(tmp_path, "Export_20240101_1200.zip", oracle_export())
    groups = {f.filename: f.group for f in res.files}
    assert groups == {
        "FUN_BUSINESS_UNIT.xml": "FUN",  # via business ZIP, through a batch ZIP
        "InventoryOrganizationMaster.xml": "INV",
        "InventoryOrganizationChild.xml": "INV",
        "AR_PAYMENT_TERMS.xml.gz": "AR",
        "ledgers.csv": "GL",  # loose file: grouped by top folder
    }
    gz = next(f for f in res.files if f.filename.endswith(".gz"))
    assert (tmp_path / "sources" / gz.stored_name).read_bytes().startswith(b"<?xml")
    assert not (tmp_path / "sources" / ".tmp").exists()


def test_outermost_business_zip_wins(tmp_path: Path) -> None:
    data = zip_bytes({"GL_INNER.zip": zip_bytes({"x.xml": rowset([{"a": "1"}])})})
    res = _scan(tmp_path, "AP_OUTER.zip", data)
    assert [f.group for f in res.files] == ["AP"]


def test_suspicious_compression_ratio_skipped(tmp_path: Path) -> None:
    data = zip_bytes({"BOMB.xml": b"<a>" + b"A" * 2_000_000 + b"</a>"})
    res = _scan(tmp_path, "X.zip", data)
    assert res.files == []
    assert any("compression ratio" in n for n in res.notes)


def test_byte_budget_enforced(tmp_path: Path) -> None:
    payload = bytes(range(256)) * 400  # ~100 KB, incompressible enough
    data = zip_bytes({f"F{i}_X.csv": b"a\n" + payload for i in range(5)})
    res = _scan(
        tmp_path,
        "X.zip",
        data,
        Limits(max_files=100, max_bytes=250_000, max_depth=5, max_ratio=200),
    )
    assert 1 <= len(res.files) < 5
    assert res.bytes_written <= 250_000


def test_depth_limit(tmp_path: Path) -> None:
    inner = zip_bytes({"AR_X.xml": rowset([{"a": "1"}])})
    for i in range(4):
        inner = zip_bytes({f"L{i}_N.zip": inner})
    res = _scan(
        tmp_path, "X.zip", inner, Limits(max_files=100, max_bytes=10**7, max_depth=3, max_ratio=200)
    )
    assert res.files == []
    assert any("nesting" in n for n in res.notes)


def test_single_file_and_bad_zip(tmp_path: Path) -> None:
    res = _scan(tmp_path, "PO_LINES.xml", rowset([{"a": "1"}]))
    assert [(f.group, f.file_type) for f in res.files] == [("PO", "xml")]
    with pytest.raises(ValueError, match="Unsupported"):
        _scan(tmp_path / "b", "notes.txt", b"hi")
    bad = _scan(tmp_path / "c", "X.zip", b"not a zip")
    assert bad.files == [] and any("not a valid ZIP" in n for n in bad.notes)


def test_zip_member_name_traversal_stays_inside(tmp_path: Path) -> None:
    up = tmp_path / "u.zip"
    with zipfile.ZipFile(up, "w") as zf:
        zf.writestr("../../evil_AR.xml", rowset([{"a": "1"}]))
    res = scan_upload(up, "u.zip", tmp_path / "sources", LIMITS)
    assert len(res.files) == 1
    assert next(iter((tmp_path / "sources").iterdir())).parent == tmp_path / "sources"
    assert not (tmp_path.parent / "evil_AR.xml").exists()
