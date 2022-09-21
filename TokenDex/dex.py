import json
from decimal import Decimal as PyDecimal

from electroncash.transaction import Transaction

from . import transaction, order, bfp, order_book, validation


class Dex:

    def __init__(self, wallet, token_hex, config={}, password=None):
        self.wallet = wallet
        self.token_hex = token_hex
        self.token_decimals = self.wallet.token_types[self.token_hex]['decimals']
        self.config = config
        self.password = password

    # TODO, freeze coins
    def place_sell_order(self, slp_coin, slp_amount_to_sell, bch_amount, rate, min_chunk):
        amount_bch_to_receive = slp_coin['token_value'] / 10**self.token_decimals * rate
        assert amount_bch_to_receive == bch_amount
        assert slp_coin['token_value'] == slp_amount_to_sell
        partial_slp_tx = transaction.create_partial_slp_tx(self.wallet, slp_coin, bch_amount, self.password)

        sell_order_op_return = order.build_sell_order_op_return(
            self.wallet, self.token_hex, slp_amount_to_sell, rate, min_chunk,
            partial_slp_tx.raw, partial_slp_tx.inputs(), self.config, self.password
        )
        sell_order_tx = transaction.create_signal_tx(self.wallet, sell_order_op_return, self.config)
        self.wallet.sign_transaction(sell_order_tx, password=self.password)

        success, sell_order_tx_id = self.wallet.network.broadcast_transaction(sell_order_tx)

        if success:
            self.wallet.set_frozen_coin_state([slp_coin], True)
            slp_coin['address'] = slp_coin['address'].to_slpaddr()
            order_dict = {
                'order_type': 'sell',
                'token_id': self.token_hex,
                'amount_to_sell': slp_amount_to_sell,
                'rate': rate,
                'min_chunk': min_chunk,
                'coin': slp_coin,
                'order_id': sell_order_tx_id
            }
            user_orders_dict = self.wallet.storage.get('user_dex_orders', {})
            user_orders_for_token = user_orders_dict.get(self.token_hex, [])
            user_orders_for_token.append(order_dict)
            user_orders_dict[self.token_hex] = user_orders_for_token
            self.wallet.storage.put('user_dex_orders', user_orders_dict)
            self.wallet.storage.write()
        else:
            print(sell_order_tx_id)
        return success

    def place_buy_order(self, bch_order_coin, amount, rate, min_chunk):
        self.wallet.set_frozen_coin_state([bch_order_coin], True)
        buy_order_op_return = order.build_buy_order_op_return(
            self.wallet, self.token_hex, amount, rate, min_chunk, bch_order_coin, self.config, self.password
        )
        buy_order_tx = transaction.create_signal_tx(self.wallet, buy_order_op_return, self.config)
        self.wallet.sign_transaction(buy_order_tx, password=self.password)

        success, buy_order_tx_id = self.wallet.network.broadcast_transaction(buy_order_tx)

        if success:
            bch_order_coin['address'] = bch_order_coin['address'].to_cashaddr()
            order_dict = {
                'order_type': 'buy',
                'token_id': self.token_hex,
                'amount_to_buy': amount,
                'rate': rate,
                'min_chunk': min_chunk,
                'coin': bch_order_coin,
                'order_id': buy_order_tx_id
            }
            user_orders_dict = self.wallet.storage.get('user_dex_orders', {})
            user_orders_for_token = user_orders_dict.get(self.token_hex, [])
            user_orders_for_token.append(order_dict)
            user_orders_dict[self.token_hex] = user_orders_for_token
            self.wallet.storage.put('user_dex_orders', user_orders_dict)
            self.wallet.storage.write()
        else:
            self.wallet.set_frozen_coin_state([bch_order_coin], False)
            print(buy_order_tx_id)
        return success

    def take_order(self, order_txid, mandatory_coin=None):
        success, raw_order_tx = self.wallet.network.get_raw_tx_for_txid(order_txid)
        print(success, raw_order_tx)
        if success:
            order_tx = Transaction(raw_order_tx)
            order_op_return = order_tx.get_outputs()[0][0]
            parsed_order_data = order.parse_order_op_return(order_op_return.to_script())
            order_type = parsed_order_data['order_type']
            amount_bch_to_receive = parsed_order_data['amount'] / PyDecimal(10**self.token_decimals) * parsed_order_data['rate']
            assert self.token_hex == parsed_order_data['token_hex']
            # TODO assert amount and chunks match
            # TODO assert amount_bch_to_receive is OK
            # if all passed, go on

            proof_of_reserve_data = json.loads(bfp.download_file(self.wallet, parsed_order_data['proof_of_reserve_tx']))

            if order_type.lower() == 'sell' or order_type.lower() == 'take':
                partial_tx_hex = proof_of_reserve_data['partial_tx']
                # verify them and validate tokens
                partial_tx = Transaction(partial_tx_hex)
                assert amount_bch_to_receive == partial_tx.output_value()
                utxos = partial_tx.inputs()
                assert len(utxos) == 1
                utxo = utxos[0]
                input_is_valid = validation.validate_transaction(
                    self.wallet, utxo['prevout_hash'], self.token_hex,
                    utxo['prevout_n'], parsed_order_data['amount']
                )
                if input_is_valid:
                    take_order_tx = transaction.complete_partial_slp_tx(
                        self.wallet, partial_tx_hex, amount_bch_to_receive,
                        parsed_order_data['amount'], self.token_hex, mandatory_coin=mandatory_coin, config=self.config
                    )
                else:
                    print('Order contained invalid SLP tokens')
            else:  # order_type == buy
                slp_coin = transaction.generate_slp_utxo_of_specific_size(
                    self.wallet, self.token_hex, utxo_size=parsed_order_data['amount'], config=self.config, password=self.password
                )
                assert slp_coin
                partial_slp_tx = transaction.create_partial_slp_tx(self.wallet, slp_coin, amount_bch_to_receive,
                                                                   self.password)
                take_order_op_return = order.build_take_order_op_return(
                    self.wallet, parsed_order_data['token_hex'], order_txid, parsed_order_data['amount'], partial_slp_tx.raw, self.config, self.password
                )
                take_order_tx = transaction.create_signal_tx(self.wallet, take_order_op_return, self.config)
                self.wallet.sign_transaction(take_order_tx, password=self.password, anyonecanpay=False)

            success, take_order_tx_id = self.wallet.network.broadcast_transaction(take_order_tx)

            if success:
                if order_type.lower() == 'buy':
                    self.wallet.set_frozen_coin_state([slp_coin], True)
                    order_dict = {
                        'order_type': 'take',
                        'token_id': self.token_hex,
                        'rate': parsed_order_data['rate'],
                        'min_chunk': parsed_order_data['min_chunk'],
                        'order_id': take_order_tx_id,
                        'address': slp_coin['address'].to_slpaddr(),
                        'coin': slp_coin,
                        'amount_to_sell': slp_coin['token_value']
                    }
                    user_orders_dict = self.wallet.storage.get('user_dex_orders', {})
                    user_orders_for_token = user_orders_dict.get(self.token_hex, [])
                    user_orders_for_token.append(order_dict)
                    user_orders_dict[self.token_hex] = user_orders_for_token
                    self.wallet.storage.put('user_dex_orders', user_orders_dict)
                    self.wallet.storage.write()
            else:
                print(take_order_tx_id)

            return success

    def get_blockchain_sell_orders(self, from_block=None):
        return order_book.get_blockchain_sell_orders(self.token_hex)

    def get_blockchain_buy_orders(self, from_block=None):
        return order_book.get_blockchain_buy_orders(self.token_hex)

    def get_blockchain_take_orders(self, order_hexes, from_block=None):
        return order_book.get_blockchain_take_orders(order_hexes)

    def get_utxo_info_batch(self, utxo_list, callback):
        network = self.wallet.network
        order_book.get_utxo_info_batch(network, utxo_list, callback)

