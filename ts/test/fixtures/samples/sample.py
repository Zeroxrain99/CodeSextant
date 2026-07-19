class Animal:
    def speak(self):
        return "woof"

    def nested_owner(self):
        def inner():
            return 1
        return inner


def top_level(x):
    return x


CONST_X = 42
config = {"a": 1}
