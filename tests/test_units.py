from pdf2ppt.pdf.extractor import _parse_pages


def test_parse_pages_ranges():
    assert _parse_pages("1-3", 5) == [0, 1, 2]
    assert _parse_pages("1-3,5", 6) == [0, 1, 2, 4]
    assert _parse_pages("2,4-5", 7) == [1, 3, 4]
    assert _parse_pages("10", 12) == [9]
    assert _parse_pages("2-2", 3) == [1]
