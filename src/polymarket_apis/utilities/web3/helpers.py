def get_market_index(question_id: str) -> int:
    """Extract the market index from a question ID (last 2 hex characters)."""
    return int(question_id[-2:], 16)


def get_index_set(question_ids: list[str]) -> int:
    """Calculate bitwise index set from question IDs."""
    indices = [get_market_index(question_id) for question_id in question_ids]
    return sum(1 << index for index in set(indices))
