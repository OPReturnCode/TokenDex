from PyQt5 import QtGui

from electroncash.plugins import BasePlugin, hook

from . import ui


class Plugin(BasePlugin):

    @hook
    def init_qt(self, gui):
        for window in gui.windows:
            # tab = ui.DexTab(window.wallet)
            tab = ui.DexTab(window.wallet, window)
            window.tabs.addTab(tab, QtGui.QIcon(":icons/tab_slp_icon.png"), "TokenDex")

    @hook
    def on_new_window(self, window):
        # tab = ui.DexTab(window.wallet)
        tab = ui.DexTab(window.wallet, window)
        window.tabs.addTab(tab, QtGui.QIcon(":icons/tab_slp_icon.png"), "TokenDex")
