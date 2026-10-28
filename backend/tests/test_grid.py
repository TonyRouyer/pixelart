from PIL import Image

from pixelforge.grid import cell_box, cell_size, compose_grid, grid_shape, split_grid


def test_grid_shape():
    assert grid_shape(6) == (3, 2)
    assert grid_shape(4) == (2, 2)
    assert grid_shape(16) == (4, 4)
    assert grid_shape(2) == (2, 1)


def test_cell_size_multiple_of_8():
    assert cell_size(4, 1024) == 512
    assert cell_size(6, 1000) == 328  # 1000 // 3 = 333 -> 328
    assert cell_size(16, 1000) % 8 == 0


def test_compose_split_roundtrip():
    imgs = [Image.new("RGB", (40, 40), (i * 30, 0, 0)) for i in range(6)]
    back = split_grid(compose_grid(imgs, 64), 6)
    assert len(back) == 6 and back[5].getpixel((32, 32))[0] == 150


def test_compose_contain_centers_and_pads():
    img = Image.new("RGB", (20, 10), (255, 0, 0))
    out = compose_grid([img], 40, background=(0, 0, 9))
    assert out.size == (40, 40)
    assert out.getpixel((20, 20)) == (255, 0, 0)
    assert out.getpixel((20, 2)) == (0, 0, 9)


def test_cell_box():
    assert cell_box(4, 6, 64) == (64, 64, 128, 128)
    assert cell_box(0, 6, 64) == (0, 0, 64, 64)
