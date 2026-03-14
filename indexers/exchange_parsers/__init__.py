"""Exchange CSV parsers for various crypto exchanges."""

from .base import BaseExchangeParser  # noqa: F401 — re-exported
from .coinbase import CoinbaseParser
from .crypto_com import CryptoComParser
from .wealthsimple import WealthsimpleParser
from .generic import GenericParser

PARSERS = {
    "coinbase": CoinbaseParser,
    "crypto_com": CryptoComParser,
    "crypto.com": CryptoComParser,
    "wealthsimple": WealthsimpleParser,
    "generic": GenericParser,
}


def get_parser(exchange_name):
    """Get parser for an exchange."""
    name = exchange_name.lower().replace(" ", "_").replace(".", "_")
    return PARSERS.get(name, GenericParser)


def list_supported():
    """List supported exchanges."""
    return list(PARSERS.keys())
