import hashlib

from electroncash import bitcoinfiles
from electroncash.transaction import Transaction


def upload_file(wallet, file_bytes, config={}, password=None):
    file_tx_id = None
    tx_batch = []

    file_size = len(file_bytes)
    assert file_size <= 10522

    metadata = dict()
    metadata['filename'] = 'data'
    metadata['fileext'] = 'json'
    metadata['filesize'] = file_size
    metadata['file_sha256'] = hashlib.sha256(file_bytes).hexdigest()
    metadata['prev_file_sha256'] = None
    metadata['uri'] = None

    cost = bitcoinfiles.calculateUploadCost(file_size, metadata)
    file_receiver_address = wallet.get_addresses()[0]  # todo change this

    # TODO, guard tokens during this transaction?
    #####################################################################################

    file_220_chunks = []
    for i in range(1, (len(file_bytes) // 220) + 2):
        file_220_chunks.append(file_bytes[(i-1)*220:i*220])

    funding_tx = bitcoinfiles.getFundingTxn(wallet, file_receiver_address, cost, config)
    wallet.sign_transaction(funding_tx, password)
    tx_batch.append(funding_tx)

    prev_tx = funding_tx
    for i in range(len(file_220_chunks)):
        tx, is_metadata_tx = bitcoinfiles.getUploadTxn(
            wallet, prev_tx=prev_tx, chunk_index=i, chunk_count=len(file_220_chunks),
            chunk_data=file_220_chunks[i], config=config, metadata=metadata, file_receiver=file_receiver_address
        )
        wallet.sign_transaction(tx, password)
        tx_batch.append(tx)
        prev_tx = tx

    if not is_metadata_tx:  # last chunk didn't fit into the metadata tx
        tx, is_metadata_tx = bitcoinfiles.getUploadTxn(
            wallet, prev_tx=prev_tx, chunk_index=i+1, chunk_count=len(file_220_chunks),
            chunk_data=b'', config=config, metadata=metadata, file_receiver=file_receiver_address
        )
        wallet.sign_transaction(tx, password)
        tx_batch.append(tx)
    if is_metadata_tx:
        file_tx_id = tx.txid()

    for tx in tx_batch:
        status, tx_id = wallet.network.broadcast_transaction(tx)
        assert status
    return file_tx_id


def download_file(wallet, tx_id):
    network = wallet.network

    status, raw_metadata_tx = network.get_raw_tx_for_txid(tx_id)
    assert status
    metadata_tx = Transaction(raw_metadata_tx)

    bitcoin_files_metadata_msg = bitcoinfiles.BfpMessage.parseBfpScriptOutput(metadata_tx.outputs()[0][1])

    chunk_count = bitcoin_files_metadata_msg.op_return_fields['chunk_count']
    chunk_data = bitcoin_files_metadata_msg.op_return_fields['chunk_data']
    chunk_data_is_empty = chunk_data == b''

    downloaded_transactions = []
    assert chunk_count != 0

    def get_tx_chunks(tx_id, index):
        status, raw_tx = network.get_raw_tx_for_txid(tx_id)
        assert status is True
        tx = Transaction(raw_tx)
        try:
            data = bitcoinfiles.parseOpreturnToChunks(
                tx.outputs()[0][1].to_script(), allow_op_0=False, allow_op_number=False
            )
        except bitcoinfiles.BfpOpreturnError:  # It's the funding tx probably
            return
        downloaded_transactions.append(
            {'tx_id': metadata_tx.txid(),
             'data': data[0]
             }
        )
        index += 1
        if index <= chunk_count - 1:  # TODO removed <= to <
            get_tx_chunks(tx.inputs()[0]['prevout_hash'], index)

    if chunk_count == 1:
        if not chunk_data_is_empty:
            downloaded_transactions.append({'tx_id': metadata_tx.txid(), 'data': chunk_data})
            # DONE! FINISHED!
    if chunk_count > 1 or (chunk_count == 1 and chunk_data_is_empty):
        if not chunk_data_is_empty:
            downloaded_transactions.append({'tx_id': metadata_tx.txid(), 'data': chunk_data})
        index = 0
        get_tx_chunks(metadata_tx.inputs()[0]['prevout_hash'], index)

    f = b''
    downloaded_transactions.reverse()
    for element in downloaded_transactions:
        f += element['data']
    assert hashlib.sha256(f).hexdigest() == bitcoin_files_metadata_msg.op_return_fields['file_sha256'].hex()
    return f


