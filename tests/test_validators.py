from backend.app.formatting.validators import validate_length

def test_text_limit():
    ok, _ = validate_length("a"*4096)
    assert ok is True
    ok2, err = validate_length("a"*4097)
    assert ok2 is False

def test_caption_limit():
    ok, _ = validate_length("a"*1024, is_caption=True)
    assert ok is True
    ok2, _ = validate_length("a"*1025, is_caption=True)
    assert ok2 is False
