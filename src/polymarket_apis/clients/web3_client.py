from typing import Literal
from pathlib import Path
from json import load

from web3 import Web3
from web3.middleware import geth_poa_middleware
from web3.exceptions import ContractCustomError

from ..utilities.constants import POLYGON
from ..utilities.config import get_contract_config
from ..types.common import EthAddress


def load_abi(contract_name: str) -> list:
    abi_path = Path(__file__).parent.parent/"utilities"/"web3"/"abis"/f"{contract_name}.json"
    with open(abi_path) as f:
        return load(f)


class PolymarketWeb3Client:
    def __init__(self, private_key: str , chain_id: Literal[137, 80002] = POLYGON):

        self.w3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)

        self.account = self.w3.eth.account.from_key(private_key)

        self.config = get_contract_config(chain_id, neg_risk=False)
        self.neg_risk_config = get_contract_config(chain_id, neg_risk=True)

        self.usdc_address = Web3.to_checksum_address(self.config.collateral)
        self.usdc_abi = load_abi("UChildERC20Proxy")
        self.usdc = self.contract(self.usdc_address, self.usdc_abi)

        self.conditional_tokens_address = Web3.to_checksum_address(self.config.conditional_tokens)
        self.conditional_tokens_abi = load_abi("ConditionalTokens")
        self.conditional_tokens = self.contract(self.conditional_tokens_address, self.conditional_tokens_abi)

        self.exchange_address = Web3.to_checksum_address(self.config.exchange)
        self.exchange_abi = load_abi("CTFExchange")
        self.exchange = self.contract(self.exchange_address, self.exchange_abi)

        self.neg_risk_exchange_address = Web3.to_checksum_address(self.neg_risk_config.exchange)
        self.neg_risk_exchange_abi = load_abi("NegRiskCtfExchange")
        self.neg_risk_exchange = self.contract(self.neg_risk_exchange_address, self.neg_risk_exchange_abi)

        self.proxy_factory_address = "0xaB45c5A4B0c941a2F231C04C3f49182e1A254052"
        self.proxy_factory_abi = load_abi("ProxyWalletFactory")
        self.proxy_factory = self.contract(self.proxy_factory_address, self.proxy_factory_abi)


    def contract(self, address, abi):
        return self.w3.eth.contract(
            address=Web3.to_checksum_address(address),
            abi=abi
        )

    def get_usdc_balance(self, address: EthAddress | None = None) -> float:
        if address is None:
            address = self.neg_risk_exchange.functions.getPolyProxyWalletAddress(self.account.address).call()
        balance_res = self.usdc.functions.balanceOf(address).call()
        return float(balance_res / 10e5)

    def get_token_balance(self, token_id: str, address: EthAddress | None = None) -> float:
        if address is None:
            address = self.neg_risk_exchange.functions.getPolyProxyWalletAddress(self.account.address).call()
        balance_res = self.conditional_tokens.functions.balanceOf(address, int(token_id)).call()
        return float(balance_res / 10e5)


# TODO maybe calculate keccak hashes for all errors in the abis to give better error messages
# use something like:
#   errors = [
#         "InvalidTokenId()"
#   ]
#   error_dict = {}
#   for error in errors:
#       error_hash = "0x" + Web3.keccak(text=error).hex()[:8]
#       error_dict[error_hash] = error
    
    def get_token_complement(self, token_id: str) -> str:
        try:
            return self.exchange.functions.getComplement(int(token_id)).call()
        except ContractCustomError as e:
            if e.args[0] == '0x3f6cc768':
                try:
                    return self.neg_risk_exchange.functions.getComplement(int(token_id)).call()
                except ContractCustomError as e2:
                    if e2.args[0] == '0x3f6cc768':
                        return "InvalidTokenId() or the market for it might be closed"