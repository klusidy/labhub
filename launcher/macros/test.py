# import python.client as lhc


def foo(name: str) -> str:
    "Hellow world"
    return f"Hello, {name}!"


def bar(name: str) -> str:
    "Bazinga"
    return f"Bazinga, {name}!"


def tst_example_device_01() -> str:
    print(labhub.devices.example_device_01)


def tst_types(name: str = "John", nums: int = 42, sure: bool = False) -> None:
    print(f"name: {name} (type: {type(name)})")
    print(f"nums: {nums} (type: {type(nums)})")
    print(f"sure: {sure} (type: {type(sure)})")
    return None
