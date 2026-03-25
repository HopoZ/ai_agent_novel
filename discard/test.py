import os
from agents.loader import LoreLoader


def test_lore_loader():
    loader = LoreLoader()
    lore_content = loader.get_all_lore()
    print("加载的百科设定内容：\n", lore_content)


if __name__ == "__main__":
    test_lore_loader()

