"""A tiny, synthetic example for a RepoInsight demonstration."""


def order_total(prices: list[float]) -> float:
    """Return the sum of the supplied item prices."""
    return sum(prices)


if __name__ == "__main__":
    print(f"Order total: {order_total([12.50, 7.50]):.2f}")
