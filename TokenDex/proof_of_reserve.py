from electroncash import bitcoin
from electroncash.address import Address


def sign_message(wallet, address: str, message: str, password=None):
    try:
        addr = Address.from_string(address)
    except Exception as e:
        raise e
    assert addr.kind == addr.ADDR_P2PKH  # must have a private key ie: not a smart contract
    assert wallet.is_mine(addr)

    signature = wallet.sign_message(addr, message, password)
    return signature


def generate_proof_of_reserve(wallet, inputs, password):
    proof = dict()
    for i in inputs:
        address = i['address']
        message = i['prevout_hash'] + str(i['prevout_n'])
        signatures = sign_message(wallet, address.to_cashaddr(), message, password)
        proof[address.to_cashaddr()] = signatures.hex()
    return proof


def verify_message(address: str, signature: str, message: str):
    # todo: binascii.unhexlify(signature)
    try:
        addr = Address.from_string(address)
    except Exception as e:
        raise e
    assert addr.kind == addr.ADDR_P2PKH  # must have a private key ie: not a smart contract

    verified = bitcoin.verify_message(address, signature, message.encode('utf-8'))
    return verified
