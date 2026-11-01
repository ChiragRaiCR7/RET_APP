import csv
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.services.comparison import Options, diff_tables, norm_col
from app.services.flatten import to_csv


def _csv(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


def test_flatten_paths_attributes_and_late_columns(tmp_path: Path) -> None:
    src = tmp_path / "a.xml"
    rows = "".join(f"<ROW><ID>{i}</ID></ROW>" for i in range(3))
    src.write_text(
        '<ROWSET xmlns="urn:x"><ROW id="7"><NAME>A</NAME><ADDR><LINE>l1</LINE>'
        f"<LINE type='b'>l2</LINE></ADDR></ROW>{rows}<ROW><LATE>z</LATE></ROW></ROWSET>"
    )
    stats = to_csv("xml", src, tmp_path / "a.csv")
    out = _csv(tmp_path / "a.csv")
    # Attributes precede their element's text (v4 order).
    assert out[0] == ["@id", "NAME", "ADDR.LINE", "ADDR.LINE[2]@type", "ADDR.LINE[2]", "ID", "LATE"]
    assert out[1] == ["7", "A", "l1", "b", "l2", "", ""]
    assert out[-1] == ["", "", "", "", "", "", "z"]  # column first seen in last row is kept
    assert (stats.rows, stats.columns, stats.record_tag) == (5, 7, "ROW")


def test_xxe_and_entity_expansion_blocked(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOPSECRET")
    src = tmp_path / "x.xml"
    src.write_text(
        f'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file://{secret}">'
        '<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
        "<R><ROW><V>&x;</V><W>&b;</W></ROW><ROW><V>2</V></ROW></R>"
    )
    to_csv("xml", src, tmp_path / "x.csv")
    text = (tmp_path / "x.csv").read_text()
    assert "TOPSECRET" not in text
    assert "aaaaaaaaaa" not in text


def test_root_without_children_is_one_record(tmp_path: Path) -> None:
    src = tmp_path / "s.xml"
    src.write_text('<CONFIG a="1">hello</CONFIG>')
    to_csv("xml", src, tmp_path / "s.csv")
    assert _csv(tmp_path / "s.csv") == [["@a"], ["1"]]


def test_empty_xml_rejected(tmp_path: Path) -> None:
    src = tmp_path / "e.xml"
    src.write_text("<R></R>")
    with pytest.raises(ValueError, match="No records"):
        to_csv("xml", src, tmp_path / "e.csv")
    assert not (tmp_path / "e.csv").exists()


def test_csv_legacy_encoding_and_ragged_rows(tmp_path: Path) -> None:
    src = tmp_path / "c.csv"
    src.write_bytes("Name,City\nJosé,Málaga\nShort\n,\n".encode("cp1252"))
    stats = to_csv("csv", src, tmp_path / "o.csv")
    assert _csv(tmp_path / "o.csv") == [["Name", "City"], ["José", "Málaga"], ["Short", ""]]
    assert stats.rows == 2


def test_xlsx_first_sheet(tmp_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["Code", None])
    ws.append(["A1", 3])
    wb.save(tmp_path / "w.xlsx")
    to_csv("xlsx", tmp_path / "w.xlsx", tmp_path / "w.csv")
    assert _csv(tmp_path / "w.csv") == [["Code", "COL_2"], ["A1", "3"]]


def _write(path: Path, rows: list[list[str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows(rows)
    return path


def test_diff_aligns_columns_by_name_and_ignores_order(tmp_path: Path) -> None:
    left = _write(tmp_path / "l.csv", [["Id", "Name"], ["1", "a"], ["2", "b"]])
    right = _write(tmp_path / "r.csv", [["Name", "Id"], ["b", "2"], ["a", "1"]])
    d = diff_tables(left, right, Options())
    assert (d.equal, d.pairs, d.added, d.removed) == (2, [], [], [])


def test_diff_classifies_changes(tmp_path: Path) -> None:
    left = _write(
        tmp_path / "l.csv",
        [
            ["Id", "Name", "Days", "CreatedBy"],
            ["1", "NET30", "30", "alice"],
            ["2", "NET60", "60", "alice"],
            ["3", "COD", "0", "bob"],
        ],
    )
    right = _write(
        tmp_path / "r.csv",
        [
            ["Id", "Name", "Days", "CreatedBy"],
            ["1", "NET30", "30", "zed"],  # only an ignored column changed
            ["2", "NET60", "45", "alice"],  # modified
            ["4", "NET90", "90", "carol"],  # added
        ],
    )
    d = diff_tables(left, right, Options(ignore_columns={norm_col("Created By")}))
    assert d.equal == 1
    assert [(i, j, [d.header[c] for c in ch]) for i, j, ch in d.pairs] == [(1, 1, ["Days"])]
    assert d.removed == [2] and d.added == [2]


def test_diff_case_and_whitespace_options(tmp_path: Path) -> None:
    left = _write(tmp_path / "l.csv", [["A"], ["Hello "]])
    right = _write(tmp_path / "r.csv", [["A"], ["hello"]])
    assert diff_tables(left, right, Options(ignore_case=True)).equal == 1
    assert diff_tables(left, right, Options(trim_whitespace=False, ignore_case=True)).equal == 0


def test_diff_one_sided(tmp_path: Path) -> None:
    right = _write(tmp_path / "r.csv", [["A"], ["x"], ["y"]])
    d = diff_tables(None, right, Options())
    assert d.added == [0, 1] and d.header == ["A"]
