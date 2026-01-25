from xml.etree import ElementTree as ET

def flatten_xml(xml_path: str) -> list[dict]:
    tree = ET.parse(xml_path)
    root = tree.getroot()

    records = []
    for elem in root:
        record = {}
        for child in elem:
            record[child.tag] = child.text
        records.append(record)

    return records
