from tplus.contracts import Registry


def ape_init_extras(chain):
    return {"registry": Registry()}
