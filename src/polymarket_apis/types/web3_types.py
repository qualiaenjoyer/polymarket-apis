from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..types.common import EthAddress, HexString, Keccak256OrPadded


class TransactionLog(BaseModel):
    """Log entry in a transaction receipt."""

    address: EthAddress
    topics: list[Keccak256OrPadded]
    data: HexString
    block_number: int = Field(alias="blockNumber")
    transaction_hash: HexString = Field(alias="transactionHash")
    transaction_index: int = Field(alias="transactionIndex")
    block_hash: HexString = Field(alias="blockHash")
    block_timestamp: Optional[HexString] = Field(None, alias="blockTimestamp")
    log_index: int = Field(alias="logIndex")
    removed: bool


class TransactionReceipt(BaseModel):
    """Transaction receipt from the blockchain."""

    model_config = ConfigDict(populate_by_name=True)

    tx_hash: HexString = Field(alias="transactionHash")
    tx_index: int = Field(alias="transactionIndex")
    block_hash: HexString = Field(alias="blockHash")
    block_number: int = Field(alias="blockNumber")

    status: Literal[0, 1]
    type: int

    gas_used: int = Field(alias="gasUsed")
    cumulative_gas_used: int = Field(alias="cumulativeGasUsed")
    effective_gas_price: int = Field(alias="effectiveGasPrice")

    from_address: EthAddress = Field(alias="from")
    to_address: EthAddress = Field(alias="to")
    contract_address: Optional[EthAddress] = Field(None, alias="contractAddress")

    logs: list[TransactionLog]
    logs_bloom: HexString = Field(alias="logsBloom")
