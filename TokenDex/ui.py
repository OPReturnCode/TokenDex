from decimal import Decimal as PyDecimal
import threading
import traceback
import queue

from PyQt5 import QtWidgets
from PyQt5 import QtGui
from PyQt5 import QtCore

from electroncash_gui.qt.amountedit import SLPAmountEdit, BTCAmountEdit
# from electroncash_gui.qt.util import ColorScheme
from electroncash_gui.qt.util import WaitingDialog
from electroncash.util import NotEnoughFunds, NotEnoughFundsSlp

from . import dex


class DexTab(QtWidgets.QWidget):
    got_order_book_data = QtCore.pyqtSignal()
    orders_need_update = QtCore.pyqtSignal()
    window_is_destroyed = threading.Event()

    def __init__(self, wallet, window, *args, **kwargs):
        super(DexTab, self).__init__(*args, **kwargs)

        self.task_queue = queue.Queue()
        self.working_thread = DexThread(None, self.task_queue)
        self.working_thread.start()
        self.working_thread.error_raised.connect(self.on_error)
        self.wallet = wallet
        self.window = window
        self.config = self.window.config
        self.password = None  # TODO get password
        self.dex = None

        self.blockchain_sell_orders = list()
        self.blockchain_buy_orders = list()
        self.blockchain_take_orders = list()
        self.user_orders_data = list()

        self.layout = QtWidgets.QGridLayout()
        self.setLayout(self.layout)
        bold_font = QtGui.QFont()
        bold_font.setBold(True)

        self.token_types_layout = QtWidgets.QGridLayout()
        token_types_label = QtWidgets.QLabel("Token Type")
        token_types_label.setFont(bold_font)
        self.token_types_combo = QtWidgets.QComboBox()
        self.token_combo_update_btn = QtWidgets.QPushButton("Update Token List")

        self._fill_token_type_combo()

        self.token_types_layout.addWidget(token_types_label, 0, 1)
        self.token_types_layout.addWidget(self.token_types_combo, 0, 2, 1, 8)
        self.token_types_layout.addWidget(self.token_combo_update_btn, 0, 10)

        self.layout.addLayout(self.token_types_layout, 0, 0, 1, 12)

        self.place_order_layout = QtWidgets.QGridLayout()
        place_order_label = QtWidgets.QLabel("Place Order")
        place_order_label.setFont(bold_font)
        self.place_order_layout.addWidget(place_order_label, 0, 0)
        self.order_type_combo = QtWidgets.QComboBox()
        self.order_type_combo.addItem('SELL', 'SELL')
        self.order_type_combo.addItem('BUY', 'BUY')

        self.place_order_layout.addWidget(QtWidgets.QLabel("Order Type"), 1, 0)
        self.place_order_layout.addWidget(self.order_type_combo, 1, 1)

        self.coins_list_combo = QtWidgets.QComboBox()
        self.place_order_layout.addWidget(QtWidgets.QLabel("Select Coin"), 2, 0)
        self.place_order_layout.addWidget(self.coins_list_combo, 2, 1)

        self.place_order_layout.addWidget(QtWidgets.QLabel("Token Amount"), 3, 0)
        self.slp_amount_edit = SLPAmountEdit('tokens', 0)
        self.slp_amount_edit.setEnabled(False)
        self.place_order_layout.addWidget(self.slp_amount_edit, 3, 1)

        self.place_order_layout.addWidget(QtWidgets.QLabel("BCH Amount"), 4, 0)
        self.bch_amount_edit = BTCAmountEdit(lambda: 8)
        self.bch_amount_edit.setEnabled(False)
        self.place_order_layout.addWidget(self.bch_amount_edit, 4, 1)

        self.place_order_layout.addWidget(QtWidgets.QLabel("Rate"), 5, 0)
        self.rate_edit = BTCAmountEdit(lambda: 8, is_int=True)
        self.place_order_layout.addWidget(self.rate_edit, 5, 1)

        self.order_btn = QtWidgets.QPushButton("Order")
        self.place_order_layout.addWidget(self.order_btn, 6, 0, 1, 2)
        self.layout.addLayout(self.place_order_layout, 4, 0, 2, 2)

        self.order_book_layout = QtWidgets.QGridLayout()
        buy_orders_label = QtWidgets.QLabel("Buy Orders")
        buy_orders_label.setFont(bold_font)
        sell_orders_label = QtWidgets.QLabel("Sell Orders")
        sell_orders_label.setFont(bold_font)

        self.order_book_layout.addWidget(buy_orders_label, 0, 0, 1, 1)
        self.order_book_layout.addWidget(sell_orders_label, 0, 1, 1, 1)
        self.buy_orders = QtWidgets.QTableWidget()
        self.buy_orders.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.buy_orders.setColumnCount(4)
        self.buy_orders.setHorizontalHeaderLabels(["BCH Amount", "Rate", "SLP To Pay", "Take Order"])
        self.buy_orders.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.order_book_layout.addWidget(self.buy_orders, 1, 0, 1, 1)

        self.sell_orders = QtWidgets.QTableWidget()
        self.sell_orders.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.sell_orders.setColumnCount(4)
        self.sell_orders.setHorizontalHeaderLabels(["SLP Amount", "Rate", "BCH To Pay", "Take Order"])
        self.sell_orders.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.order_book_layout.addWidget(self.sell_orders, 1, 1, 1, 1)

        your_orders_label = QtWidgets.QLabel("Your Orders")
        your_orders_label.setFont(bold_font)
        take_orders_label = QtWidgets.QLabel("Take Orders")
        take_orders_label.setFont(bold_font)
        self.order_book_layout.addWidget(your_orders_label, 2, 0)
        # self.order_book_layout.addWidget(take_orders_label, 2, 1)

        self.user_orders = QtWidgets.QTableWidget()
        self.user_orders.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.user_orders.setColumnCount(6)
        self.user_orders.setHorizontalHeaderLabels([
            "Order Type", "Amount", "Rate", "BCH Payment", "Cancel Order", "Got Take Order"
        ])
        self.user_orders.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.order_book_layout.addWidget(self.user_orders, 3, 0, 5, 5)

        self.refresh_btn = QtWidgets.QPushButton('Refresh Orders')
        self.order_book_layout.addWidget(self.refresh_btn, 9, 0, 5, 5)

        # self.take_orders = QtWidgets.QTableWidget()
        # self.take_orders.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        # self.take_orders.setColumnCount(5)
        # self.take_orders.setHorizontalHeaderLabels([
        # "Order Type", "Token Amount", "Rate", "BCH Amount", "Accept Order"
        # ])
        # self.take_orders.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        # self.order_book_layout.addWidget(self.take_orders, 3, 1, 1, 1)

        self.layout.addLayout(self.order_book_layout, 1, 2, 5, 10)

        self.token_types_combo.currentIndexChanged.connect(self.token_type_index_changed)
        self.order_type_combo.currentIndexChanged.connect(self.order_type_index_changed)
        self.coins_list_combo.currentIndexChanged.connect(self.coins_list_index_changed)

        self.got_order_book_data.connect(self.handle_blockchain_orders)
        self.orders_need_update.connect(self.update_orders)
        self.bch_amount_edit.textChanged.connect(self.rate_changed)
        self.slp_amount_edit.textChanged.connect(self.rate_changed)
        self.rate_edit.textChanged.connect(self.rate_changed)
        self.order_btn.clicked.connect(self.place_order)
        self.refresh_btn.clicked.connect(self.get_blockchain_orders_with_waiting_dialog)
        self.token_combo_update_btn.clicked.connect(self._fill_token_type_combo)
        # token_types_combo.currentIndexChanged.connect()  # TODO monitor for orders to place automatically?

    def on_error(self, exc_info):
        print(exc_info[2])
        traceback.print_exception(*exc_info)
        self.window.show_error(str(exc_info[1]))

    def _fill_token_type_combo(self):
        blacklist = [  # blacklisted these tokens due to complications with them
            'fb1813fd1a53c1bed61f15c0479cc5315501e6da6a4d06da9d8122c1a4fabb6c',
            'dd21be4532d93661e8ffe16db6535af0fb8ee1344d1fef81a193e2b4cfa9fbc9'
        ]
        current_combo_data = []
        for i in range(self.token_types_combo.count()):
            current_combo_data.append(self.token_types_combo.itemData(i))
        if len(current_combo_data) == 0:
            self.token_types_combo.addItem(QtGui.QIcon(":icons/tab_coins.png"), "None", None)
        for token in self.wallet.token_types:
            if token not in current_combo_data and token not in blacklist:
                self.token_types_combo.addItem(QtGui.QIcon(":icons/tab_slp_icon.png"),
                                               self.wallet.token_types[token]['name'], token)

    def token_type_index_changed(self):
        token_hex = self.token_types_combo.currentData()
        if not token_hex:
            self.bch_amount_edit.clear()
            self.slp_amount_edit.clear()
            self.rate_edit.clear()
            self.coins_list_combo.clear()
            return
        token = self.wallet.token_types[token_hex]
        self.slp_amount_edit.set_token(token['name'][:6], token['decimals'])

        self.order_type_index_changed()

        self.dex = dex.Dex(self.wallet, token_hex, self.config, self.password)

        self.update_orders()

    def update_orders(self):
        # self.get_blockchain_orders()
        self.get_blockchain_orders_with_waiting_dialog()
        self.handle_user_orders()

    def get_blockchain_orders(self):
        def wrapper():
            self.blockchain_sell_orders = self.dex.get_blockchain_sell_orders()
            self.blockchain_buy_orders = self.dex.get_blockchain_buy_orders()

            self.get_user_orders()
            order_hexes = [order['order_id'] for order in self.user_orders_data]
            self.blockchain_take_orders = self.dex.get_blockchain_take_orders(order_hexes)

            utxo_list = []
            for order in self.blockchain_sell_orders:
                utxo_list.append([order['utxo_prevout_hash'], order['utxo_prevout_n']])
            for order in self.blockchain_buy_orders:
                utxo_list.append([order['utxo_prevout_hash'], order['utxo_prevout_n']])

            def callback(result):
                if not result['result']:
                    prevout_h = result['params'][0]
                    prevout_n = result['params'][1]
                    sell_order_indexes = []
                    buy_order_indexes = []

                    for i, order in enumerate(self.blockchain_sell_orders):
                        if order['utxo_prevout_hash'] == prevout_h and order['utxo_prevout_n'] == prevout_n:
                            sell_order_indexes.append(i)
                    sorted(sell_order_indexes, reverse=True)
                    for i in sell_order_indexes:
                        del self.blockchain_sell_orders[i]

                    for i, order in enumerate(self.blockchain_buy_orders):
                        if order['utxo_prevout_hash'] == prevout_h and order['utxo_prevout_n'] == prevout_n:
                            buy_order_indexes.append(i)
                    sorted(buy_order_indexes, reverse=True)
                    for i in buy_order_indexes:
                        del self.blockchain_buy_orders[i]
                self.got_order_book_data.emit()
            self.dex.get_utxo_info_batch(utxo_list, callback)

            self.got_order_book_data.emit()
        self.task_queue.put(wrapper)

    def get_blockchain_orders_with_waiting_dialog(self):
        if not self.token_types_combo.currentData():
            return

        def wrapper():
            self.blockchain_sell_orders = self.dex.get_blockchain_sell_orders()
            self.blockchain_buy_orders = self.dex.get_blockchain_buy_orders()

            self.get_user_orders()
            order_hexes = [order['order_id'] for order in self.user_orders_data]
            self.blockchain_take_orders = self.dex.get_blockchain_take_orders(order_hexes)

            utxo_list = []
            for order in self.blockchain_sell_orders:
                utxo_list.append([order['utxo_prevout_hash'], order['utxo_prevout_n']])
            for order in self.blockchain_buy_orders:
                utxo_list.append([order['utxo_prevout_hash'], order['utxo_prevout_n']])

            def callback(result):
                if not result['result']:
                    prevout_h = result['params'][0]
                    prevout_n = result['params'][1]
                    sell_order_indexes = []
                    buy_order_indexes = []

                    for i, order in enumerate(self.blockchain_sell_orders):
                        if order['utxo_prevout_hash'] == prevout_h and order['utxo_prevout_n'] == prevout_n:
                            sell_order_indexes.append(i)
                    sorted(sell_order_indexes, reverse=True)
                    for i in sell_order_indexes:
                        del self.blockchain_sell_orders[i]

                    for i, order in enumerate(self.blockchain_buy_orders):
                        if order['utxo_prevout_hash'] == prevout_h and order['utxo_prevout_n'] == prevout_n:
                            buy_order_indexes.append(i)
                    sorted(buy_order_indexes, reverse=True)
                    for i in buy_order_indexes:
                        del self.blockchain_buy_orders[i]
                self.got_order_book_data.emit()
            self.dex.get_utxo_info_batch(utxo_list, callback)

            self.got_order_book_data.emit()

        WaitingDialog(self, "Fetching latest order book data. Please wait...", wrapper, on_error=self.on_error)

    def handle_blockchain_orders(self):
        token_hex = self.token_types_combo.currentData()
        if token_hex is not None:
            token_decimals = self.wallet.token_types[token_hex]['decimals']

            self.sell_orders.setRowCount(len(self.blockchain_sell_orders))
            self.buy_orders.setRowCount(len(self.blockchain_buy_orders))

            for i, order in enumerate(self.blockchain_sell_orders):
                amount_to_sell = order['amount_to_sell'] / PyDecimal(10**token_decimals)
                rate = order['rate']
                total = amount_to_sell * rate / PyDecimal(10**8)  # TODO BCH TO PAY?
                amount_to_sell_column = QtWidgets.QTableWidgetItem(str(amount_to_sell))
                rate_column = QtWidgets.QTableWidgetItem(str(rate))
                total_column = QtWidgets.QTableWidgetItem(str(total))

                self.sell_orders.setItem(i, 0, amount_to_sell_column)
                self.sell_orders.setItem(i, 1, rate_column)
                self.sell_orders.setItem(i, 2, total_column)
                btn = QtWidgets.QPushButton()
                btn.setText('Take Order')
                # btn.setStyleSheet(ColorScheme.RED.as_stylesheet())
                btn.clicked.connect(self.take_sell_order)

                self.sell_orders.setCellWidget(i, 3, btn)
            for i, order in enumerate(self.blockchain_buy_orders):
                amount_to_buy = order['amount_to_buy'] / PyDecimal(10**8)
                rate = order['rate']
                total = amount_to_buy * rate
                amount_to_buy_column = QtWidgets.QTableWidgetItem(str(amount_to_buy))
                rate_column = QtWidgets.QTableWidgetItem(str(rate))
                total_column = QtWidgets.QTableWidgetItem(str(total))
                self.buy_orders.setItem(i, 0, total_column)
                self.buy_orders.setItem(i, 1, rate_column)
                self.buy_orders.setItem(i, 2, amount_to_buy_column)

                btn = QtWidgets.QPushButton()
                btn.setText('Take Order')
                # btn.setStyleSheet(ColorScheme.GREEN.as_stylesheet())
                btn.clicked.connect(self.take_buy_order)

                self.buy_orders.setCellWidget(i, 3, btn)

        self.handle_user_orders()

    def get_user_orders(self):
        token_hex = self.token_types_combo.currentData()
        user_dex_orders = self.wallet.storage.get('user_dex_orders', {})
        data = user_dex_orders.get(token_hex, [])

        self.user_orders_data = []
        for order in data:
            # check if coin still exists in wallet
            coin = order['coin']
            prevout_hash = coin['prevout_hash']
            prevout_n = coin['prevout_n']
            wallet_utxos = self.wallet.get_utxos(exclude_slp=False, exclude_frozen=False)
            for utxo in wallet_utxos:
                if utxo['prevout_hash'] == prevout_hash and utxo['prevout_n'] == prevout_n:
                    self.user_orders_data.append(order)

    def handle_user_orders(self):
        self.get_user_orders()

        token_hex = self.token_types_combo.currentData()
        token_decimals = self.wallet.token_types[token_hex]['decimals']
        self.user_orders.setRowCount(len(self.user_orders_data))

        for i, order in enumerate(self.user_orders_data):
            order_type = order['order_type']
            if order_type == 'sell' or order_type == 'take':
                amount = order['amount_to_sell'] / PyDecimal(10**token_decimals)
            elif order_type == 'buy':
                amount = order['amount_to_buy'] / PyDecimal(10**token_decimals)

            order_type_column = QtWidgets.QTableWidgetItem(order_type)
            total = amount * order['rate'] / 10**8
            amount_column = QtWidgets.QTableWidgetItem(str(amount))
            rate_column = QtWidgets.QTableWidgetItem(str(order['rate']))
            total_column = QtWidgets.QTableWidgetItem(str(total))
            self.user_orders.setItem(i, 0, order_type_column)
            self.user_orders.setItem(i, 1, amount_column)
            self.user_orders.setItem(i, 2, rate_column)
            self.user_orders.setItem(i, 3, total_column)
            btn = QtWidgets.QPushButton()
            btn.setText('Cancel Order')
            # btn.setStyleSheet(ColorScheme.RED.as_stylesheet())
            btn.clicked.connect(self.cancel_order)
            self.user_orders.setCellWidget(i, 4, btn)

            for take_order in self.blockchain_take_orders:
                assert take_order['order_type'] == 'TAKE'
                order_id_to_take = take_order['order_id_to_take']

                if order_id_to_take == order['order_id']:
                    btn = QtWidgets.QPushButton()
                    btn.setText('Accept Take Order')
                    # btn.setStyleSheet(ColorScheme.RED.as_stylesheet())
                    btn.clicked.connect(self.accept_take_order)
                    self.user_orders.setCellWidget(i, 5, btn)

    def accept_take_order(self):
        # TODO make sure current row index always equals self.user_orders_data index
        current_row = self.user_orders.currentRow()
        order = self.user_orders_data[current_row]
        # print(current_row, order)

        for take_order in self.blockchain_take_orders:
            assert take_order['order_type'] == 'TAKE'
            order_id_to_take = take_order['order_id_to_take']

            if order_id_to_take == order['order_id']:
                tx_id = take_order['tx_id']

                def take_order_wrapper():
                    try:
                        coin = order['coin']
                        from electroncash.address import Address
                        coin['address'] = Address.from_string(coin['address'])
                        print(self.dex.take_order(tx_id, mandatory_coin=coin))
                        self.orders_need_update.emit()
                    except NotEnoughFunds:
                        raise NotEnoughFunds("Not Enough Funds")
                    except Exception as e:
                        print(e);raise e
                        raise (e)

                WaitingDialog(self, "Please wait...", take_order_wrapper, on_error=self.on_error)
                break


    def place_order(self):
        order_type = self.order_type_combo.currentData()
        rate = self.rate_edit.get_amount()
        if rate is None:
            return self.window.show_error("Please enter a rate.")

        rate = PyDecimal(rate) / 10 ** 8
        assert rate.as_tuple().exponent == 0  # make sure it doesn't get round
        rate = int(rate)

        if order_type == 'SELL':
            bch_amount = self.bch_amount_edit.get_amount()
            slp_coin = self.coins_list_combo.currentData()
            slp_amount_to_sell = slp_coin['token_value']

            def place_sell_order_wrapper():
                try:
                    print(self.dex.place_sell_order(slp_coin, slp_amount_to_sell, bch_amount, rate, slp_amount_to_sell))
                    self.orders_need_update.emit()
                except NotEnoughFunds:
                    raise NotEnoughFunds("Not Enough Funds")
            WaitingDialog(self, "Please wait...", place_sell_order_wrapper, on_error=self.on_error)
        elif order_type == 'BUY':
            bch_amount = self.bch_amount_edit.get_amount()
            bch_order_coin = self.coins_list_combo.currentData()
            slp_amount_to_buy = self.slp_amount_edit.get_amount()

            def place_buy_order_wrapper():
                try:
                    print(self.dex.place_buy_order(
                        bch_order_coin, slp_amount_to_buy, rate, slp_amount_to_buy)
                    )  # TODO let the user set min chunk
                    self.orders_need_update.emit()
                except NotEnoughFunds:
                    raise NotEnoughFunds("Not Enough Funds")
            WaitingDialog(self, "Please wait...", place_buy_order_wrapper, on_error=self.on_error)

    def take_sell_order(self):
        current_row = self.sell_orders.currentRow()
        tx_id = self.blockchain_sell_orders[current_row]['tx_id']

        def take_order_wrapper():
            try:
                print(self.dex.take_order(tx_id))
                self.orders_need_update.emit()
            except NotEnoughFunds:
                raise NotEnoughFunds("Not Enough Funds")
            except Exception as e:
                print(e);raise e
                raise(e)

        WaitingDialog(self, "Please wait...", take_order_wrapper, on_error=self.on_error)

    def cancel_order(self):
        current_row = self.sell_orders.currentRow()
        order = self.user_orders_data[current_row]
        coin = order['coin']
        from electroncash.address import Address
        coin['address'] = Address.from_string(coin['address'])

        if order['order_type'] == 'sell':
            token_hex = self.token_types_combo.currentData()

            def spend_order_slp_coin_wrapper():
                try:
                    self.wallet.set_frozen_coin_state([coin], False)
                    tx = dex.transaction.spend_slp_coin(
                        self.wallet, token_hex, coin, self.config, None, self.password
                    )
                    self.orders_need_update.emit()
                except Exception as e:
                    self.wallet.set_frozen_coin_state([coin], True)
                    raise e
            WaitingDialog(
                self, "Please wait...", spend_order_slp_coin_wrapper,
                on_error=self.on_error, on_success=lambda res: self.handle_user_orders()
            )

        elif order['order_type'] == 'buy':
            self.window.spend_coins([coin])

    def take_buy_order(self):
        current_row = self.buy_orders.currentRow()
        tx_id = self.blockchain_buy_orders[current_row]['tx_id']
        print(tx_id)

        def take_order_wrapper():
            try:
                print(self.dex.take_order(tx_id))
                self.orders_need_update.emit()
            except NotEnoughFunds:
                raise NotEnoughFunds("Not Enough Funds")
        WaitingDialog(self, "Please wait...", take_order_wrapper, on_error=self.on_error)

    def order_type_index_changed(self):
        token_hex = self.token_types_combo.currentData()
        if not token_hex:
            return
        token_decimals = self.wallet.token_types[token_hex]['decimals']
        order_type = self.order_type_combo.currentData()
        self.bch_amount_edit.clear()
        self.slp_amount_edit.clear()
        self.rate_edit.clear()
        self._fill_coins_list_combo(token_hex, order_type, token_decimals)

    def coins_list_index_changed(self):
        token_hex = self.token_types_combo.currentData()
        if not token_hex or not self.coins_list_combo.currentData():
            return
        order_type = self.order_type_combo.currentData()
        if order_type == 'SELL':
            token_decimals = self.wallet.token_types[token_hex]['decimals']
            current_slp_amount = self.coins_list_combo.currentData()['token_value'] / PyDecimal(10 ** token_decimals)
            self.slp_amount_edit.setAmount(current_slp_amount * 10**token_decimals)
        elif order_type == 'BUY':
            current_bch_amount = self.coins_list_combo.currentData()['value']
            self.bch_amount_edit.setAmount(current_bch_amount)

    def _fill_coins_list_combo(self, token_hex, order_type, token_decimals):
        self.coins_list_combo.clear()
        if order_type == 'SELL':
            coins = self.wallet.get_slp_spendable_coins(token_hex, None, {})
            for coin in coins:
                slp_amount = coin['token_value'] / PyDecimal(10 ** token_decimals)
                self.coins_list_combo.addItem(
                    ', SLP Amount: '.join(["...".join([
                        str(coin['address'])[:6],
                        str(coin['address'])[-6:]]),
                        str(slp_amount)
                    ]), coin
                )
        elif order_type == 'BUY':
            coins = self.wallet.get_spendable_coins(None, {})  # TODO: pass the config properly
            for coin in coins:
                self.coins_list_combo.addItem(
                    ', Amount: '.join(["...".join([
                        str(coin['address'])[:6],
                        str(coin['address'])[-6:]]),
                        str(coin['value'])
                    ]), coin
                )
        self.coins_list_index_changed()

    def rate_changed(self):
        order_type = self.order_type_combo.currentData()
        token_hex = self.token_types_combo.currentData()
        rate = self.rate_edit.get_amount()
        if rate is not None and token_hex is not None:
            token_decimals = self.wallet.token_types[token_hex]['decimals']
            rate = PyDecimal(rate) / 10**8
            assert rate.as_tuple().exponent == 0  # make sure it doesn't get round
            rate = int(rate)
            if order_type == 'SELL':  # UTXO is SLP
                slp_amount = self.slp_amount_edit.get_amount()
                if slp_amount:
                    self.bch_amount_edit.setAmount(rate * slp_amount / 10**token_decimals)
            elif order_type == 'BUY':  # UTXO is BCH

                bch_amount = self.bch_amount_edit.get_amount()
                if bch_amount:
                    self.slp_amount_edit.setAmount(bch_amount / rate * 10**token_decimals if rate != 0 else 0)

    def background_thread_loop(self):
        while not self.isHidden():  # Find a better way
            try:
                print('loop')
                task = self.task_queue.get(timeout=3)
                print("running", task.__name__)
                task()
            except Exception as e:
                pass


class DexThread(QtCore.QThread):
    error_raised = QtCore.pyqtSignal(str)

    def __init__(self, parent=None, task_queue=None):
        super(DexThread, self).__init__(parent)
        self.task_queue = task_queue

    def run(self):
        while True:
            try:
                task = self.task_queue.get(timeout=3)
                print("running", task.__name__)
                task()
            except queue.Empty:
                pass
            except NotEnoughFunds as e:
                raise NotEnoughFunds("Not Enough Funds")
            except Exception as e:
                self.error_raised.emit(e.__class__.__name__ + ' ' + str(e))


def generate_dex_tab(wallet, window):
    tab = DexTab(wallet, window)
    return tab
