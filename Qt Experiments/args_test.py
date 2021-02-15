import threading


def func(first_args, second_args):
    threading.Thread(target=otherfunc, args=first_args, daemon=True).start()
    threading.Thread(target=otherfunc2, args=second_args, daemon=True).start()


def otherfunc(a, b, c):
    print(a+b+c)


def otherfunc2(d, e):
    print("second func args: " + d + " " + e)


func(first_args=(1,2,3),second_args=("hello","world"))
