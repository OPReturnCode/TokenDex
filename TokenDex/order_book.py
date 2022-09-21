import requests
import base64
import json

from electroncash import networks

if networks.net.TESTNET:
    bitdb_server_url = 'https://testnet-bitdb.opreturn.me/q/'
else:
    bitdb_server_url = 'https://bitdb.fountainhead.cash/q/'


def query_to_bitdb_url(query, server_url=bitdb_server_url):
    q = json.dumps(query)
    query_path = base64.standard_b64encode(q.encode()).decode()
    return server_url + query_path


def get_utxo_info_batch(network, utxo_list, callback):
    """utxo_list = [['prev_h', 'prev_n']]"""
    reqs = list()
    for utxo in utxo_list:
        reqs.append(
            ('blockchain.utxo.get_info', utxo)
        )
    network.send(reqs, callback)


def get_blockchain_sell_orders(token_hex):
    get_sell_orders_query = {
        "v": 2,
        "q": {
            "find": {
                "out.s1": "DEX\u0000",
                "out.s2": "SELL",
                "out.b3": base64.standard_b64encode(bytes.fromhex(token_hex)).decode('ascii')
            },
            "limit": 10000
        }
    }

    url = query_to_bitdb_url(get_sell_orders_query)
    res = requests.get(url)
    assert res.status_code == 200
    data = res.json()
    transactions = data['c'] + data['u']

    orders = []
    for tx in transactions:
        try:
            op_return = tx['out'][0]
            order_data = {
                'tx_id': tx['tx']['h'],
                'order_type': op_return['s2'],
                'token_id': op_return['h3'],
                'amount_to_sell': int.from_bytes(bytes.fromhex(op_return['h4']), 'big'),
                'rate': int.from_bytes(bytes.fromhex(op_return['h5']), 'big'),
                'min_chunk': int.from_bytes(bytes.fromhex(op_return['h6']), 'big'),
                'utxo_prevout_hash': op_return['h7'],
                'utxo_prevout_n': int.from_bytes(bytes.fromhex(op_return['h8']), 'big'),
                'proof_of_reserve': op_return['h9']
            }
            orders.append(order_data)
        except Exception as e:
            print(e);raise e
    return orders


def get_blockchain_buy_orders(token_hex):
    get_sell_orders_query = {
        "v": 2,
        "q": {
            "find": {
                "out.s1": "DEX\u0000",
                "out.s2": "BUY",
                "out.b3": base64.standard_b64encode(bytes.fromhex(token_hex)).decode('ascii')
            },
            "limit": 10000
        }
    }

    url = query_to_bitdb_url(get_sell_orders_query)
    res = requests.get(url)
    assert res.status_code == 200
    data = res.json()
    transactions = data['c'] + data['u']

    orders = []
    for tx in transactions:
        try:
            op_return = tx['out'][0]
            order_data = {
                'tx_id': tx['tx']['h'],
                'order_type': op_return['s2'],
                'token_id': op_return['h3'],
                'amount_to_buy': int.from_bytes(bytes.fromhex(op_return['h4']), 'big'),
                'rate': int.from_bytes(bytes.fromhex(op_return['h5']), 'big'),
                'min_chunk': int.from_bytes(bytes.fromhex(op_return['h6']), 'big'),
                'utxo_prevout_hash': op_return['h7'],
                'utxo_prevout_n': int.from_bytes(bytes.fromhex(op_return['h8']), 'big'),
                'proof_of_reserve': op_return['h9']
            }
            orders.append(order_data)
        except Exception as e:
            print(e);raise e
    return orders


def get_blockchain_take_orders(orders_hex):
    get_sell_orders_query = {
        "v": 2,
        "q": {
            "find": {
                "out.s1": "DEX\u0000",
                "out.s2": "TAKE",  # TODO use token hex as out.b3 too?
                "out.b4": {
                    "$in": [
                        base64.standard_b64encode(bytes.fromhex(order_hex)).decode('ascii') for order_hex in orders_hex
                    ]
                }
            },
            "limit": 10000
        }
    }

    url = query_to_bitdb_url(get_sell_orders_query)
    res = requests.get(url)
    assert res.status_code == 200
    data = res.json()
    transactions = data['c'] + data['u']

    orders = []
    for tx in transactions:
        try:
            op_return = tx['out'][0]
            order_data = {
                'tx_id': tx['tx']['h'],
                'order_type': op_return['s2'],
                'token_hex': op_return['h3'],
                'order_id_to_take': op_return['h4'],
                'amount': int.from_bytes(bytes.fromhex(op_return['h4']), 'big'),
                'proof_of_reserve': op_return['h5'],
            }
            orders.append(order_data)
        except Exception as e:
            print(e);raise e
    return orders
