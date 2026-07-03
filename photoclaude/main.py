import os
import sys

from PySide6.QtWidgets import QApplication

from photoclaude import APP_NAME
from photoclaude.ui.main_window import MainWindow


def main():
    if os.environ.get("PHOTOSTUDIO_SELFTEST") == "1":
        from photoclaude import selftest

        sys.exit(selftest.run())

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
