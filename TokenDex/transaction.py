import time

from electroncash import slp
from electroncash.transaction import Transaction
from electroncash.slp_coinchooser import SlpCoinChooser
from electroncash.slp_checker import SlpTransactionChecker

from .utils import AnyoneCanPaySingleTransaction, slp_get_change_address


def create_partial_slp_tx(wallet, slp_coin, amount_bch_to_receive: int, password=None):
    bch_address = slp_coin['address']  # sends the payment back to the token UTXO address
    bch_payment_output = (0, bch_address, int(amount_bch_to_receive))

    wallet.add_input_info(slp_coin)

    # Create partial TX
    tx = Transaction.from_io([slp_coin], [bch_payment_output], sign_schnorr=True)
    tx.__class__ = AnyoneCanPaySingleTransaction  # uses SIGHASH_SINGLE |SIGHASH_ANYONECANPAY | SIGHASH_FORKID
    wallet.sign_transaction(tx, anyonecanpay=True, password=password)

    # print('partial tx generated:', tx.raw)
    return tx


def complete_partial_slp_tx(
        wallet, tx_hex, bch_amount_to_send, slp_amount_to_receive, token_hex, mandatory_coin=None,
        config={}, domain=None, password=None
):
    tx = Transaction(tx_hex)
    tx.deserialize()

    tx_outputs = tx.outputs()
    tx_inputs = tx.inputs()
    assert len(tx_outputs) == len(tx_inputs) == 1
    assert tx.output_value() == bch_amount_to_send

    op_return_output = slp.buildSendOpReturnOutput_V1(token_hex, [0, slp_amount_to_receive])

    tx_outputs.insert(0, op_return_output)
    tx_outputs.insert(2, (0, wallet.get_addresses()[0], 546))
    assert len(tx_outputs) == 3

    coins = wallet.get_spendable_coins(domain, config)
    if mandatory_coin:
        funding_tx = wallet.make_unsigned_transaction(coins, tx_outputs, config=config, mandatory_coins=[mandatory_coin])
    else:
        funding_tx = wallet.make_unsigned_transaction(coins, tx_outputs, config=config)
    funding_inputs = funding_tx.inputs()

    for i in funding_inputs:
        wallet.add_input_info(i)

    for output in funding_tx.outputs():  # add change output if existed
        if output not in tx.outputs():
            # print('Adding output')
            tx.add_outputs([output])
    # wallet.sign_transaction(tx, anyonecanpay=False, password=password)

    funding_inputs.insert(1, tx_inputs[0])
    tx_inputs = funding_inputs
    tx = Transaction.from_io(tx_inputs, tx_outputs)
    wallet.sign_transaction(tx, anyonecanpay=False, password=password)

    return tx  # return final tx


def create_signal_tx(wallet, op_return_output, config, domain=None):
    coins = wallet.get_spendable_coins(domain, config)
    outputs = [op_return_output]
    tx = wallet.make_unsigned_transaction(coins, outputs, config=config)
    return tx


def spend_slp_coin(wallet, token_hex, slp_coin, config={}, domain=None, password=None):
    op_return_output = slp.buildSendOpReturnOutput_V1(token_hex, [slp_coin['token_value']])
    slp_msg = slp.SlpMessage.parseSlpOutputScript(op_return_output[1])
    token_outputs = slp_msg.op_return_fields['token_output'][1:]
    assert len(token_outputs) == 1

    output = (0, slp_coin['address'], 546)
    bch_outputs = [op_return_output, output]
    coins = wallet.get_spendable_coins(domain, config)
    tx = wallet.make_unsigned_transaction(coins, bch_outputs, config=config, mandatory_coins=[slp_coin])
    wallet.sign_transaction(tx, password=password)

    SlpTransactionChecker.check_tx_slp(wallet, tx)

    status, tx_id = wallet.network.broadcast_transaction(tx)

    assert status
    time.sleep(5)  # TODO FIX THIS
    return status


def generate_slp_utxo_of_specific_size(wallet, token_hex, utxo_size, config={}, domain=None, password=None):
    slp_coins, op_return = SlpCoinChooser.select_coins(wallet, token_hex, utxo_size, config)
    slp_msg = slp.SlpMessage.parseSlpOutputScript(op_return[1])
    token_outputs = slp_msg.op_return_fields['token_output'][1:]
    assert len(token_outputs) < 3
    change_address = slp_get_change_address(wallet)
    output = (0, change_address, 546)
    bch_outputs = [op_return, output]
    if len(token_outputs) > 1:  # has change
        bch_outputs.append(output)
    coins = wallet.get_spendable_coins(domain, config)
    tx = wallet.make_unsigned_transaction(coins, bch_outputs, config=config, mandatory_coins=slp_coins)
    wallet.sign_transaction(tx, password=password)

    SlpTransactionChecker.check_tx_slp(wallet, tx)

    status, tx_id = wallet.network.broadcast_transaction(tx)

    assert status

    new_coin = {
        'address': change_address,
        'value': 546,
        'prevout_n': 1,
        'prevout_hash': tx_id, 'coinbase': False,
        'is_frozen_coin': False,
        'token_value': utxo_size,
        'token_id_hex': token_hex,
        'token_type': 'SLP1'
    }
    time.sleep(5)  # TODO FIX THIS
    return new_coin

