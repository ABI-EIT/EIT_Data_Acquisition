
class Foo:
    def __init__(self, on_start_args=()):
        self.on_start_args = on_start_args

    def start_new(self, on_start_args=()):
        self.work((*self.on_start_args, *on_start_args))

    @staticmethod
    def work(args):
        for arg in (*args,):
            print(arg)


if __name__ == "__main__":
    f = Foo(("hello ",))
    f.start_new(on_start_args=("world!", "it's a mee"))
