from tplus.contracts import Registry


def main():
    registry = Registry()
    print(registry.get_assets())
