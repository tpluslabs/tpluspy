try:
    from ape.utils.basemodel import ManagerAccessMixin
except ImportError:
    raise ImportError("Must have [evm] extras to use this manager.")

from tplus.managers.base import BaseManager


class ChainConnectedManager(BaseManager, ManagerAccessMixin):
    """
    A base manager with access to Ape managers.
    """
