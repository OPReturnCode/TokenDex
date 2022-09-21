from electroncash.transaction import Transaction
from electroncash.bitcoin import *


def slp_get_change_address(wallet):
    """ copied from main_window.py - start of logic copied from wallet.py """
    addrs = wallet.get_change_addresses()[-wallet.gap_limit_for_change:]
    if wallet.use_change and addrs:
        # New change addresses are created only after a few
        # confirmations.  Select the unused addresses within the
        # gap limit; if none take one at random
        change_addrs = [addr for addr in addrs if
                        wallet.get_num_tx(addr) == 0]
        if not change_addrs:
            import random
            change_addrs = [random.choice(addrs)]
            change_addr = change_addrs[0]
        elif len(change_addrs) > 1:
            change_addr = change_addrs[1]
        else:
            change_addr = change_addrs[0]
    else:
        change_addr = wallet.get_addresses()[0]
    return change_addr

class AnyoneCanPaySingleTransaction(Transaction):

    def serialize_preimage(self, i, nHashType=0x00000041, use_cache = False):
        """ See `.calc_common_sighash` for explanation of use_cache feature """
        if not (nHashType & 0xff) in [0x41, 0xc1, 0xC3]:
            raise ValueError("other hashtypes not supported; submit a PR to fix this!")

        anyonecanpay = True if (nHashType & 0x80) > 0 else False

        nVersion = int_to_hex(self.version, 4)
        nHashType = int_to_hex(nHashType, 4)
        nLocktime = int_to_hex(self.locktime, 4)

        txin = self.inputs()[i]
        outpoint = self.serialize_outpoint(txin)
        preimage_script = self.get_preimage_script(txin)
        scriptCode = var_int(len(preimage_script) // 2) + preimage_script
        try:
            amount = int_to_hex(txin['value'], 8)
        except KeyError:
            raise InputValueMissing
        nSequence = int_to_hex(txin.get('sequence', 0xffffffff - 1), 4)

        hashPrevouts, hashSequence, hashOutputs = self.calc_common_sighash(use_cache = use_cache)

        if anyonecanpay or nHashType & 0xff != 0xC3:
            hashPrevouts = "0000000000000000000000000000000000000000000000000000000000000000"
            hashSequence = "0000000000000000000000000000000000000000000000000000000000000000"
        else:
            hashPrevouts = bh2u(hashPrevouts)
            hashSequence = bh2u(hashSequence)

        preimage = nVersion + hashPrevouts + hashSequence + outpoint + scriptCode + amount + nSequence + bh2u(hashOutputs) + nLocktime + nHashType
        return preimage


    def _sign_txin(self, i, j, sec, compressed, *, use_cache=False, anyonecanpay=False):
        '''Note: precondition is self._inputs is valid (ie: tx is already deserialized)'''
        pubkey = public_key_from_private_key(sec, compressed)
        # add signature
        nHashType = 0x00000043  # hardcoded, perhaps should be taken from unsigned input dict
        if anyonecanpay:
            nHashType += 0x00000080
        pre_hash = Hash(bfh(self.serialize_preimage(i, nHashType)))
        if self._sign_schnorr:
            sig = self._schnorr_sign(pubkey, sec, pre_hash)
        else:
            sig = self._ecdsa_sign(sec, pre_hash)
        reason = []
        if not self.verify_signature(bfh(pubkey), sig, pre_hash, reason=reason):
            print_error(f"Signature verification failed for input#{i} sig#{j}, reason: {str(reason)}")
            return None
        txin = self._inputs[i]
        txin['signatures'][j] = bh2u(sig + bytes((nHashType & 0xff,)))
        txin['pubkeys'][j] = pubkey  # needed for fd keys
        return txin
