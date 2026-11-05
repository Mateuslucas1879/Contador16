"""Ponto de entrada: python main.py"""
import sys

from PyQt6.QtWidgets import QApplication

from contador.ui import theme
from contador.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")              # base neutra: o QSS do tema cuida do visual
    app.setStyleSheet(theme.QSS)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
