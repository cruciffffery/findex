from findex.tokenize import WordStream, tokenize


def test_unicode_fold_and_case():
    assert list(tokenize("CAFÉ")) == ["café"]
    assert list(WordStream().tokenize("Ａｌｉｃｅ")) == ["alice"]


def test_apostrophes_stay_inside():
    assert list(tokenize("don't")) == ["don't"]
    assert list(tokenize("it's")) == ["it's"]


def test_hyphen_glues_parts():
    assert list(tokenize("good-for-nothing")) == ["good-for-nothing"]


def test_digits_survive():
    assert list(tokenize("number 4 and 1991")) == ["number", "4", "and", "1991"]


def test_punctuation_is_boundary():
    assert list(tokenize("Hello, world!")) == ["hello", "world"]


def test_blank_input():
    assert list(tokenize("")) == []
    assert list(tokenize("... --- !!!")) == []


def test_lazy_yield():
    it = tokenize("a b c")
    assert next(it) == "a"
    assert list(it) == ["b", "c"]
