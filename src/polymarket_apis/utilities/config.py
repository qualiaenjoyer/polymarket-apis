from ..types.clob_types import ContractConfig

CONFIG = {
    137: ContractConfig(
        exchange="0xE111180000d2663C0091e4f400237545B87B996B",
        neg_risk_exchange="0xe2222d279d744050d28e00520010520000310F59",
        neg_risk_adapter="0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",
        collateral="0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB",
        conditional_tokens="0x4D97DCd97eC945f40cF65F87097ACe5EA0476045",
    ),
    80002: ContractConfig(
        exchange="0xE111180000d2663C0091e4f400237545B87B996B",
        neg_risk_exchange="0xe2222d279d744050d28e00520010520000310F59",
        neg_risk_adapter="0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",
        collateral="0x9c4e1703476e875070ee25b56a58b008cfb8fa78",
        conditional_tokens="0x69308FB512518e39F9b16112fA8d994F4e2Bf8bB",
    ),
}

NEG_RISK_CONFIG = {
    137: ContractConfig(
        exchange="0xe2222d279d744050d28e00520010520000310F59",
        neg_risk_exchange="0xe2222d279d744050d28e00520010520000310F59",
        neg_risk_adapter="0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",
        collateral="0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB",
        conditional_tokens="0x4D97DCd97eC945f40cF65F87097ACe5EA0476045",
    ),
    80002: ContractConfig(
        exchange="0xe2222d279d744050d28e00520010520000310F59",
        neg_risk_exchange="0xe2222d279d744050d28e00520010520000310F59",
        neg_risk_adapter="0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",
        collateral="0x9c4e1703476e875070ee25b56a58b008cfb8fa78",
        conditional_tokens="0x69308FB512518e39F9b16112fA8d994F4e2Bf8bB",
    ),
}

def get_contract_config(chain_id: int, neg_risk: bool = False) -> ContractConfig:
    """Get the contract configuration for the chain."""
    config = NEG_RISK_CONFIG.get(chain_id) if neg_risk else CONFIG.get(chain_id)
    if config is None:
        msg = f"Invalid chain_id: ${chain_id}"
        raise ValueError(msg)

    return config

GRAPHQL_ENDPOINTS = {
    "activity_subgraph": "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/activity-subgraph/0.0.4/gn",
    "fpmm_subgraph": "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/fpmm-subgraph/0.0.1/gn",
    "open_interest_subgraph": "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/oi-subgraph/0.0.6/gn",
    "orderbook_subgraph": "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/orderbook-subgraph/0.0.1/gn",
    "pnl_subgraph": "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/pnl-subgraph/0.0.14/gn",
    "positions_subgraph": "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/positions-subgraph/0.0.7/gn",
    "sports_oracle_subgraph": "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/sports-oracle-subgraph/0.0.1/gn",
    "wallet_subgraph": "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/wallet-subgraph/0.0.4/gn",
}
