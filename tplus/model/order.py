import logging
from dataclasses import dataclass
from typing import Any

from tplus.model.asset_identifier import IndexAsset
from tplus.model.limit_order import GTC, LimitOrderDetails
from tplus.model.market_order import MarketOrderDetails

logger = logging.getLogger(__name__)

@dataclass
class Order:
    signer: list[int]
    order_id: str
    base_asset: IndexAsset
    details: LimitOrderDetails | MarketOrderDetails
    side: str
    creation_timestamp_ns: int

    def to_dict(self):
        return {
            "signer": self.signer,
            "order_id": self.order_id,
            "base_asset": self.base_asset.to_dict(),
            "details": self.details.to_dict(),
            "side": self.side,
            "creation_timestamp_ns": self.creation_timestamp_ns
        }


@dataclass
class CreateOrderRequest:
    order: Order
    signature: list[int]

    def to_dict(self):
        return {
            "CreateOrderRequest": {
                "order": self.order.to_dict(),
                "signature": self.signature
            }
        }


def parse_orders(orders_data: list[dict[str, Any]]) -> list[Order]:
    """
    Parses a list of order dictionaries (from API response) into Order objects.
    """
    parsed_orders = []
    if not isinstance(orders_data, list):
        logger.error(f"Expected a list for orders_data, got {type(orders_data)}")
        # Depending on desired behavior, could return [] or raise TypeError
        return []

    for order_dict in orders_data:
        try:
            # Parse base_asset
            base_asset_data = order_dict.get('base_asset')
            if not isinstance(base_asset_data, dict) or 'Index' not in base_asset_data:
                raise ValueError(f"Invalid base_asset data: {base_asset_data}")
            base_asset = IndexAsset(**base_asset_data) # Assumes {'Index': value}

            # Parse details based on type (Limit or Market)
            details_data = order_dict.get('details')
            if not isinstance(details_data, dict):
                 raise ValueError(f"Invalid details data: {details_data}")

            order_details: LimitOrderDetails | MarketOrderDetails
            if 'Limit' in details_data:
                limit_data = details_data['Limit']
                # Parse nested time_in_force (GTC)
                tif_data = limit_data.get('time_in_force', {}).get('GTC', {})
                time_in_force = GTC(**tif_data)
                order_details = LimitOrderDetails(
                    limit_price=limit_data['limit_price'],
                    quantity=limit_data['quantity'],
                    time_in_force=time_in_force
                )
            elif 'Market' in details_data:
                market_data = details_data['Market']
                # Handle potentially nested quantity like {'BaseAsset': qty}
                quantity_data = market_data.get('quantity')
                if isinstance(quantity_data, dict) and 'BaseAsset' in quantity_data:
                    quantity = quantity_data['BaseAsset']
                elif isinstance(quantity_data, int): # Allow direct int quantity as fallback
                     quantity = quantity_data
                else:
                    raise ValueError(f"Invalid quantity data in Market order: {quantity_data}")

                order_details = MarketOrderDetails(
                    quantity=quantity,
                    fill_or_kill=market_data['fill_or_kill']
                )
            else:
                raise ValueError(f"Unknown order details type in data: {details_data}")

            # Create Order object
            order = Order(
                signer=order_dict['signer'],
                order_id=order_dict['order_id'],
                base_asset=base_asset,
                details=order_details,
                side=order_dict['side'],
                creation_timestamp_ns=order_dict['creation_timestamp_ns']
            )
            parsed_orders.append(order)

        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Skipping order due to parsing error: {e}. Data: {order_dict}")
            continue # Skip this order and proceed to the next

    return parsed_orders


