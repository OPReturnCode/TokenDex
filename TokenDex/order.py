import json
import time

from electroncash import slp

from . import proof_of_reserve, bfp


LOCAD_ID = b'DEX\x00'


def build_buy_order_op_return(
        wallet, token_hex, amount_to_buy: int, rate: int, min_chunk: int, bch_order_coin, config={}, password=None
):
    chunks = [LOCAD_ID, b'BUY']

    token_id = bytes.fromhex(token_hex)
    assert len(token_id) == 32
    chunks.append(token_id)

    amount_to_buy_bytes = int(amount_to_buy).to_bytes(8, 'big')
    chunks.append(amount_to_buy_bytes)

    rate_bytes = int(rate).to_bytes(8, 'big')
    chunks.append(rate_bytes)

    min_chunk_bytes = int(min_chunk).to_bytes(8, 'big')
    chunks.append(min_chunk_bytes)

    chunks.append(bytes.fromhex(bch_order_coin['prevout_hash']))
    chunks.append(int(bch_order_coin['prevout_n']).to_bytes(8, 'big'))

    bch_receive_address = bch_order_coin['address'].to_cashaddr()
    proof = proof_of_reserve.generate_proof_of_reserve(wallet, [bch_order_coin], password)
    metadata = {
        'order_type': 'buy',
        'token_id': token_hex,
        'amount_to_buy': amount_to_buy,
        'rate': rate,
        'min_chunk': min_chunk,
        'bch_receive_address': bch_receive_address,
        'proof_of_reserve': proof
    }

    file_address = bytes.fromhex(bfp.upload_file(
        wallet, json.dumps(metadata).encode(), config=config, password=password
    ))
    chunks.append(file_address)

    time.sleep(5)

    return slp.chunksToOpreturnOutput(chunks)


def build_sell_order_op_return(
        wallet, token_hex, amount_to_sell: int, rate: int, min_chunk: int,
        partial_tx: str, inputs, config={}, password=None
):
    chunks = [LOCAD_ID, b'SELL']

    token_id = bytes.fromhex(token_hex)
    assert len(token_id) == 32
    assert len(inputs) == 1  # multiple inputs are not supported for now
    chunks.append(token_id)

    amount_to_sell_bytes = int(amount_to_sell).to_bytes(8, 'big')
    chunks.append(amount_to_sell_bytes)

    rate_bytes = int(rate).to_bytes(8, 'big')
    chunks.append(rate_bytes)

    min_chunk_bytes = int(min_chunk).to_bytes(8, 'big')
    chunks.append(min_chunk_bytes)

    proof = proof_of_reserve.generate_proof_of_reserve(wallet, inputs, password)
    chunks.append(bytes.fromhex(inputs[0]['prevout_hash']))
    chunks.append(int(inputs[0]['prevout_n']).to_bytes(8, 'big'))
    metadata = {
        'order_type': 'sell',
        'token_id': token_hex,
        'amount_to_sell': amount_to_sell,
        'rate': rate,
        'min_chunk': min_chunk,
        'proof_of_reserve': proof,
        'partial_tx': partial_tx  # full partial tx when chunk == amount
    }
    file_address = bytes.fromhex(bfp.upload_file(
        wallet, json.dumps(metadata).encode(), config=config, password=password)
    )
    chunks.append(file_address)
    time.sleep(5)

    return slp.chunksToOpreturnOutput(chunks)


def parse_order_op_return(op_return):
    chunks = slp.parseOpreturnToChunks(op_return, allow_op_0=False, allow_op_number=False)
    order_type = chunks[1].decode()
    parsed_data_dict = dict()
    parsed_data_dict['order_type'] = order_type

    if order_type == 'BUY' or order_type == 'SELL':
        parsed_data_dict['token_hex'] = chunks[2].hex()
        parsed_data_dict['amount'] = int.from_bytes(chunks[3], 'big')
        parsed_data_dict['rate'] = int.from_bytes(chunks[4], 'big')
        parsed_data_dict['min_chunk'] = int.from_bytes(chunks[5], 'big')  # TAKE ORDER DOESN'T HAVE THIS! Maybe make it return a dict?
        parsed_data_dict['input_utxo'] = chunks[6].hex()
        parsed_data_dict['input_vout'] = int.from_bytes(chunks[7], 'big')
        parsed_data_dict['proof_of_reserve_tx'] = chunks[8].hex()
    elif order_type == 'TAKE':
        parsed_data_dict['token_hex'] = chunks[2].hex()
        parsed_data_dict['order_id'] = int.from_bytes(chunks[3], 'big')
        parsed_data_dict['amount'] = int.from_bytes(chunks[4], 'big')
        parsed_data_dict['proof_of_reserve_tx'] = chunks[5].hex()
        parsed_data_dict['rate'] = 1  # TODO TAKE orders don't have rate! Is this ok?

    return parsed_data_dict


def build_take_order_op_return(wallet, token_hex, order_txid_hex, amount: int, partial_tx: str, config={}, password=None):

    chunks = [LOCAD_ID, b'TAKE']

    token_bytes = bytes.fromhex(token_hex)
    assert len(token_bytes) == 32
    chunks.append(token_bytes)

    order_txid = bytes.fromhex(order_txid_hex)
    assert len(order_txid) == 32
    chunks.append(order_txid)

    amount_to_buy = int(amount).to_bytes(8, 'big')
    chunks.append(amount_to_buy)

    metadata = {
        'order_type': 'take',
        'token_id': token_hex,
        'amount': amount,
        'partial_tx': partial_tx  # full partial tx when chunk == amount
    }

    file_address = bytes.fromhex(bfp.upload_file(
        wallet, json.dumps(metadata).encode(), config=config, password=password)
    )
    chunks.append(file_address)

    time.sleep(5)

    return slp.chunksToOpreturnOutput(chunks)
