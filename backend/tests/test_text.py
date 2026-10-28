from pixelforge.text import slugify


def test_slugify():
    assert slugify("Élan Bleu!!") == "elan-bleu"
    assert slugify("???") == "project"
