from queue import Queue

from electroncash.slp import SlpMessage
from electroncash import slp_validator_0x01
from electroncash.transaction import Transaction


def validate_transaction(wallet, txid, token_hex, prevout_n, amount):
    status, raw_tx = wallet.network.get_raw_tx_for_txid(txid)
    assert status is True
    tx = Transaction(raw_tx)
    print(tx)
    q = Queue()

    graphdb = slp_validator_0x01.GraphContext(name='DEXValidation')
    job = graphdb.make_job(tx, wallet, wallet.network)
    if not job:  # none slp tx
        return
    job.add_callback(q.put, way='weakmethod')

    job = q.get()
    assert not job.running
    try:
        n = next(iter(job.nodes.values()))
        validity_name = job.graph.validator.validity_states[n.validity]
        print(n, validity_name)
        assert job.nodes[txid].validity == 1
        assert job.nodes[txid].outputs[prevout_n] == amount
        op_return = tx.outputs()[0][1]
        slp_msg = SlpMessage.parseSlpOutputScript(op_return)
        print(slp_msg.op_return_fields)
        assert slp_msg.op_return_fields['token_id_hex'] == token_hex
        return True
    except Exception as e:
        print(e);raise e
    return False
